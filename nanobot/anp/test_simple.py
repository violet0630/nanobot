"""Simple test for ANP Agent Registry without external dependencies.

This demonstrates the correct pattern:
1. Registry starts with only nanobot (User Representative)
2. Other agents are registered dynamically
3. LLM must READ the registry to discover agents (NOT hardcoded)
"""

import json
from pathlib import Path


def test_agent_registry():
    """Test the Agent Registry functionality with dynamic discovery."""

    # Create registry path
    registry_path = Path.home() / ".nanobot" / "agents.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ANP Agent Registry - Dynamic Discovery Test")
    print("=" * 60)

    # Step 1: Initialize registry with ONLY nanobot
    # (Other agents are NOT pre-populated)
    nanobot_only = {
        "nanobot": {
            "@context": "https://www.w3.org/ns/did/v1",
            "protocolType": "ANP",
            "protocolVersion": "1.0.0",
            "type": "AgentDescription",
            "name": "Nanobot User Representative",
            "did": "did:wba:nanobot.local:agent:user-representative",
            "role": "User Representative",
            "description": "Nanobot is the user's personal AI assistant representing the user in the ANP network.",
            "capabilities": [
                "Human-in-the-loop authorization",
                "Verification code provision",
            ],
            "interfaces": [
                {
                    "type": "NaturalLanguageInterface",
                    "protocol": "ANP-NL",
                    "version": "1.0",
                },
                {
                    "type": "StructuredInterface",
                    "protocol": "openrpc",
                    "url": "http://localhost:8080/anp/rpc",
                }
            ],
        }
    }

    # Save initial registry
    with open(registry_path, "w") as f:
        json.dump({"agents": nanobot_only}, f, indent=2)

    print(f"\n1. Registry initialized at: {registry_path}")
    print("   Initially contains ONLY nanobot (User Representative)")
    print("\n   Registered Agents:")
    for name in nanobot_only.keys():
        print(f"   - {name}")

    # Step 2: Simulate dynamic registration of other agents
    # (In real scenario, these would be registered via discovery or admin action)

    print("\n" + "=" * 60)
    print("2. Simulating Dynamic Agent Registration")
    print("=" * 60)

    # Register smart-home-hub (could be discovered via ANP discovery protocol)
    smart_home_hub = {
        "@context": "https://www.w3.org/ns/did/v1",
        "protocolType": "ANP",
        "protocolVersion": "1.0.0",
        "type": "AgentDescription",
        "name": "Smart Home Hub",
        "did": "did:wba:smarthome.local:agent:hub",
        "role": "Security Supervisor",
        "description": "Provides security supervision and security upgrade services.",
        "capabilities": [
            "Security status monitoring",
            "Security upgrade verification",
            "Alert management"
        ],
        "interfaces": [
            {
                "type": "StructuredInterface",
                "protocol": "openrpc",
                "url": "http://smarthome.local:8081/anp/rpc",
                "description": "JSON-RPC 2.0 interface for security operations"
            }
        ],
    }

    # Register cloud-storage
    cloud_storage = {
        "@context": "https://www.w3.org/ns/did/v1",
        "protocolType": "ANP",
        "protocolVersion": "1.0.0",
        "type": "AgentDescription",
        "name": "Cloud Storage Agent",
        "did": "did:wba:cloudstorage.local:agent:storage",
        "role": "Data Storage Provider",
        "description": "Responsible for network data storage.",
        "capabilities": [
            "Secure data storage",
            "Log management",
            "Credential storage"
        ],
        "interfaces": [
            {
                "type": "StructuredInterface",
                "protocol": "openrpc",
                "url": "http://cloudstorage.local:8082/anp/rpc",
                "description": "JSON-RPC 2.0 interface for storage operations"
            }
        ],
    }

    # Update registry with dynamically discovered agents
    nanobot_only["smart-home-hub"] = smart_home_hub
    nanobot_only["cloud-storage"] = cloud_storage

    with open(registry_path, "w") as f:
        json.dump({"agents": nanobot_only}, f, indent=2)

    print("\n   Agents registered (dynamically):")
    print("   - smart-home-hub (Security Supervisor)")
    print("   - cloud-storage (Data Storage Provider)")

    # Step 3: Show the correct LLM workflow
    print("\n" + "=" * 60)
    print("3. Correct LLM Workflow (NO hardcoded agent names)")
    print("=" * 60)

    print("""
When user says: "Check security status"

LLM should:
1. READ ~/.nanobot/agents.json
2. PARSE each agent's role and capabilities
3. FIND agent with "security" capability
4. CALL that agent

LLM should NOT:
- Have smart-home-hub name hardcoded
- Assume which agents exist
- Skip reading the registry
    """)

    print("\n" + "=" * 60)
    print("4. Example: Reading Registry to Find Agent")
    print("=" * 60)

    print(f"\nReading {registry_path}...")
    with open(registry_path, "r") as f:
        registry = json.load(f)

    print("\n   Available agents (from registry):")
    for name, agent in registry["agents"].items():
        role = agent.get("role", "Unknown")
        capabilities = agent.get("capabilities", [])
        print(f"\n   Agent: {name}")
        print(f"     Role: {role}")
        print(f"     Capabilities: {', '.join(capabilities)}")

    print("\n   Finding agent for 'security' task...")
    for name, agent in registry["agents"].items():
        capabilities = agent.get("capabilities", [])
        if any("security" in cap.lower() for cap in capabilities):
            print(f"\n   → Found: {name}")
            print(f"     Role: {agent.get('role')}")
            print(f"     Would call: anp_call(agent_name='{name}', method='getSecurityStatus')")

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    print("""
KEY POINT: The registry is DYNAMIC. Agents can be added/removed at any time.
The LLM must ALWAYS read the registry to discover available agents,
NOT rely on hardcoded agent names in the skill prompt.
    """)

    return True


if __name__ == "__main__":
    test_agent_registry()
