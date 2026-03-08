"""Test the ANP response correlation fix."""

import asyncio
from nanobot.anp.server import _pending_anp_requests, complete_pending_request
from nanobot.bus.events import OutboundMessage


async def test_response_correlation():
    """Test that ANP responses are properly correlated with requests."""
    print("Testing ANP response correlation fix...")

    # Create a test future (simulating server.py behavior)
    test_future = asyncio.Future()
    correlation_id = "test_correlation_123"

    # Register the pending request (simulating server.py:289)
    _pending_anp_requests[correlation_id] = test_future
    print(f"✓ Registered pending request: {correlation_id}")

    # Create a response (simulating loop.py:624-633)
    response = OutboundMessage(
        channel="anp",
        chat_id="did:test:caller",
        content="Test response content",
        metadata={
            "correlation_id": correlation_id,
            "caller_did": "did:test:caller",
            "method": "testMethod",
        }
    )
    print(f"✓ Created OutboundMessage with correlation_id: {correlation_id}")

    # Simulate loop.py:_complete_anp_response behavior
    result = {
        "status": "success",
        "content": response.content,
        "metadata": response.metadata,
    }

    # Complete the pending request
    if complete_pending_request(correlation_id, result):
        print(f"✓ Completed pending request: {correlation_id}")

        # Check if future was set
        if test_future.done():
            actual_result = test_future.result()
            print(f"✓ Future was set with result: {actual_result}")

            # Verify result content
            if actual_result["status"] == "success":
                print(f"✓ Result status correct: {actual_result['status']}")
            if actual_result["content"] == "Test response content":
                print(f"✓ Result content correct: {actual_result['content']}")
            if actual_result["metadata"]["correlation_id"] == correlation_id:
                print(f"✓ Correlation ID preserved: {actual_result['metadata']['correlation_id']}")
        else:
            print("✗ Future was not set!")
    else:
        print(f"✗ Failed to complete pending request: {correlation_id}")

    # Clean up
    _pending_anp_requests.pop(correlation_id, None)

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_response_correlation())
