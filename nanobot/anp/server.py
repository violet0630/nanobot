"""ANP Server mode for receiving external ANP requests.

This module provides:
- HTTP server for receiving ANP requests
- DID WBA authentication middleware
- JSON-RPC 2.0 request handling
- Integration with nanobot message bus
- Request-response correlation for ANP calls
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from loguru import logger

try:
    from fastapi import FastAPI, Request, HTTPException, Response
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None
    Request = None
    HTTPException = None
    JSONResponse = None
    Response = None

from nanobot.anp.auth import DIDWBAAuthenticator
from nanobot.anp.agent_registry import AgentRegistry
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus


# Global storage for pending ANP requests (correlation_id -> Future)
_pending_anp_requests: dict[str, asyncio.Future] = {}


class ANPServer:
    """
    ANP Server for receiving external ANP requests from other agents.

    Implements the server-side flow with proper request-response correlation.
    """

    def __init__(
        self,
        bus: MessageBus,
        host: str = "0.0.0.0",
        port: int = 8080,
        jwt_secret: str = "your-secret-key",
        auth_enabled: bool = True,
        agent_registry_path: str | None = None,
        agent_loop = None,
    ):
        """
        Initialize the ANP server.

        Args:
            bus: The nanobot message bus
            host: Server host address
            port: Server port
            jwt_secret: JWT secret for token generation
            auth_enabled: Whether DID WBA authentication is required
            agent_registry_path: Path to agent registry file
            agent_loop: The AgentLoop instance for direct request processing
        """
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI is required for ANP server mode. Install with: pip install fastapi uvicorn")

        self.bus = bus
        self.host = host
        self.port = port
        self.auth_enabled = auth_enabled
        self.agent_loop = agent_loop  # Store agent loop reference

        self.authenticator = DIDWBAAuthenticator(jwt_secret=jwt_secret) if auth_enabled else None
        self.registry = AgentRegistry(agent_registry_path)

        self.app = FastAPI(
            title="Nanobot ANP Server",
            description="ANP (Agent Network Protocol) server for nanobot",
            version="1.0.0",
        )

        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._setup_routes()
        self._server_task: asyncio.Task | None = None

    def _setup_routes(self) -> None:
        """Set up the API routes."""

        @self.app.get("/.well-known/did.json")
        async def get_did_document():
            """Return the DID document for this agent."""
            nanobot_desc = self.registry.get("nanobot")
            if not nanobot_desc:
                raise HTTPException(status_code=404, detail="Agent description not found")

            # Create DID document from agent description
            did = nanobot_desc.get("did", "did:wba:nanobot.local:agent:user-representative")
            return {
                "@context": ["https://www.w3.org/ns/did/v1"],
                "id": did,
                "verificationMethod": [],
                "authentication": [],
                "service": [
                    {
                        "id": f"{did}#agent-description",
                        "type": "AgentDescription",
                        "serviceEndpoint": f"http://{self.host}:{self.port}/ad.json",
                    }
                ],
            }

        @self.app.get("/ad.json")
        async def get_agent_description():
            """Return the agent description document."""
            nanobot_desc = self.registry.get("nanobot")
            if not nanobot_desc:
                raise HTTPException(status_code=404, detail="Agent description not found")

            # Add URL fields
            desc = nanobot_desc.copy()
            desc["url"] = f"http://{self.host}:{self.port}/ad.json"
            return desc

        @self.app.post("/anp/rpc")
        async def handle_jsonrpc(request: Request):
            """
            Handle JSON-RPC 2.0 requests from external ANP agents.

            This endpoint:
            1. Verifies DID WBA authentication
            2. Parses JSON-RPC request
            3. Creates InboundMessage with correlation_id and response_future
            4. Waits for agent loop to process and set result
            5. Returns JSON-RPC response
            """
            # Check authentication
            caller_did = None
            if self.auth_enabled:
                auth_header = request.headers.get("Authorization", "")
                bearer_token = request.headers.get("Authorization", "").replace("Bearer ", "")

                # First try JWT token
                if bearer_token and not auth_header.startswith("DIDWba"):
                    token_result = self.authenticator.verify_jwt_token(bearer_token)
                    if not token_result["valid"]:
                        raise HTTPException(
                            status_code=401,
                            detail={
                                "error": "invalid_access_token",
                                "error_description": token_result.get("error"),
                            },
                        )
                    caller_did = token_result["payload"].get("sub")
                # Then try DID WBA authentication
                elif auth_header.startswith("DIDWba"):
                    auth_result = self.authenticator.verify_auth_header(
                        auth_header,
                        expected_audience=request.headers.get("Host", f"{self.host}:{self.port}"),
                    )
                    if not auth_result["valid"]:
                        raise HTTPException(
                            status_code=401,
                            detail={
                                "error": "invalid_did",
                                "error_description": auth_result.get("error"),
                            },
                        )
                    caller_did = auth_result["did"]
                    # Generate JWT token for next requests
                    token = self.authenticator.generate_jwt_token(caller_did)
                    # Return token in header for next requests
                    response = JSONResponse(content={"message": "Authenticated", "token": token})
                    response.headers["X-ANP-Token"] = token
                    return response
                else:
                    raise HTTPException(
                        status_code=401,
                        detail={"error": "missing_authentication", "error_description": "Authentication required"},
                    )
            else:
                caller_did = "anonymous"

            # Parse JSON-RPC request
            try:
                rpc_request = await request.json()
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")

            # Validate JSON-RPC 2.0 format
            if not isinstance(rpc_request, dict):
                return self._jsonrpc_error(-32600, "Invalid Request", None)

            jsonrpc_version = rpc_request.get("jsonrpc")
            request_id = rpc_request.get("id")
            method = rpc_request.get("method")
            params = rpc_request.get("params", {})

            if jsonrpc_version != "2.0":
                return self._jsonrpc_error(-32600, "Invalid Request: jsonrpc version must be 2.0", request_id)

            if not method:
                return self._jsonrpc_error(-32600, "Invalid Request: method is required", request_id)

            # Extract caller_did from params (ANP protocol standard)
            # This allows the caller to identify themselves without requiring auth
            params_caller_did = params.get("caller_did") or params.get("from")
            if params_caller_did and (not caller_did or caller_did == "anonymous"):
                caller_did = params_caller_did
                logger.debug(f"[ANP Server] Using caller_did from params: {caller_did}")

            if not caller_did:
                caller_did = "anonymous"

            # Process the ANP request with proper correlation
            try:
                result = await self._process_anp_request_with_correlation(
                    caller_did=caller_did,
                    method=method,
                    params=params,
                )

                return JSONResponse({
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": request_id,
                })

            except asyncio.TimeoutError:
                return self._jsonrpc_error(-32603, "Request timeout", request_id)
            except Exception as e:
                logger.exception("Error processing ANP request")
                return self._jsonrpc_error(-32603, f"Internal error: {e}", request_id)

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    def _jsonrpc_error(self, code: int, message: str, request_id: Any) -> JSONResponse:
        """Create a JSON-RPC error response."""
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message,
            },
            "id": request_id,
        })

    async def _process_anp_request_with_correlation(
        self,
        caller_did: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Process an ANP request with proper request-response correlation.

        This method directly calls the agent loop's _process_anp_message method
        to handle the request and get a response.

        Args:
            caller_did: The DID of the calling agent
            method: The method name being called
            params: Method parameters

        Returns:
            Result dictionary from the agent loop processing
        """
        # Use the agent loop instance passed during initialization
        agent_loop = self.agent_loop
        if not agent_loop:
            return {
                "status": "error",
                "message": "Agent loop not available"
            }

        # Build the request message for nanobot
        request_content = self._build_anp_request_message(method, params, caller_did)

        # Create inbound message for processing
        from nanobot.bus.events import InboundMessage
        inbound_msg = InboundMessage(
            channel="anp",
            sender_id=caller_did,
            chat_id=caller_did,
            content=request_content,
            metadata={
                "method": method,
                "params": params,
                "caller_did": caller_did,
                "correlation_id": f"anp_{secrets.token_urlsafe(16)}",
            },
        )

        try:
            # Directly call the agent loop's _process_anp_message method
            # This bypasses the normal message queue for faster response
            outbound_msg = await agent_loop._process_anp_message(inbound_msg)

            # Extract the content and metadata
            result_content = outbound_msg.content if outbound_msg else ""

            # Try to parse as JSON for structured response
            try:
                # If the response is already JSON (starts with {), parse it
                if result_content.strip().startswith("{"):
                    return json.loads(result_content)
                else:
                    # Otherwise, wrap in a success response
                    return {
                        "status": "success",
                        "message": result_content
                    }
            except json.JSONDecodeError:
                return {
                    "status": "success",
                    "message": result_content
                }

        except Exception as e:
            logger.exception(f"[ANP Server] Error processing request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def _build_anp_request_message(
        self,
        method: str,
        params: dict[str, Any],
        caller_did: str,
    ) -> str:
        """Build a human-readable message from the ANP request."""
        # Convert the structured request to natural language
        # This helps the LLM understand the request context

        # Generic method description (not hardcoded)
        method_desc = f"calling method '{method}'"

        params_str = ""
        if params:
            formatted_params = []
            for k, v in params.items():
                formatted_params.append(f"{k}={v}")
            params_str = ". Parameters: " + ", ".join(formatted_params)

        return (
            f"[ANP Request from {caller_did}]\n"
            f"The agent is {method_desc}"
            f"{params_str}.\n\n"
            f"Please analyze this request and respond appropriately. "
            f"If this requires user authorization, forward to the user via the available chat channel."
        )

    async def start(self) -> None:
        """Start the ANP server."""
        logger.info("Starting ANP server on {}:{}", self.host, self.port)

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        self._server_task = asyncio.create_task(server.serve())

        # Wait a bit for server to start
        await asyncio.sleep(0.5)

        logger.info("ANP server started successfully")

    async def stop(self) -> None:
        """Stop the ANP server."""
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        logger.info("ANP server stopped")


def get_pending_request(correlation_id: str) -> asyncio.Future | None:
    """Get a pending ANP request Future by correlation_id."""
    return _pending_anp_requests.get(correlation_id)


def complete_pending_request(correlation_id: str, result: dict[str, Any]) -> bool:
    """Complete a pending ANP request by setting the Future result."""
    future = _pending_anp_requests.get(correlation_id)
    if future and not future.done():
        future.set_result(result)
        return True
    return False
