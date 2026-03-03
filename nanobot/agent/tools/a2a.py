"""A2A (Agent-to-Agent) tool for nanobot.

This tool allows nanobot to call other nanobot instances using the A2A protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.a2a.client import A2AClientManager


class A2ACallTool(Tool):
    """Tool for calling remote nanobot agents via A2A protocol.

    This tool enables LLMs to delegate tasks to other specialized nanobot instances.
    """

    name = "a2a_call"
    description = "Call a remote nanobot agent for specialized assistance. " \
                  "Use this when the current task requires expertise from another agent. " \
                  "Available agents can be listed using the a2a_list_agents tool."

    def __init__(self, client_manager: "A2AClientManager"):
        self.client_manager = client_manager

    async def call(self, agent_name: str, message: str) -> str:
        """Send a message to a remote agent.

        Args:
            agent_name: Name of the remote agent to call
            message: Message to send to the remote agent

        Returns:
            Response from the remote agent

        Raises:
            ValueError: If the agent is not found or the call fails
        """
        logger.info("A2A call to agent '{}' with message: {}", agent_name, message[:100])

        try:
            response = await self.client_manager.send_message(
                agent_name=agent_name,
                message=message,
            )
            logger.info("A2A response from '{}': {}", agent_name, str(response)[:100])
            return str(response)
        except Exception as e:
            logger.error("A2A call to '{}' failed: {}", agent_name, e)
            raise ValueError(f"Failed to call agent '{agent_name}': {e}")

    def get_definition(self) -> dict:
        """Get the tool definition for LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the remote agent to call",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message to send to the remote agent",
                        },
                    },
                    "required": ["agent_name", "message"],
                },
            },
        }


class A2AListAgentsTool(Tool):
    """Tool for listing available remote nanobot agents."""

    name = "a2a_list_agents"
    description = "List all available remote nanobot agents that can be called. " \
                  "Returns information about each agent including their name, URL, and description."

    def __init__(self, client_manager: "A2AClientManager"):
        self.client_manager = client_manager

    async def call(self) -> list[dict]:
        """List all available remote agents.

        Returns:
            List of agent information dictionaries
        """
        agents = self.client_manager.list_remote_agents()
        logger.info("A2A listing {} remote agent(s)", len(agents))
        return agents

    def get_definition(self) -> dict:
        """Get the tool definition for LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
