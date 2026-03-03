"""A2A Client Manager for nanobot.

This module manages connections to remote nanobot instances, allowing
nanobot to call other nanobots using the A2A protocol.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from loguru import logger

try:
    import httpx
    from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
    from a2a.types import (
        AgentCard,
        Message,
        Part,
        Role,
        Task,
        TaskState,
        TextPart,
        TransportProtocol,
    )
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    httpx = None  # type: ignore
    AgentCard = None  # type: ignore


class RemoteAgentConnection:
    """Connection to a remote nanobot agent."""

    def __init__(
        self,
        name: str,
        url: str,
        description: str,
        client_factory: ClientFactory,
        agent_card: AgentCard,
    ):
        self.name = name
        self.url = url
        self.description = description
        self.client_factory = client_factory
        self.agent_card = agent_card
        self._client = None

    async def get_client(self):
        """Get or create the A2A client."""
        if self._client is None:
            self._client = self.client_factory.create_client(self.agent_card)
        return self._client

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display."""
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description or self.agent_card.description,
        }


class A2AClientManager:
    """Manager for A2A client connections to remote nanobots.

    This manager handles:
    - Discovering remote agents via their AgentCards
    - Creating and caching client connections
    - Sending messages to remote agents
    - Lazy connection with retry support for startup order issues
    """

    def __init__(self, remote_agents: list[dict[str, str]]):
        if not A2A_AVAILABLE:
            raise ImportError(
                "a2a-python is not installed. "
                "Install it with: pip install a2a-python"
            )

        self.remote_agents: dict[str, RemoteAgentConnection] = {}
        self.httpx_client = httpx.AsyncClient(timeout=30.0)
        self.client_factory = self._create_client_factory()
        self._initialized = False
        # Track agents that failed to connect (for lazy retry)
        self._pending_agents: dict[str, dict[str, str]] = {}

    def _create_client_factory(self) -> ClientFactory:
        """Create the A2A client factory."""
        config = ClientConfig(
            httpx_client=self.httpx_client,
            supported_transports=[
                TransportProtocol.jsonrpc,
                TransportProtocol.http_json,
            ],
        )
        return ClientFactory(config)

    async def initialize(self) -> None:
        """Initialize connections to remote agents.
        
        Failed connections are stored for lazy retry when sending messages.
        This handles the startup order issue where remote agents may not be
        available yet.
        """
        if self._initialized:
            return

        logger.info("Initializing A2A client connections...")

        # Discover and connect to remote agents
        for agent_config in self.remote_agents_configs:
            try:
                await self._connect_remote_agent(agent_config)
            except Exception as e:
                # Store failed connection for lazy retry
                name = agent_config.get("name", "unknown")
                self._pending_agents[name] = agent_config
                logger.warning(
                    "Failed to connect to remote agent '{}' at {}: {}. "
                    "Will retry when sending messages.",
                    name,
                    agent_config.get("url", "unknown"),
                    e,
                )

        self._initialized = True
        total_known = len(self.remote_agents) + len(self._pending_agents)
        logger.info(
            "A2A client manager initialized: {} connected, {} pending",
            len(self.remote_agents),
            len(self._pending_agents),
        )

    async def _connect_remote_agent(self, agent_config: dict[str, str]) -> None:
        """Connect to a remote agent and retrieve its AgentCard."""
        url = agent_config["url"]
        name = agent_config["name"]
        description = agent_config.get("description", "")

        logger.info("Connecting to remote agent '{}' at {}", name, url)

        # Resolve the AgentCard
        resolver = A2ACardResolver(self.httpx_client, url)
        agent_card = await resolver.get_agent_card()

        # Create the connection
        connection = RemoteAgentConnection(
            name=name,
            url=url,
            description=description,
            client_factory=self.client_factory,
            agent_card=agent_card,
        )

        self.remote_agents[name] = connection
        logger.info("Connected to remote agent '{}'", name)

    @property
    def remote_agents_configs(self) -> list[dict[str, str]]:
        """Get list of remote agent configs (to be set externally)."""
        # This will be populated via setter
        return getattr(self, "_remote_agents_configs", [])

    def set_remote_agents(self, agents: list[dict[str, str]]) -> None:
        """Set the list of remote agents to connect to."""
        self._remote_agents_configs = agents

    def list_remote_agents(self) -> list[dict[str, Any]]:
        """List all configured remote agents (connected and pending).
        
        Returns a list with both connected agents and pending agents
        (those that failed initial connection but may become available later).
        """
        result = []
        
        # Add connected agents
        for conn in self.remote_agents.values():
            info = conn.to_dict()
            info["status"] = "connected"
            result.append(info)
        
        # Add pending agents (not yet connected)
        for name, config in self._pending_agents.items():
            result.append({
                "name": name,
                "url": config.get("url", ""),
                "description": config.get("description", "Pending connection"),
                "status": "pending",
            })
        
        return result

    async def _try_connect_pending_agent(self, agent_name: str) -> bool:
        """Try to connect a pending agent.
        
        Returns:
            True if successfully connected, False otherwise
        """
        if agent_name not in self._pending_agents:
            return False
            
        agent_config = self._pending_agents[agent_name]
        try:
            await self._connect_remote_agent(agent_config)
            # Successfully connected, remove from pending
            del self._pending_agents[agent_name]
            logger.info(
                "Successfully connected to pending agent '{}' after retry",
                agent_name
            )
            return True
        except Exception as e:
            logger.warning(
                "Retry connection to agent '{}' failed: {}",
                agent_name,
                e
            )
            return False

    async def send_message(
        self,
        agent_name: str,
        message: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> str | list[str]:
        """Send a message to a remote agent.

        Args:
            agent_name: Name of the remote agent to send to
            message: Message content
            context_id: Optional context ID for conversation continuity
            task_id: Optional task ID

        Returns:
            Response text or list of texts

        Raises:
            ValueError: If agent not found or request fails
        """
        # If agent is not connected but is pending, try to connect now (lazy retry)
        if agent_name not in self.remote_agents:
            if agent_name in self._pending_agents:
                await self._try_connect_pending_agent(agent_name)
        
        if agent_name not in self.remote_agents:
            available = list(self.remote_agents.keys())
            pending = list(self._pending_agents.keys())
            raise ValueError(
                f"Remote agent '{agent_name}' not found. "
                f"Connected agents: {available}. "
                f"Pending agents (not yet available): {pending}"
            )

        connection = self.remote_agents[agent_name]
        client = await connection.get_client()

        # Build the message
        request_message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            message_id=str(uuid.uuid4()),
            context_id=context_id,
            task_id=task_id,
        )

        logger.info(
            "Sending A2A message to '{}': {}",
            agent_name,
            message[:100],
        )

        # Send the message
        response = await client.send_message(request_message)

        # Handle response
        if isinstance(response, str):
            return response
        elif isinstance(response, list):
            return response
        elif hasattr(response, "parts"):
            # Message with parts
            result = []
            for part in response.parts:
                if hasattr(part.root, "text"):
                    result.append(part.root.text)
            return "\n".join(result) if result else "Empty response"
        else:
            # Task object
            if isinstance(response, Task):
                if response.status.state == TaskState.completed:
                    if response.status.message:
                        parts = response.status.message.parts
                        result = []
                        for part in parts:
                            if hasattr(part.root, "text"):
                                result.append(part.root.text)
                        return "\n".join(result) if result else "Task completed"
                    return "Task completed"
                elif response.status.state == TaskState.failed:
                    raise ValueError(
                        f"Remote agent task failed: "
                        f"{response.status.message.parts[0].root.text if response.status.message and response.status.message.parts else 'Unknown error'}"
                    )
                else:
                    return f"Task state: {response.status.state}"

        return str(response)

    async def close(self) -> None:
        """Close all connections."""
        logger.info("Closing A2A client connections...")
        await self.httpx_client.aclose()
        self.remote_agents.clear()
        self._initialized = False
