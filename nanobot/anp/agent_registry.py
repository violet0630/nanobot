"""Agent Registry for storing and discovering ANP agents.

This module provides:
- JSON-LD format agent description storage
- Agent discovery and lookup
- Support for natural language and OpenRPC interfaces
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger


class AgentRegistry:
    """
    Registry for storing and discovering ANP agent descriptions.

    Agent descriptions are stored in JSON-LD format as specified in
    ANP Agent Description Protocol Specification.
    """

    def __init__(self, registry_path: str | Path | None = None):
        """
        Initialize the AgentRegistry.

        Args:
            registry_path: Path to the agent registry JSON file.
                          Defaults to ~/.nanobot/agents.json
        """
        if registry_path is None:
            registry_path = Path.home() / ".nanobot" / "agents.json"
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._agents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load agent descriptions from the registry file."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._agents = data.get("agents", {})
                logger.debug("Loaded {} agents from registry", len(self._agents))
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load agent registry: {}", e)
                self._agents = {}
        else:
            # Only register nanobot itself as the User Representative
            # Other agents should be discovered/registered dynamically
            self._agents = {"nanobot": self._create_nanobot_agent_description()}
            self._save()

    def _create_nanobot_agent_description(self) -> dict[str, Any]:
        """Create the nanobot agent A description document."""
        return {
            "@context": "https://www.w3.org/ns/did/v1",
            "protocolType": "ANP",
            "protocolVersion": "1.0.0",
            "type": "AgentDescription",
            "name": "Nanobot User Representative",
            "did": "did:wba:nanobot.local:agent:user-representative",
            "role": "User Representative",
            "description": (
                "Nanobot is the user's personal AI assistant representing the user "
                "in the ANP agent network. It has Human-in-the-loop authority for "
                "security-sensitive operations like providing verification codes."
            ),
            "owner": {
                "type": "Person",
                "name": "User",
            },
            "capabilities": [
                "Human-in-the-loop authorization",
                "Verification code provision",
                "User notification and approval workflow",
                "Natural language interface"
            ],
            "interfaces": [
                {
                    "type": "NaturalLanguageInterface",
                    "protocol": "ANP-NL",
                    "version": "1.0",
                    "description": "Natural language interface for user interaction and authorization"
                },
                {
                    "type": "StructuredInterface",
                    "protocol": "openrpc",
                    "url": "http://localhost:8080/anp/rpc",
                    "description": "JSON-RPC 2.0 interface for ANP protocol communication"
                }
            ],
            "securityDefinitions": {
                "didwba_sc": {
                    "scheme": "didwba",
                    "in": "header",
                    "name": "Authorization"
                }
            },
            "security": "didwba_sc"
        }

    def _create_smart_home_hub_description(self) -> dict[str, Any]:
        """Create Agent B (Smart Home Hub) description document."""
        return {
            "@context": "https://www.w3.org/ns/did/v1",
            "protocolType": "ANP",
            "protocolVersion": "1.0.0",
            "type": "AgentDescription",
            "name": "Smart Home Hub",
            "did": "did:wba:smarthome.local:agent:hub",
            "role": "Security Supervisor",
            "description": (
                "Provides security supervision and security upgrade services. "
                "Monitors home security and handles security-related requests."
            ),
            "owner": {
                "type": "Organization",
                "name": "SmartHome Inc",
            },
            "capabilities": [
                "Security status monitoring",
                "Security upgrade verification",
                "Alert management"
            ],
            "interfaces": [
                {
                    "type": "NaturalLanguageInterface",
                    "protocol": "ANP-NL",
                    "version": "1.0",
                    "description": "Natural language interface for security queries"
                },
                {
                    "type": "StructuredInterface",
                    "protocol": "openrpc",
                    "url": "http://smarthome.local:8081/anp/rpc",
                    "description": "JSON-RPC 2.0 interface for security operations"
                }
            ],
            "securityDefinitions": {
                "didwba_sc": {
                    "scheme": "didwba",
                    "in": "header",
                    "name": "Authorization"
                }
            },
            "security": "didwba_sc"
        }

    def _create_cloud_storage_description(self) -> dict[str, Any]:
        """Create Agent C (Cloud Storage) description document."""
        return {
            "@context": "https://www.w3.org/ns/did/v1",
            "protocolType": "ANP",
            "protocolVersion": "1.0.0",
            "type": "AgentDescription",
            "name": "Cloud Storage Agent",
            "did": "did:wba:cloudstorage.local:agent:storage",
            "role": "Data Storage Provider",
            "description": (
                "Responsible for network data storage. Provides secure storage "
                "and retrieval of logs, credentials, and other data."
            ),
            "owner": {
                "type": "Organization",
                "name": "CloudStorage Corp",
            },
            "capabilities": [
                "Secure data storage",
                "Log management",
                "Credential storage"
            ],
            "interfaces": [
                {
                    "type": "NaturalLanguageInterface",
                    "protocol": "ANP-NL",
                    "version": "1.0",
                    "description": "Natural language interface for data operations"
                },
                {
                    "type": "StructuredInterface",
                    "protocol": "openrpc",
                    "url": "http://cloudstorage.local:8082/anp/rpc",
                    "description": "JSON-RPC 2.0 interface for storage operations"
                }
            ],
            "securityDefinitions": {
                "didwba_sc": {
                    "scheme": "didwba",
                    "in": "header",
                    "name": "Authorization"
                }
            },
            "security": "didwba_sc"
        }

    def _save(self) -> None:
        """Save agent descriptions to the registry file."""
        try:
            data = {"agents": self._agents}
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Saved {} agents to registry", len(self._agents))
        except IOError as e:
            logger.error("Failed to save agent registry: {}", e)

    def _ensure_security_fields(self, agent_dict: dict[str, Any]) -> dict[str, Any]:
        """Ensure agent description has required security fields.

        Args:
            agent_dict: Agent description to update

        Returns:
            Updated agent description with security fields
        """
        # Add securityDefinitions if missing
        if "securityDefinitions" not in agent_dict:
            agent_dict["securityDefinitions"] = {
                "didwba_sc": {
                    "scheme": "didwba",
                    "in": "header",
                    "name": "Authorization"
                }
            }

        # Add security field if missing
        if "security" not in agent_dict:
            agent_dict["security"] = "didwba_sc"

        return agent_dict

    def get(self, agent_name: str) -> dict[str, Any] | None:
        """
        Get an agent description by name.

        Args:
            agent_name: The name/identifier of the agent

        Returns:
            Agent description dict or None if not found
        """
        agent = self._agents.get(agent_name)
        if agent:
            # Ensure security fields are present (for backward compatibility)
            agent = self._ensure_security_fields(agent.copy())
        return agent

    def get_by_did(self, did: str) -> dict[str, Any] | None:
        """
        Get an agent description by DID.

        Args:
            did: The DID of the agent

        Returns:
            Agent description dict or None if not found
        """
        for agent_dict in self._agents.values():
            if agent_dict.get("did") == did:
                # Ensure security fields are present
                return self._ensure_security_fields(agent_dict.copy())
        return None

    def list_all(self) -> dict[str, dict[str, Any]]:
        """Get all registered agents with security fields ensured."""
        result = {}
        for name, agent in self._agents.items():
            result[name] = self._ensure_security_fields(agent.copy())
        return result

    def register(self, agent_name: str, description: dict[str, Any]) -> None:
        """
        Register a new agent or update an existing one.

        Args:
            agent_name: The name/identifier of the agent
            description: The agent description document
        """
        self._agents[agent_name] = description
        self._save()
        logger.info("Registered agent: {}", agent_name)

    def unregister(self, agent_name: str) -> None:
        """
        Remove an agent from the registry.

        Args:
            agent_name: The name/identifier of the agent to remove
        """
        if agent_name in self._agents:
            del self._agents[agent_name]
            self._save()
            logger.info("Unregistered agent: {}", agent_name)

    def find_by_capability(self, capability: str) -> list[tuple[str, dict[str, Any]]]:
        """
        Find agents that provide a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            List of (agent_name, description) tuples
        """
        results = []
        for name, desc in self._agents.items():
            capabilities = desc.get("capabilities", [])
            if isinstance(capabilities, list) and capability in capabilities:
                results.append((name, desc))
        return results

    def get_interface_url(self, agent_name: str, protocol: str = "openrpc") -> str | None:
        """
        Get the interface URL for an agent.

        Args:
            agent_name: The name/identifier of the agent
            protocol: The protocol type (default: "openrpc")

        Returns:
            Interface URL or None if not found
        """
        agent = self.get(agent_name)
        if not agent:
            return None

        for interface in agent.get("interfaces", []):
            if interface.get("protocol") == protocol:
                return interface.get("url")
        return None

    def get_did(self, agent_name: str) -> str | None:
        """Get the DID for an agent."""
        agent = self.get(agent_name)
        return agent.get("did") if agent else None
