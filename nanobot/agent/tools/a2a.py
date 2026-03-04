"""A2A tool for delegating requests to remote A2A agents.

This tool allows the LLM to delegate requests to specialized remote
agents that advertise their capabilities via Agent Cards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class A2ATool(Tool):
    """Tool for delegating requests to remote A2A agents.

    When the LLM identifies that a user request matches an available
    A2A agent's skills, it can use this tool to delegate the request
    to that agent.
    """

    def __init__(self, client: Any, registry: Any):
        """Initialize the A2A tool.

        Args:
            client: A2AClientWrapper instance for sending messages.
            registry: AgentCardRegistry instance for querying available agents.
        """
        self._client = client
        self._registry = registry
        self._available_agents = list(registry.get_server_names())

    @property
    def name(self) -> str:
        """Tool name used in function calls."""
        return "delegate_to_a2a_agent"

    @property
    def description(self) -> str:
        """Description of what the tool does."""
        return (
            "Delegate a request to a remote A2A agent. Use this when the user's "
            "request requires specialized capabilities that match an available "
            "agent's skills. The agent will process the request and return the result."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": (
                        "The name of the A2A server to delegate to. "
                        f"Available servers: {', '.join(self._available_agents) if self._available_agents else 'none'}"
                    ),
                    "enum": self._available_agents if self._available_agents else [],
                },
                "message": {
                    "type": "string",
                    "description": "The message/request to send to the remote agent.",
                },
            },
            "required": ["server", "message"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool by sending a message to the remote A2A agent.

        Args:
            **kwargs: Tool parameters (server, message).

        Returns:
            The response from the remote agent.
        """
        server = kwargs.get("server")
        message = kwargs.get("message", "")

        if not server:
            return "Error: No server specified for A2A delegation"

        if not self._client.is_connected(server):
            available = ", ".join(self._available_agents)
            return f"Error: Server '{server}' is not connected. Available servers: {available}"

        if not message:
            return "Error: No message provided"

        logger.info("Delegating to A2A agent '{}': {}", server, message[:100])

        try:
            # Collect streaming response
            response_parts = []
            async for chunk in self._client.send_message(server, message):
                response_parts.append(chunk)

            response = "".join(response_parts)
            logger.info("A2A agent '{}' response: {}", server, response[:100])
            return response or "Agent returned an empty response"

        except Exception as e:
            error_msg = f"Error communicating with A2A agent '{server}': {e}"
            logger.error(error_msg)
            return error_msg

    def update_description(self) -> None:
        """Update the tool description with current available agents.

        Call this when the registry has been refreshed to update
        the available servers list in the tool description.
        """
        self._available_agents = list(self._registry.get_server_names())


class A2AQueryTool(Tool):
    """Tool for querying available A2A agents and their skills.

    This tool allows the LLM to discover what remote agents are available
    and what skills they offer.
    """

    def __init__(self, registry: Any):
        """Initialize the A2A query tool.

        Args:
            registry: AgentCardRegistry instance for querying available agents.
        """
        self._registry = registry

    @property
    def name(self) -> str:
        """Tool name used in function calls."""
        return "query_a2a_agents"

    @property
    def description(self) -> str:
        """Description of what the tool does."""
        return (
            "Query available A2A agents and their skills. "
            "Use this to discover what remote agents are available "
            "and what capabilities they offer."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "skill_tag": {
                    "type": "string",
                    "description": (
                        "Optional skill tag to filter agents by. "
                        "If provided, returns only agents that have skills matching this tag. "
                        "If not provided, returns all available agents."
                    ),
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool by querying available agents.

        Args:
            **kwargs: Tool parameters (skill_tag optional).

        Returns:
            Formatted information about available agents.
        """
        skill_tag = kwargs.get("skill_tag")

        if skill_tag:
            agents = self._registry.find_agents_by_tag(skill_tag)
            if not agents:
                return f"No A2A agents found with skill tag: {skill_tag}"

            result = f"A2A agents with skill tag '{skill_tag}':\n"
            for agent in agents:
                result += f"\n- {agent['server']}: {agent['name']}\n"
                result += f"  {agent['description']}\n"
                for skill in agent.get("skills", []):
                    if skill_tag.lower() in str(skill.get("tags", [])).lower():
                        result += f"  - {skill['name']}: {skill['description']}\n"
            return result
        else:
            return self._registry.format_for_llm() or "No A2A agents currently available."
