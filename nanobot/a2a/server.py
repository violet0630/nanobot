"""A2A Server for nanobot.

This module provides the A2A server functionality, allowing nanobot to receive
requests from other nanobot instances.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from loguru import logger

try:
    import httpx
    import uvicorn
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import (
        AgentCapabilities,
        AgentCard,
        AgentSkill,
    )
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    httpx = None  # type: ignore
    uvicorn = None  # type: ignore

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.schema import A2AConfig


class A2AServer:
    """A2A server for nanobot.

    This server allows nanobot to receive requests from other nanobot instances
    using the A2A protocol.
    """

    def __init__(
        self,
        agent_loop: "AgentLoop",
        config: "A2AConfig",
    ):
        if not A2A_AVAILABLE:
            raise ImportError(
                "a2a-python is not installed. "
                "Install it with: pip install a2a-python"
            )

        self.agent_loop = agent_loop
        self.config = config
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None
        self._app = None

    def _create_agent_card(self) -> AgentCard:
        """Create the AgentCard for this nanobot."""
        # Basic skill - this will be dynamically updated based on nanobot's tools
        basic_skill = AgentSkill(
            id="chat",
            name="Chat Assistant",
            description=f"{self.config.agent_description}",
            tags=["chat", "assistant"],
            examples=["Hello", "How are you?"],
        )

        return AgentCard(
            name=self.config.agent_name,
            description=self.config.agent_description,
            url=f"http://{self.config.host}:{self.config.port}/",
            version=self.config.agent_version,
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[basic_skill],
            supports_authenticated_extended_card=self.config.require_auth_for_extended,
        )

    def _build_app(self) -> A2AStarletteApplication:
        """Build the A2A Starlette application."""
        from nanobot.a2a.agent_executor import NanobotAgentExecutor

        agent_card = self._create_agent_card()
        agent_executor = NanobotAgentExecutor(self.agent_loop)
        task_store = InMemoryTaskStore()
        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=task_store,
        )

        app = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )
        return app

    async def start(self) -> None:
        """Start the A2A server."""
        if self._server is not None:
            logger.warning("A2A server is already running")
            return

        logger.info(
            "Starting A2A server on {}:{}",
            self.config.host,
            self.config.port,
        )

        # Build the application
        self._app = self._build_app()

        # Configure uvicorn
        config = uvicorn.Config(
            app=self._app.build(),
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )

        # Create and start the server
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())

        logger.info(
            "A2A server started at http://{}:{}",
            self.config.host,
            self.config.port,
        )

    async def stop(self) -> None:
        """Stop the A2A server."""
        if self._server is None:
            logger.warning("A2A server is not running")
            return

        logger.info("Stopping A2A server...")
        self._server.should_exit = True

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("A2A server stop timed out, cancelling task")
                if self._task and not self._task.done():
                    self._task.cancel()

        self._server = None
        self._task = None
        self._app = None
        logger.info("A2A server stopped")

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None and self._task is not None

    @property
    def url(self) -> str:
        """Get the URL of this A2A server."""
        return f"http://{self.config.host}:{self.config.port}/"
