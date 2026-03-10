"""ANP client for sending messages to agents and users."""

import httpx
from typing import Optional

from .message import ANPMessage


class ANPClient:
    """Client for sending ANP messages."""

    def __init__(self, message_bus=None, registry=None):
        """Initialize ANP client.

        Args:
            message_bus: MessageBus instance for sending to users
            registry: AgentRegistry for resolving agent endpoints
        """
        self.message_bus = message_bus
        self.registry = registry
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def send_to_agent(self, target_did: str, message: ANPMessage) -> str:
        """Send message to another agent via HTTP JSON-RPC.

        Args:
            target_did: Target agent DID
            message: ANP message to send

        Returns:
            Response from target agent
        """
        if not self.registry:
            return "Error: Agent registry not configured"

        agent_info = self.registry.get_agent_info(target_did)
        if not agent_info:
            return f"Error: Agent {target_did} not found in registry"

        endpoint = agent_info["endpoint"]

        try:
            response = await self.http_client.post(
                endpoint,
                json={
                    "jsonrpc": "2.0",
                    "method": "receive_message",
                    "params": message.to_dict(),
                    "id": 1,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", "Message sent")
        except Exception as e:
            return f"Error sending to agent: {str(e)}"

    async def send_to_user(
        self, channel: str, chat_id: str, content: str, metadata: Optional[dict] = None
    ) -> str:
        """Send message to user via MessageBus.

        Args:
            channel: Channel name (e.g., "feishu")
            chat_id: Chat ID
            content: Message content
            metadata: Optional metadata

        Returns:
            Status message
        """
        if not self.message_bus:
            return "Error: MessageBus not configured"

        from nanobot.bus import OutboundMessage

        outbound = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            metadata=metadata or {},
        )

        await self.message_bus.publish_outbound(outbound)
        return "Message sent to user"

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()
