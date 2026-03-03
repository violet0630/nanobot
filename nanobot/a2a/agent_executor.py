"""A2A AgentExecutor for nanobot.

This adapter connects nanobot's AgentLoop with the A2A server protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from loguru import logger

try:
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.utils import new_agent_text_message
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    # Define stub types for when a2a is not installed
    class AgentExecutor:  # type: ignore
        pass
    class RequestContext:  # type: ignore
        pass
    class EventQueue:  # type: ignore
        pass

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


class NanobotAgentExecutor(AgentExecutor):
    """A2A AgentExecutor that delegates to nanobot's AgentLoop."""

    def __init__(self, agent_loop: "AgentLoop"):
        if not A2A_AVAILABLE:
            raise ImportError(
                "a2a-python is not installed. "
                "Install it with: pip install a2a-python"
            )
        self.agent_loop = agent_loop

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute an A2A request using nanobot's AgentLoop."""
        try:
            # Extract the message from the A2A request
            message = context.message
            if not message or not message.parts:
                await event_queue.enqueue_event(
                    new_agent_text_message("Error: No message content provided")
                )
                return

            # Get the text content from the message parts
            text_content = ""
            for part in message.parts:
                if hasattr(part.root, "text"):
                    text_content = part.root.text
                    break

            if not text_content:
                await event_queue.enqueue_event(
                    new_agent_text_message("Error: No text content in message")
                )
                return

            logger.info("A2A request received: {}", text_content[:100])

            # Process the message using nanobot's AgentLoop
            # We use "system" channel to indicate this is an A2A request
            from nanobot.bus.events import InboundMessage

            a2a_msg = InboundMessage(
                channel="a2a",
                sender_id=message.context_id or "a2a_client",
                chat_id=message.task_id or "a2a_task",
                content=text_content,
                metadata={
                    "a2a_task_id": message.task_id,
                    "a2a_context_id": message.context_id,
                    "a2a_message_id": message.message_id,
                },
            )

            response = await self.agent_loop._process_message(
                a2a_msg,
                session_key=f"a2a:{message.context_id or 'default'}",
            )

            # Send the response back through A2A
            if response and response.content:
                await event_queue.enqueue_event(
                    new_agent_text_message(response.content)
                )
            else:
                await event_queue.enqueue_event(
                    new_agent_text_message("Processed successfully")
                )

        except Exception as e:
            logger.exception("Error executing A2A request")
            await event_queue.enqueue_event(
                new_agent_text_message(f"Error: {str(e)}")
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation requests."""
        await event_queue.enqueue_event(
            new_agent_text_message("Cancellation not supported")
        )
