"""ANP Client mode for sending requests to other agents.

This module provides:
- HTTP client for sending ANP requests
- DID WBA authentication for outgoing requests
- JSON-RPC 2.0 request construction
- Agent discovery and interface lookup
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from nanobot.anp.auth import DIDWBAAuth
from nanobot.anp.agent_registry import AgentRegistry


class ANPClient:
    """
    ANP Client for sending requests to other ANP-compliant agents.

    Implements the client-side flow:
    1. Target Discovery (get agent description from registry)
    2. Parse & Understand (read target agent's interfaces)
    3. Prepare Request (build JSON-RPC with DID WBA auth)
    4. Response Processing (handle and return results)
    """

    def __init__(
        self,
        auth: DIDWBAAuth | None = None,
        agent_registry: AgentRegistry | None = None,
    ):
        """
        Initialize the ANP client.

        Args:
            auth: DID WBA authentication instance
            agent_registry: Agent registry for discovery
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for ANP client mode. Install with: pip install aiohttp")

        self.auth = auth
        self.registry = agent_registry or AgentRegistry()
        self._session = None
        self._access_tokens: dict[str, str] = {}  # URL -> token cache

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def discover_agent(self, agent_name: str) -> dict[str, Any] | None:
        """
        Discover an agent by name from the registry.

        Args:
            agent_name: The name/identifier of the target agent

        Returns:
            Agent description dict or None if not found
        """
        agent = self.registry.get(agent_name)
        if agent:
            logger.debug("Discovered agent: {} ({})", agent_name, agent.get("did"))
        else:
            logger.warning("Agent not found in registry: {}", agent_name)
        return agent

    async def fetch_agent_description(self, url: str) -> dict[str, Any] | None:
        """
        Fetch an agent description document from a URL.

        Args:
            url: The URL to the agent's ad.json

        Returns:
            Agent description dict or None if fetch failed
        """
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning("Failed to fetch agent description: HTTP {}", response.status)
                    return None
        except Exception as e:
            logger.error("Error fetching agent description from {}: {}", url, e)
            return None

    async def call(
        self,
        agent_name: str,
        method: str,
        params: dict[str, Any] | None = None,
        use_auth: bool = True,
    ) -> dict[str, Any]:
        """
        Call a method on a remote agent.

        Args:
            agent_name: The name/identifier of the target agent
            method: The method name to call
            params: Method parameters
            use_auth: Whether to use DID WBA authentication

        Returns:
            Result dict from the remote agent
        """
        # Get agent info from registry
        agent = await self.discover_agent(agent_name)
        if not agent:
            return {
                "status": "error",
                "message": f"Agent not found: {agent_name}",
            }

        # Get the RPC endpoint URL
        rpc_url = self._get_rpc_url(agent)
        if not rpc_url:
            return {
                "status": "error",
                "message": f"Agent {agent_name} has no RPC endpoint configured",
            }

        # Build JSON-RPC request
        rpc_request = {
            "jsonrpc": "2.0",
            "id": f"{agent_name}-{method}",
            "method": method,
            "params": params or {},
        }

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
        }

        # Add authentication
        if use_auth and self.auth:
            auth_result = await self._authenticate_request(rpc_url, agent.get("did", ""))
            if "error" in auth_result and auth_result["error"]:
                return {"status": "error", "message": auth_result["error"]}
            if "header" in auth_result:
                headers["Authorization"] = auth_result["header"]

        # Send the request
        return await self._send_jsonrpc(rpc_url, rpc_request, headers)

    def _get_rpc_url(self, agent: dict[str, Any]) -> str | None:
        """Extract the RPC URL from an agent description."""
        for interface in agent.get("interfaces", []):
            if interface.get("protocol") == "openrpc":
                url = interface.get("url")
                if url:
                    return url
        return None

    async def _authenticate_request(self, url: str, target_did: str) -> dict[str, Any]:
        """
        Prepare authentication for a request.

        Args:
            url: The target URL
            target_did: The target agent's DID

        Returns:
            Dict with 'header' or 'error'
        """
        if not self.auth:
            return {"error": "No auth configured"}

        try:
            # Extract audience from URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            audience = parsed.netloc or parsed.hostname or "localhost"

            # Check for cached token
            if url in self._access_tokens:
                return {"header": f"Bearer {self._access_tokens[url]}"}

            # Create DID WBA auth header
            header_name, header_value = self.auth.create_auth_header(audience=audience)
            return {"header": header_value}

        except Exception as e:
            logger.error("Error creating auth header: {}", e)
            return {"error": str(e)}

    async def _send_jsonrpc(
        self,
        url: str,
        request: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Send a JSON-RPC request.

        Args:
            url: The target URL
            request: The JSON-RPC request dict
            headers: HTTP headers including auth

        Returns:
            Result dict or error dict
        """
        try:
            session = await self._get_session()
            async with session.post(url, json=request, headers=headers) as response:
                response_data = await response.json()

                if response.status == 200:
                    # Check for JSON-RPC response
                    if "result" in response_data:
                        # Cache access token if returned
                        if response.headers.get("Authorization", "").startswith("Bearer "):
                            token = response.headers["Authorization"][7:]
                            self._access_tokens[url] = token

                        return response_data["result"]
                    elif "error" in response_data:
                        return {
                            "status": "error",
                            "message": response_data["error"].get("message", "Unknown error"),
                            "code": response_data["error"].get("code"),
                        }
                    else:
                        return response_data
                else:
                    return {
                        "status": "error",
                        "message": f"HTTP {response.status}",
                        "detail": response_data,
                    }

        except aiohttp.ClientError as e:
            logger.error("HTTP error calling {}: {}", url, e)
            return {
                "status": "error",
                "message": f"Connection error: {e}",
            }
        except Exception as e:
            logger.exception("Error calling {} {}", url, request.get("method"))
            return {
                "status": "error",
                "message": str(e),
            }

    async def send_notification(
        self,
        agent_name: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Send a natural language notification to an agent.

        Args:
            agent_name: The name/identifier of the target agent
            message: The natural language message to send

        Returns:
            Result dict from the remote agent
        """
        return await self.call(
            agent_name=agent_name,
            method="naturalLanguageNotification",
            params={"message": message},
        )

    def format_request_for_llm(
        self,
        agent_name: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Format an ANP request as a natural language description for the LLM.

        This helps the LLM understand what external service is being called.

        Args:
            agent_name: The name/identifier of the target agent
            method: The method name to call
            params: Method parameters

        Returns:
            Natural language description of the request
        """
        agent = self.registry.get(agent_name)
        if not agent:
            return f"Call {method} on agent {agent_name} (agent not found in registry)"

        agent_role = agent.get("role", agent.get("name", agent_name))
        agent_did = agent.get("did", "unknown")

        params_str = ""
        if params:
            formatted_params = []
            for k, v in params.items():
                formatted_params.append(f"{k}={v}")
            params_str = f" with parameters: {', '.join(formatted_params)}"

        return (
            f"I will call the {method} method on {agent_role} ({agent_name}, DID: {agent_did})"
            f"{params_str}."
        )

    def get_available_methods(self, agent_name: str) -> list[str]:
        """
        Get available methods for an agent based on its description.

        Args:
            agent_name: The name/identifier of the target agent

        Returns:
            List of available method names
        """
        agent = self.registry.get(agent_name)
        if not agent:
            return []

        # For now, return common ANP methods
        # In a full implementation, this would parse OpenRPC documents
        common_methods = [
            "naturalLanguageNotification",
            "getSecurityStatus",
            "requestLogAccess",
            "provideVerificationCode",
            "sendAlert",
        ]

        return common_methods
