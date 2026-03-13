"""ANP server for receiving messages from other agents, using OpenANP SDK."""

import logging

import uvicorn
from fastapi import FastAPI
from anp.openanp import anp_agent, interface, AgentConfig

logger = logging.getLogger(__name__)

# MessageBus reference, set at startup
_message_bus = None


def set_message_bus(bus):
    """Set the global message bus reference."""
    global _message_bus
    _message_bus = bus


def create_security_manager_agent(agent_did: str, prefix: str = "/agent"):
    """Create the SecurityManager ANP agent class dynamically."""

    @anp_agent(AgentConfig(
        name="SecurityManager",
        did=agent_did,
        prefix=prefix,
        description="安全管理员 Agent，负责处理安全相关事务，协调其他 Agent",
    ))
    class SecurityManagerAgent:

        @interface
        async def receive_message(self, sender_did: str, content: str, message_type: str = "agent_request") -> str:
            """接收来自其他 Agent 的 ANP 消息。

            Args:
                sender_did: 发送者 DID
                content: 消息内容
                message_type: 消息类型 (agent_request / agent_response)

            Returns:
                处理结果
            """
            if _message_bus is None:
                return "Error: MessageBus not initialized"

            try:
                from nanobot.bus.events import InboundMessage

                inbound = InboundMessage(
                    channel="anp",
                    sender_id=sender_did,
                    chat_id=agent_did,
                    content=content,
                    metadata={"message_type": message_type},
                )
                await _message_bus.publish_inbound(inbound)
                return "Message received"
            except Exception as e:
                logger.error("Error processing ANP message: %s", e)
                return f"Error: {str(e)}"

    return SecurityManagerAgent


class ANPServer:
    """ANP server wrapping the OpenANP agent."""

    def __init__(self, config, message_bus):
        self.config = config
        self.message_bus = message_bus

        set_message_bus(message_bus)

        # Create ANP agent and FastAPI app
        self.agent_cls = create_security_manager_agent(
            agent_did=config.agent_did,
            prefix="/agent",
        )
        self.app = FastAPI()
        self.app.include_router(self.agent_cls.router())

    async def start(self):
        """Start the ANP server."""
        cfg = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.config.server_port,
            log_level="info",
        )
        server = uvicorn.Server(cfg)
        await server.serve()
