"""A2A (Agent-to-Agent) protocol integration for nanobot.

This module allows nanobot instances to communicate with each other using the A2A protocol.
A nanobot can act as both a server (receiving requests from other nanobots) and a client
(sending requests to other nanobots).

Configuration is managed through nanobot's main config system (config/schema.py).
"""

from nanobot.a2a.server import A2AServer
from nanobot.a2a.client import A2AClientManager
from nanobot.a2a.agent_executor import NanobotAgentExecutor

__all__ = [
    "A2AServer",
    "A2AClientManager",
    "NanobotAgentExecutor",
]
