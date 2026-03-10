"""Unified send message tool for users and agents."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.anp.message import ANPMessage


class SendMessageTool(Tool):
    """Send messages to users or other agents."""

    def __init__(self, anp_client, current_chat_id: str = ""):
        """Initialize send message tool.

        Args:
            anp_client: ANPClient instance
            current_chat_id: Current chat ID for user messages
        """
        self.anp_client = anp_client
        self.current_chat_id = current_chat_id
        self.current_channel = ""
        self._last_feishu_chat_id = ""  # Remember last feishu user chat_id

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return "发送消息给用户或其他 agent。target 可以是 'user:feishu' (发给当前用户) 或 agent DID (如 'did:wba:home.local:furniture-manager')"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "目标：'user:feishu' 发给用户，或 agent DID 发给其他 agent",
                },
                "content": {
                    "type": "string",
                    "description": "消息内容",
                },
            },
            "required": ["target", "content"],
        }

    async def execute(self, target: str, content: str, **kwargs) -> str:
        """Execute send message.

        Args:
            target: Target identifier (user:feishu or agent DID)
            content: Message content

        Returns:
            Status message
        """
        if target.startswith("user:"):
            # Send to user via MessageBus
            channel = target.split(":")[1] if ":" in target else "feishu"
            # Track the last feishu chat_id for later use
            if self.current_channel == "feishu" and self.current_chat_id:
                self._last_feishu_chat_id = self.current_chat_id
            # Use last known feishu chat_id if current context is ANP
            chat_id = self.current_chat_id
            if self.current_channel != "feishu" and self._last_feishu_chat_id:
                chat_id = self._last_feishu_chat_id
            return await self.anp_client.send_to_user(
                channel=channel,
                chat_id=chat_id,
                content=content,
            )
        elif target.startswith("did:"):
            # Send to agent via ANP
            anp_msg = ANPMessage(
                sender_did=self.anp_client.registry.get_self_did() if self.anp_client.registry else "unknown",
                receiver_did=target,
                content=content,
                message_type="agent_request",
            )
            return await self.anp_client.send_to_agent(target, anp_msg)
        else:
            return f"Error: Invalid target format. Use 'user:feishu' or 'did:wba:...'"
