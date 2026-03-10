"""ANP HTTP server for receiving messages from other agents."""

import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from .message import ANPMessage

logger = logging.getLogger(__name__)


class ANPServer:
    """HTTP server for receiving ANP messages."""

    def __init__(self, config, message_bus):
        """Initialize ANP server.

        Args:
            config: ANP configuration
            message_bus: MessageBus instance
        """
        self.config = config
        self.message_bus = message_bus
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.post("/rpc")
        async def handle_rpc(request: Request):
            """Handle JSON-RPC requests from other agents."""
            try:
                data = await request.json()
                method = data.get("method")
                params = data.get("params", {})

                if method == "receive_message":
                    result = await self._handle_receive_message(params)
                    return JSONResponse(
                        {"jsonrpc": "2.0", "result": result, "id": data.get("id")}
                    )
                else:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "error": {"code": -32601, "message": "Method not found"},
                            "id": data.get("id"),
                        }
                    )
            except Exception as e:
                logger.error(f"Error handling RPC: {e}")
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e)},
                        "id": None,
                    }
                )

    async def _handle_receive_message(self, params: dict) -> str:
        """Handle incoming message from another agent."""
        try:
            anp_msg = ANPMessage.from_dict(params)

            from nanobot.bus import InboundMessage

            inbound = InboundMessage(
                channel="anp",
                sender_id=anp_msg.sender_did,
                chat_id=anp_msg.receiver_did,
                content=anp_msg.content,
                metadata={
                    "message_type": anp_msg.message_type,
                    **anp_msg.metadata,
                },
            )

            await self.message_bus.publish_inbound(inbound)
            return "Message received"
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return f"Error: {str(e)}"

    async def start(self):
        """Start the ANP server."""
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.config.server_port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
