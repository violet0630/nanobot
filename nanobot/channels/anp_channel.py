"""ANP channel adapter for agent-to-agent communication."""

import asyncio
from typing import Any

from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus


class ANPChannel(BaseChannel):
    """Channel for ANP (Agent Network Protocol) communication."""

    name = "anp"

    def __init__(self, config: Any, bus: MessageBus, anp_server=None):
        """Initialize ANP channel.

        Args:
            config: ANP configuration
            bus: MessageBus instance
            anp_server: ANPServer instance (optional, will be set later)
        """
        super().__init__(config, bus)
        self.anp_server = anp_server

    async def start(self) -> None:
        """Start ANP server (handled by ANPServer separately)."""
        self._running = True
        # ANP server is started separately in gateway command
        # This channel just marks itself as running

    async def stop(self) -> None:
        """Stop ANP channel."""
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """ANP channel doesn't send directly - sending is handled by ANPClient."""
        # Outbound messages to agents are handled by SendMessageTool + ANPClient
        # This method is not used for ANP
        pass
