"""ANP client for sending messages to agents and users, using OpenANP SDK."""

import logging
from typing import Optional

from anp.openanp import RemoteAgent
from anp.authentication import DIDWbaAuthHeader

logger = logging.getLogger(__name__)


class ANPClient:
    """Client for sending ANP messages via OpenANP SDK."""

    def __init__(self, message_bus=None, registry=None, auth: DIDWbaAuthHeader = None):
        """Initialize ANP client.

        Args:
            message_bus: MessageBus instance for sending to users
            registry: AgentRegistry for resolving agent ad_urls
            auth: DIDWbaAuthHeader for authenticated requests
        """
        self.message_bus = message_bus
        self.registry = registry
        self.auth = auth
        self._remote_agents: dict[str, RemoteAgent] = {}

    async def _get_remote_agent(self, target_did: str) -> Optional[RemoteAgent]:
        """Discover and cache a remote agent by DID."""
        if target_did in self._remote_agents:
            logger.debug("Using cached remote agent for %s", target_did)
            return self._remote_agents[target_did]

        if not self.registry:
            logger.error("Agent registry not configured")
            return None

        agent_info = self.registry.get_agent_info(target_did)
        if not agent_info:
            logger.error("Agent %s not found in registry", target_did)
            return None

        ad_url = agent_info.get("ad_url")
        if not ad_url:
            logger.error("No ad_url for agent %s in registry", target_did)
            return None

        try:
            logger.info("Discovering agent %s at %s", target_did, ad_url)
            remote = await RemoteAgent.discover(ad_url, self.auth)
            self._remote_agents[target_did] = remote
            logger.info("Successfully discovered agent %s", target_did)
            return remote
        except Exception as e:
            logger.error("Failed to discover agent %s at %s: %s", target_did, ad_url, e, exc_info=True)
            return None

    async def send_to_agent(self, target_did: str, sender_did: str, content: str, message_type: str = "agent_request") -> str:
        """Send message to another agent via OpenANP SDK.

        Args:
            target_did: Target agent DID
            sender_did: This agent's DID
            content: Message content
            message_type: Message type

        Returns:
            Response from target agent
        """
        remote = await self._get_remote_agent(target_did)
        if not remote:
            return f"Error: Agent {target_did} not found or unreachable"

        try:
            result = await remote.receive_message(
                sender_did=sender_did,
                content=content,
                message_type=message_type,
            )
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error("Error sending to agent %s: %s", target_did, e)
            return f"Error: {str(e)}"

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

        from nanobot.bus.events import OutboundMessage

        outbound = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            metadata=metadata or {},
        )
        await self.message_bus.publish_outbound(outbound)
        return "Message sent to user"
