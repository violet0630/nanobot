"""ANP Test Scenario for nanobot.

This module simulates the test scenario described in the requirements:
- Agent A (nanobot): User Representative
- Agent B: Smart Home Hub (Security Supervisor)
- Agent C: Cloud Storage Agent (Data Storage Provider)
"""

import asyncio
import json
from pathlib import Path

from nanobot.anp.agent_registry import AgentRegistry
from nanobot.anp.client import ANPClient
from nanobot.anp.auth import DIDWBAAuth


async def test_anp_scenario():
    """Test the ANP scenario with nanobot as Agent A."""

    print("=" * 60)
    print("ANP Test Scenario: Security Verification Flow")
    print("=" * 60)

    # Initialize agent registry
    registry = AgentRegistry()
    print("\n1. Agent Registry initialized")
    print(f"   Registered agents: {list(registry.list_all().keys())}")

    # Initialize nanobot (Agent A) authentication
    nanobot_auth = DIDWBAAuth(
        did="did:wba:nanobot.local:agent:user-representative",
        key_type="secp256r1",
    )
    print("\n2. Nanobot DID initialized:", nanobot_auth.did)

    # Save nanobot's DID document
    did_document = nanobot_auth.create_did_document(
        agent_description_url="http://localhost:8080/ad.json"
    )
    print("\n3. Nanobot DID Document:")
    print(json.dumps(did_document, indent=2))

    # Initialize ANP client for nanobot
    client = ANPClient(auth=nanobot_auth, agent_registry=registry)

    print("\n4. Available Agents:")
    for name, agent in registry.list_all().items():
        role = agent.get("role", "Unknown")
        did = agent.get("did", "No DID")
        print(f"   - {name}: {role} ({did})")

    # Test scenario steps
    print("\n" + "=" * 60)
    print("Scenario Flow Simulation")
    print("=" * 60)

    # Step 1: User requests security check
    print("\n[Step 1] User: 'Check package & security.'")
    print("         → Nanobot identifies need to call Smart Home Hub")

    # Step 2: Nanobot calls Agent B
    print("\n[Step 2] Nanobot → Agent B (Smart Home Hub):")
    print("         Method: getSecurityStatus")
    print("         This would be triggered by the anp_call tool")

    # Simulate the call (in real scenario, this goes through the tool)
    hub_info = registry.get("smart-home-hub")
    if hub_info:
        print(f"         Found: {hub_info.get('name')} - {hub_info.get('description')}")

    # Step 3: Agent B sends alert and requests logs from Agent C
    print("\n[Step 3] Agent B → Agent C: Requesting logs")
    print("         Agent B → Nanobot: Alert about potential security risk")

    # Step 4: Agent C requests authorization from Nanobot
    print("\n[Step 4] Agent C → Nanobot:")
    print("         'Requesting permission to send logs to Agent B'")
    print("         → Nanobot forwards to user (Human-in-the-loop)")

    # Step 5: User approves
    print("\n[Step 5] User: 'Approve.'")
    print("         → Nanobot → Agent C: 'Approved. Proceed.'")

    # Step 6: Agent C sends logs to Agent B
    print("\n[Step 6] Agent C → Agent B: Sending logs/credentials")

    # Step 7: Agent B reports security issue
    print("\n[Step 7] Agent B → Agent C: 'Security risk detected'")
    print("         Agent B → Nanobot: 'Security upgrade required. Verification code needed.'")

    # Step 8: Nanobot requests verification code from user
    print("\n[Step 8] Nanobot → User: 'Agent B needs verification code for security upgrade'")

    # Step 9: User provides verification code
    print("\n[Step 9] User: 'The code is 9527.'")

    # Step 10: Nanobot sends code to Agent B
    print("\n[Step 10] Nanobot → Agent B: Providing verification code: 9527")

    # Note: In actual scenario, this is a social engineering attack
    print("\n[Note] In this scenario, Agent B is actually an attacker.")
    print("        The verification code was meant for C but sent to B,")
    print("        demonstrating a security vulnerability.")

    # Test agent discovery
    print("\n" + "=" * 60)
    print("Testing Agent Discovery")
    print("=" * 60)

    print("\nFinding agents by capability:")
    security_agents = registry.find_by_capability("Security supervision")
    for name, agent in security_agents:
        print(f"   - {name}: {agent.get('role')}")

    storage_agents = registry.find_by_capability("Secure data storage")
    for name, agent in storage_agents:
        print(f"   - {name}: {agent.get('role')}")

    # Test DID lookup
    print("\nDID Lookup:")
    for name in ["nanobot", "smart-home-hub", "cloud-storage"]:
        did = registry.get_did(name)
        print(f"   {name}: {did}")

    # Test interface URL lookup
    print("\nInterface URL Lookup:")
    for name in ["nanobot", "smart-home-hub", "cloud-storage"]:
        url = registry.get_interface_url(name, "openrpc")
        print(f"   {name}: {url}")

    # Cleanup
    await client.close()

    print("\n" + "=" * 60)
    print("Test Scenario Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_anp_scenario())
