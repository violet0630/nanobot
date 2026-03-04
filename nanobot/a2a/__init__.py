"""A2A (Agent-to-Agent) client integration for nanobot.

This module enables nanobot to act as an A2A protocol client, allowing it to
delegate requests to remote A2A-compliant agents based on their Agent Cards.
"""

from nanobot.a2a.client import A2AClientWrapper
from nanobot.a2a.registry import AgentCardRegistry

__all__ = ["A2AClientWrapper", "AgentCardRegistry"]
