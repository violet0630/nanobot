"""Agent discovery and registry, with OpenANP ad.json support."""

import json
from pathlib import Path
from typing import Optional


class AgentRegistry:
    """Registry for managing agent information, supports ad.json discovery."""

    def __init__(self, registry_path: str, self_did: str = ""):
        """Initialize agent registry.

        Args:
            registry_path: Path to agent_registry.json
            self_did: This agent's DID
        """
        self.registry_path = Path(registry_path).expanduser()
        self.self_did = self_did
        self.agents = self._load_registry()

    def _load_registry(self) -> dict:
        """Load agent registry from JSON file."""
        if not self.registry_path.exists():
            return {}

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {agent["did"]: agent for agent in data.get("agents", [])}
        except Exception:
            return {}

    def get_agent_info(self, did: str) -> Optional[dict]:
        """Get agent information by DID."""
        return self.agents.get(did)

    def list_all_agents(self) -> list[dict]:
        """List all registered agents."""
        return list(self.agents.values())

    def get_self_did(self) -> str:
        """Get this agent's DID."""
        return self.self_did

    def get_agents_summary(self) -> str:
        """Get formatted summary of all agents for LLM prompt."""
        if not self.agents:
            return "当前网络中没有其他 agent。"

        lines = ["# Agent 网络注册表\n"]
        for agent in self.agents.values():
            lines.append(f"- **{agent['name']}** (`{agent['did']}`)")
            lines.append(f"  描述: {agent['description']}")
            if agent.get("ad_url"):
                lines.append(f"  发现地址: {agent['ad_url']}")
            if agent.get("capabilities"):
                lines.append(f"  能力: {', '.join(agent['capabilities'])}")
            lines.append("")

        return "\n".join(lines)
