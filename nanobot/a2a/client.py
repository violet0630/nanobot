"""A2A client wrapper for nanobot integration.

This module provides a wrapper around the a2a-sdk-python client,
managing connections to multiple A2A servers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from loguru import logger

try:
    import httpx
    from a2a.client.card_resolver import A2ACardResolver
    from a2a.client.client_factory import ClientFactory, ClientConfig
    from a2a.types import AgentCard, Message, Part, Role, TextPart
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    AgentCard = None
    ClientConfig = None

if TYPE_CHECKING:
    from nanobot.config.schema import A2AServerConfig


class A2AClientWrapper:
    """Wrapper around a2a-sdk client for nanobot integration.

    Manages connections to multiple A2A servers, handles Agent Card
    discovery, and provides message sending capabilities.
    """

    def __init__(self, servers: dict[str, A2AServerConfig]):
        """Initialize the A2A client wrapper.

        Args:
            servers: Dictionary mapping server names to their configurations.
        """
        if not A2A_AVAILABLE:
            raise ImportError(
                "a2a-sdk is not installed. Install with: pip install 'nanobot-ai[a2a]'"
            )

        self.servers = servers
        self._clients: dict[str, Any] = {}
        self._cards: dict[str, AgentCard] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def connect_all(self) -> None:
        """Connect to all configured A2A servers and fetch Agent Cards."""
        if not self.servers:
            logger.info("No A2A servers configured")
            return

        self._http_client = httpx.AsyncClient(timeout=30.0)

        for name, config in self.servers.items():
            if not config.enabled:
                logger.info("A2A server '{}' is disabled, skipping", name)
                continue

            try:
                await self._connect_server(name, config)
            except Exception as e:
                logger.warning("Failed to connect to A2A server '{}': {}", name, e)

    async def _connect_server(self, name: str, config: A2AServerConfig) -> None:
        """Connect to a single A2A server and fetch its Agent Card.

        Args:
            name: Server identifier.
            config: Server configuration.
        """
        logger.info("Connecting to A2A server '{}' at {}", name, config.url)

        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        # Fetch Agent Card
        resolver = A2ACardResolver(self._http_client, config.url)
        card = await resolver.get_agent_card()
        self._cards[name] = card
        logger.info(
            "Fetched Agent Card for '{}': {} (skills: {})",
            name,
            card.name,
            len(card.skills),
        )

        # Create client
        client_config = ClientConfig(streaming=True)

        # Add API key header if configured
        interceptors = []
        if config.api_key:
            from a2a.client.middleware import ClientCallInterceptor

            class ApiKeyInterceptor(ClientCallInterceptor):
                def __init__(self, key: str):
                    self.key = key

                async def intercept(
                    self, method: str, params: dict[str, Any], next_fn: callable
                ) -> Any:
                    # Inject API key into request via headers
                    return await next_fn(method, params)

            # Store for later use in client initialization
            self._server_api_keys = getattr(self, "_server_api_keys", {})
            self._server_api_keys[name] = config.api_key

        factory = ClientFactory(client_config)

        # Set up authentication headers if API key is configured
        if config.api_key:
            import httpx

            auth_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {config.api_key}"},
                timeout=30.0,
            )
            factory = ClientFactory(ClientConfig(streaming=True, httpx_client=auth_client))

        client = factory.create(card)
        self._clients[name] = client
        logger.info("Connected to A2A server '{}'", name)

    async def get_agent_card(self, server_name: str) -> AgentCard | None:
        """Get cached Agent Card for a server.

        Args:
            server_name: Name of the configured server.

        Returns:
            The cached AgentCard, or None if not found.
        """
        return self._cards.get(server_name)

    async def send_message(
        self,
        server_name: str,
        message: str,
        session_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Send message to specific A2A server, yield streaming response.

        Args:
            server_name: Name of the configured server.
            message: Message content to send.
            session_id: Optional session/context ID for conversation tracking.

        Yields:
            Text chunks from the streaming response.

        Raises:
            ValueError: If server is not connected.
        """
        if server_name not in self._clients:
            raise ValueError(f"A2A server '{server_name}' is not connected")

        client = self._clients[server_name]
        card = self._cards[server_name]

        logger.debug("Sending message to A2A server '{}': {}", server_name, message[:100])

        try:
            # Create user message
            import uuid
            user_message = Message(
                role=Role.user,
                message_id=str(uuid.uuid4()),
                parts=[TextPart(text=message)],
                context_id=session_id,
            )

            # Send and stream responses
            async for event in client.send_message(user_message):
                # Handle different event types from A2A protocol
                if isinstance(event, list) and len(event) > 0:
                    event_item = event[0]

                    # Task status update
                    if hasattr(event_item, "kind") and event_item.kind == "status-update":
                        status = event_item.status
                        if status.state.value in ("completed", "failed", "canceled"):
                            logger.debug(
                                "Task '{}' completed with state: {}",
                                status.state.value,
                            )

                    # Message with text content
                    elif hasattr(event_item, "kind") and event_item.kind == "message":
                        for part in event_item.parts:
                            if hasattr(part, "kind") and part.kind == "text":
                                yield part.text
                            elif hasattr(part.root, "text"):
                                # TextPart wrapped in Part
                                yield part.root.text

                    # Task object (initial response)
                    elif hasattr(event_item, "kind") and event_item.kind == "task":
                        # Initial task creation, wait for actual message
                        pass

        except Exception as e:
            logger.error("Error sending message to A2A server '{}': {}", server_name, e)
            raise

    async def get_all_cards(self) -> dict[str, AgentCard]:
        """Get all cached Agent Cards.

        Returns:
            Dictionary mapping server names to their Agent Cards.
        """
        return self._cards.copy()

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected.

        Args:
            server_name: Name of the configured server.

        Returns:
            True if connected, False otherwise.
        """
        return server_name in self._clients

    async def close_all(self) -> None:
        """Close all connections."""
        for name, client in self._clients.items():
            try:
                if hasattr(client, "close"):
                    await client.close()
            except Exception as e:
                logger.warning("Error closing A2A client '{}': {}", name, e)

        self._clients.clear()
        self._cards.clear()

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("All A2A connections closed")
