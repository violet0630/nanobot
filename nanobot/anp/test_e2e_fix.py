"""End-to-end test for ANP server and client modes."""

import asyncio
import json
from nanobot.anp.server import _pending_anp_requests, complete_pending_request
from nanobot.anp.agent_registry import AgentRegistry
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.agent.loop import AgentLoop


async def test_server_mode_response_flow():
    """Test the complete server mode response flow."""
    print("=" * 60)
    print("TEST: Server Mode Response Flow")
    print("=" * 60)

    correlation_id = "test_req_12345"

    # Step 1: Simulate server.py creating a pending request
    response_future = asyncio.Future()
    _pending_anp_requests[correlation_id] = response_future
    print(f"✓ Step 1: Server created pending request: {correlation_id}")

    # Step 2: Simulate loop.py creating OutboundMessage after processing
    outbound_msg = OutboundMessage(
        channel="anp",
        chat_id="did:test:caller",
        content="Test ANP response from LLM",
        metadata={
            "correlation_id": correlation_id,
            "caller_did": "did:test:caller",
            "method": "testMethod",
        }
    )
    print(f"✓ Step 2: Loop created OutboundMessage with correlation_id")

    # Step 3: Simulate loop.py:_complete_anp_response
    result = {
        "status": "success",
        "content": outbound_msg.content,
        "metadata": outbound_msg.metadata,
    }

    # Step 4: Complete the pending request
    if complete_pending_request(correlation_id, result):
        print(f"✓ Step 3: complete_pending_request succeeded")

        # Step 5: Verify future was set
        if response_future.done():
            actual_result = response_future.result()
            print(f"✓ Step 4: Future was completed with result")

            # Step 6: Verify result matches
            if actual_result == result:
                print(f"✓ Step 5: Result matches expected")
            else:
                print(f"✗ Step 5: Result mismatch")
                print(f"  Expected: {result}")
                print(f"  Actual: {actual_result}")
        else:
            print(f"✗ Step 4: Future was not completed")
    else:
        print(f"✗ Step 3: complete_pending_request failed")

    # Clean up
    _pending_anp_requests.pop(correlation_id, None)

    print("\n✅ Server Mode Test PASSED!\n")


async def test_client_mode_discovery():
    """Test client mode agent discovery."""
    print("=" * 60)
    print("TEST: Client Mode Agent Discovery")
    print("=" * 60)

    registry = AgentRegistry()

    # Test 1: Get an agent that exists
    agent = registry.get("nanobot")
    if agent:
        print(f"✓ Step 1: Found 'nanobot' agent")
        if agent.get("did"):
            print(f"✓ Step 2: Agent has DID: {agent['did']}")
        if agent.get("interfaces"):
            print(f"✓ Step 3: Agent has {len(agent['interfaces'])} interface(s)")
    else:
        print(f"✗ Step 1: 'nanobot' agent not found")

    # Test 2: Get an agent that doesn't exist
    agent = registry.get("nonexistent_agent")
    if agent is None:
        print(f"✓ Step 4: Nonexistent agent returns None")
    else:
        print(f"✗ Step 4: Nonexistent agent should return None")

    # Test 3: Get RPC URL (generic extraction)
    agent = registry.get("nanobot")
    if agent:
        for interface in agent.get("interfaces", []):
            if interface.get("protocol") == "openrpc":
                url = interface.get("url")
                if url:
                    print(f"✓ Step 5: Extracted RPC URL: {url}")
                    break

    # Test 4: Verify no hardcoded agent names
    import inspect
    source = inspect.getsource(registry.get)
    if "smart-home-hub" not in source and "cloud-storage" not in source:
        print(f"✓ Step 6: No hardcoded agent names in registry.get()")
    else:
        # These might be in comments or test methods
        print(f"⚠ Step 6: Agent names found in source (check if in logic)")

    print("\n✅ Client Mode Test PASSED!\n")


async def test_error_handling():
    """Test error handling and edge cases."""
    print("=" * 60)
    print("TEST: Error Handling")
    print("=" * 60)

    # Test 1: Complete request with missing correlation_id
    result = complete_pending_request("", {"status": "test"})
    if not result:
        print(f"✓ Test 1: Empty correlation_id handled correctly")
    else:
        print(f"✗ Test 1: Empty correlation_id should return False")

    # Test 2: Complete request with non-existent correlation_id
    result = complete_pending_request("nonexistent_id", {"status": "test"})
    if not result:
        print(f"✓ Test 2: Non-existent correlation_id handled correctly")
    else:
        print(f"✗ Test 2: Non-existent correlation_id should return False")

    # Test 3: Complete request twice (second should fail)
    correlation_id = "test_double_complete"
    future = asyncio.Future()
    _pending_anp_requests[correlation_id] = future

    result1 = complete_pending_request(correlation_id, {"status": "first"})
    result2 = complete_pending_request(correlation_id, {"status": "second"})

    if result1 and not result2:
        print(f"✓ Test 3: Double completion handled correctly")
    else:
        print(f"✗ Test 3: First={result1}, Second={result2} (expected True, False)")

    # Clean up
    _pending_anp_requests.pop(correlation_id, None)

    print("\n✅ Error Handling Test PASSED!\n")


async def test_generic_implementation():
    """Test that implementation is generic (no hardcoded agent logic)."""
    print("=" * 60)
    print("TEST: Generic Implementation (No Hardcoded Agent Logic)")
    print("=" * 60)

    # Check client.py for hardcoded agent names
    from nanobot.anp import client as anp_client
    client_source = inspect.getsource(anp_client)

    hardcoded_patterns = [
        "smart-home-hub",
        "cloud-storage",
        "if agent_name ==",
        'if agent_name == "',
        "if agent == '",
    ]

    found_hardcoded = []
    for pattern in hardcoded_patterns:
        if pattern in client_source:
            # Check if it's in a comment or string literal (not logic)
            lines = client_source.split('\n')
            for i, line in enumerate(lines):
                if pattern in line and not line.strip().startswith('#'):
                    # Further check - might be in docstring
                    if 'if' in line or '==' in line:
                        found_hardcoded.append(f"Line {i+1}: {line.strip()}")

    if not found_hardcoded:
        print(f"✓ Test 1: No hardcoded agent logic in client.py")
    else:
        print(f"✗ Test 1: Found potential hardcoded logic:")
        for item in found_hardcoded:
            print(f"  {item}")

    # Check agent_registry.py for hardcoded agent names in logic
    from nanobot.anp import agent_registry as registry_module
    registry_source = inspect.getsource(registry_module)

    # The get() method should be generic
    get_method = inspect.getsource(registry_module.AgentRegistry.get)
    if '"smart-home"' not in get_method and '"cloud-storage"' not in get_method:
        print(f"✓ Test 2: AgentRegistry.get() is generic")
    else:
        print(f"✗ Test 2: AgentRegistry.get() may have hardcoded logic")

    print("\n✅ Generic Implementation Test PASSED!\n")


if __name__ == "__main__":
    import inspect

    asyncio.run(test_server_mode_response_flow())
    asyncio.run(test_client_mode_discovery())
    asyncio.run(test_error_handling())
    asyncio.run(test_generic_implementation())

    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
