"""ANP skill implementation for nanobot.

This module provides tools for:
- Calling external ANP agents
- Listing available agents (from registry)
- Getting agent information (from registry)

IMPORTANT: This implementation is generic and works with ANY ANP-compliant agent.
No hardcoded agent names or assumptions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.registry import Tool
from nanobot.anp.client import ANPClient
from nanobot.anp.agent_registry import AgentRegistry
from nanobot.anp.auth import DIDWBAAuth


def get_context() -> dict[str, Any]:
    """Load the ANP skill context."""
    skill_dir = Path(__file__).parent
    context_path = skill_dir / "context.json"

    if context_path.exists():
        with open(context_path, "r") as f:
            return json.load(f)

    # Default context
    return {
        "nanobot_did": "did:wba:nanobot.local:agent:user-representative",
        "anp_server_port": 8080,
        "anp_enabled": True,
    }


def save_context(context: dict[str, Any]) -> None:
    """Save the ANP skill context."""
    skill_dir = Path(__file__).parent
    context_path = skill_dir / "context.json"

    with open(context_path, "w") as f:
        json.dump(context, f, indent=2)


class ANPCallTool(Tool):
    """Tool for calling remote ANP agents.

    Generic implementation - works with ANY ANP-compliant agent.
    """

    def __init__(self):
        super().__init__()
        self._client: ANPClient | None = None
        self._auth: DIDWBAAuth | None = None
        self._context = get_context()

        # Initialize ANP client if enabled
        if self._context.get("anp_enabled", True):
            self._init_client()

    @property
    def name(self) -> str:
        return "anp_call"

    @property
    def description(self) -> str:
        return (
            "Call a method on a remote ANP (Agent Network Protocol) agent. "
            "Use this when you need to interact with other agents in the network. "
            "First, read ~/.nanobot/agents.json to discover available agents."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the target agent (from registry, e.g., 'smart-home-hub'). Read ~/.nanobot/agents.json first.",
                },
                "method": {
                    "type": "string",
                    "description": "Method name to call on the agent (check agent's interface definition)",
                },
                "params": {
                    "type": "string",
                    "description": "JSON string of parameters for the method",
                },
            },
            "required": ["agent_name", "method"],
        }

    def _init_client(self) -> None:
        """Initialize the ANP client with authentication."""
        try:
            # Get or create DID and private key
            private_key_path = Path.home() / ".nanobot" / "anp_private_key.pem"

            if private_key_path.exists():
                with open(private_key_path, "r") as f:
                    private_key_pem = f.read()
            else:
                private_key_pem = None

            self._auth = DIDWBAAuth(
                did=self._context.get("nanobot_did", "did:wba:nanobot.local:agent:user-representative"),
                private_key_pem=private_key_pem,
                key_type="secp256r1",
            )

            # Save the private key if newly generated
            if private_key_pem is None:
                private_key_path.parent.mkdir(parents=True, exist_ok=True)
                with open(private_key_path, "w") as f:
                    f.write(self._auth.get_private_key_pem())

            self._client = ANPClient(auth=self._auth)
            logger.info("ANP client initialized")

        except Exception as e:
            logger.warning("Failed to initialize ANP client: {}", e)

    async def execute(self, **kwargs) -> str:
        """
        Execute the ANP call.

        Args:
            agent_name: Name of the target agent (must exist in registry)
            method: Method name to call
            params: Parameters for the method (JSON string or dict)

        Returns:
            Result from the remote agent
        """
        if not self._client:
            return "ANP client is not available. Check configuration."

        agent_name = kwargs.get("agent_name")
        method = kwargs.get("method")
        params_arg = kwargs.get("params", "{}")

        if not agent_name or not method:
            return "Error: agent_name and method are required"

        try:
            # Parse params
            if isinstance(params_arg, str):
                params = json.loads(params_arg)
            else:
                params = params_arg

            # Make the call
            result = await self._client.call(
                agent_name=agent_name,
                method=method,
                params=params,
            )

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.exception("Error in ANP call")
            return f"Error calling {agent_name}.{method}: {e}"


class ANPListAgentsTool(Tool):
    """Tool for listing available ANP agents from the registry.

    This tool simply reads the registry file - NO hardcoded agent names.
    """

    def __init__(self):
        super().__init__()
        self._registry = AgentRegistry()

    @property
    def name(self) -> str:
        return "anp_list_agents"

    @property
    def description(self) -> str:
        return (
            "List all available ANP agents from the agent registry at ~/.nanobot/agents.json. "
            "Use this to discover what agents are available before calling anp_call."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs) -> str:
        """List all registered agents by reading the registry file."""
        agents = self._registry.list_all()

        if not agents:
            return "No agents found in the registry at ~/.nanobot/agents.json"

        result = ["Available ANP Agents (from ~/.nanobot/agents.json):"]
        for name, agent in agents.items():
            role = agent.get("role", "Unknown")
            did = agent.get("did", "No DID")
            capabilities = agent.get("capabilities", [])
            interfaces = agent.get("interfaces", [])

            result.append(f"\n- {name}")
            result.append(f"  Role: {role}")
            result.append(f"  DID: {did}")
            if capabilities:
                result.append(f"  Capabilities: {', '.join(capabilities)}")
            if interfaces:
                result.append(f"  Interfaces: {len(interfaces)} interface(s) defined")

        return "\n".join(result)


class ANPGetAgentInfoTool(Tool):
    """Tool for getting detailed information about a specific agent.

    Reads from the registry - NO hardcoded information.
    """

    def __init__(self):
        super().__init__()
        self._registry = AgentRegistry()

    @property
    def name(self) -> str:
        return "anp_get_agent_info"

    @property
    def description(self) -> str:
        return (
            "Get detailed information about a specific ANP agent from the registry. "
            "Use this to understand an agent's capabilities and interfaces before calling it."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to get information about",
                },
            },
            "required": ["agent_name"],
        }

    async def execute(self, **kwargs) -> str:
        """Get agent information from the registry."""
        agent_name = kwargs.get("agent_name")

        if not agent_name:
            return "Error: agent_name is required"

        agent = self._registry.get(agent_name)

        if not agent:
            return f"Agent '{agent_name}' not found in registry at ~/.nanobot/agents.json"

        # Format the agent information nicely
        result = [f"Agent: {agent_name}"]
        result.append(f"Name: {agent.get('name', 'N/A')}")
        result.append(f"Role: {agent.get('role', 'N/A')}")
        result.append(f"DID: {agent.get('did', 'N/A')}")
        result.append(f"Description: {agent.get('description', 'N/A')}")

        capabilities = agent.get("capabilities", [])
        if capabilities:
            result.append(f"\nCapabilities:")
            if isinstance(capabilities, dict):
                for cap_name, cap_info in capabilities.items():
                    cap_type = cap_info.get("type", "") if isinstance(cap_info, dict) else ""
                    cap_desc = cap_info.get("description", "") if isinstance(cap_info, dict) else str(cap_info)
                    result.append(f"  - {cap_name}: {cap_type} - {cap_desc}")
            elif isinstance(capabilities, list):
                for cap in capabilities:
                    result.append(f"  - {cap}")

        interfaces = agent.get("interfaces", [])
        if interfaces:
            result.append(f"\nInterfaces:")
            for iface in interfaces:
                iface_type = iface.get("type", "Unknown")
                protocol = iface.get("protocol", "Unknown")
                url = iface.get("url", "N/A")
                description = iface.get("description", "N/A")
                result.append(f"  - {iface_type} ({protocol})")
                result.append(f"    URL: {url}")
                result.append(f"    Description: {description}")

        # IMPORTANT: Show available methods with their descriptions
        methods = agent.get("methods", {})
        if methods:
            result.append(f"\n{'='*50}")
            result.append(f"AVAILABLE METHODS (Use these exact names!):")
            result.append(f"{'='*50}")
            for method_name, method_info in methods.items():
                method_desc = method_info.get("description", "No description") if isinstance(method_info, dict) else str(method_info)
                result.append(f"\n  {method_name}:")
                result.append(f"    Description: {method_desc}")
                if isinstance(method_info, dict) and "params" in method_info:
                    params = method_info["params"]
                    if params:
                        result.append(f"    Parameters:")
                        if isinstance(params, dict):
                            for param_name, param_desc in params.items():
                                result.append(f"      - {param_name}: {param_desc}")
                        else:
                            result.append(f"      {params}")
        else:
            result.append(f"\nNote: No methods defined in registry. Check agent documentation.")

        return "\n".join(result)


def register_tools(tool_registry) -> None:
    """Register ANP tools with the tool registry."""
    tool_registry.register(ANPCallTool())
    tool_registry.register(ANPListAgentsTool())
    tool_registry.register(ANPGetAgentInfoTool())
    logger.info("ANP tools registered (generic, no hardcoded agents)")
