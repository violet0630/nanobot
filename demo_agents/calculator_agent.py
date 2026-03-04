"""简单计算器 A2A 服务器。

执行数学计算功能，用于演示 nanobot 的 A2A 集成。
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import uvicorn

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers.default_request_handler import (
    DefaultRequestHandler,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    Message,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)


JSONRPC_URL = "/a2a/jsonrpc"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CalculatorAgent")


class CalculatorAgentExecutor(AgentExecutor):
    """计算器 Agent 执行器。"""

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """取消任务。"""
        status_update = TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id or str(uuid.uuid4()),
            status=TaskStatus(
                state=TaskState.canceled,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            final=True,
        )
        await event_queue.enqueue_event(status_update)

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """执行计算任务。"""
        user_message = context.message
        task_id = context.task_id
        context_id = context.context_id

        # 提取用户消息内容
        user_text = ""
        for part in user_message.parts:
            if hasattr(part, "text"):
                user_text = part.text
                break
            elif hasattr(part, "root") and hasattr(part.root, "text"):
                user_text = part.root.text
                break

        logger.info("[CalculatorAgent] 收到计算请求: %s", user_text)

        # 发送 working 状态
        working_status = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    role="agent",
                    message_id=str(uuid.uuid4()),
                    parts=[TextPart(text="正在计算...")],
                    task_id=task_id,
                    context_id=context_id,
                ),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_status)

        # 模拟处理延迟
        await asyncio.sleep(0.5)

        # 计算结果
        reply = self._calculate(user_text)

        # 创建最终消息
        agent_message = Message(
            role="agent",
            message_id=str(uuid.uuid4()),
            parts=[TextPart(text=reply)],
            task_id=task_id,
            context_id=context_id,
        )

        final_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=agent_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            final=True,
        )
        await event_queue.enqueue_event(final_update)

    def _calculate(self, query: str) -> str:
        """解析并计算数学表达式。"""
        # 移除常见的数学表达描述
        text = query.lower()
        text = text.replace("计算", "").replace("等于", "=")
        text = text.replace("乘以", "*").replace("x", "*").replace("×", "*")
        text = text.replace("除以", "/").replace("÷", "/")
        text = text.replace("加", "+").replace("减", "-")
        text = text.replace("的平方", "**2").replace("²", "**2")
        text = text.replace("的立方", "**3").replace("³", "**3")
        text = text.replace("的", "")

        # 尝试提取数学表达式
        # 匹配形如 "123 * 456" 或 "123+456" 的表达式
        patterns = [
            r"[\d\s\+\-\*\/\(\)\.\*\*]+",
            r"\d+[\s\*\+\-\/]\d+",
        ]

        expression = None
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 清理表达式
                expr = match.strip()
                if expr and len(expr) > 2:
                    expression = expr
                    break
            if expression:
                break

        # 如果没有找到表达式，尝试从文本中直接提取数字和运算符
        if not expression:
            # 查找所有数字和运算符
            tokens = re.findall(r"(\d+\.?\d*|[\+\-\*\/])", text)
            if len(tokens) >= 3:
                expression = "".join(tokens)

        if expression:
            try:
                # 安全地计算表达式
                result = eval(expression, {"__builtins__": {}}, {})
                return f"🔢 计算结果：\n{expression} = {result}"
            except Exception as e:
                return f"❌ 无法计算表达式 '{expression}'：{str(e)}"

        return (
            "🤔 请提供一个数学计算表达式。\n"
            "支持的运算：加(+)、减(-)、乘(*)、除(/)、平方(**2)、立方(**3)\n"
            "例如：\n"
            "- \"123 * 456\"\n"
            "- \"100 + 200\"\n"
            "- \"50 / 2\"\n"
            "- \"12 ** 2\" (12的平方)"
        )


def main() -> None:
    """启动计算器 A2A 服务器。"""
    http_port = int(os.environ.get("PORT", "8002"))

    agent_card = AgentCard(
        name="Calculator Agent",
        description="提供数学计算服务的 A2A 代理",
        url=f"http://localhost:{http_port}{JSONRPC_URL}",
        provider=AgentProvider(
            organization="Demo",
            url="https://example.com",
        ),
        version="1.0.0",
        protocol_version="0.3.0",
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=False,
        ),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            {
                "id": "calculate",
                "name": "数学计算",
                "description": "执行基本的数学运算，包括加减乘除、平方、立方等",
                "tags": ["计算", "calculator", "数学", "运算"],
                "examples": [
                    "123 乘以 456",
                    "计算 100 + 200",
                    "50 除以 2",
                    "12 的平方是多少",
                    "计算 3.14 * 2",
                ],
                "input_modes": ["text"],
                "output_modes": ["text"],
            }
        ],
        supports_authenticated_extended_card=False,
        preferred_transport="JSONRPC",
        additional_interfaces=[
            {
                "url": f"http://localhost:{http_port}{JSONRPC_URL}",
                "transport": "JSONRPC",
            },
        ],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CalculatorAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build(rpc_url=JSONRPC_URL)

    logger.info(f"🔢 计算 A2A 服务器启动在 http://localhost:{http_port}")
    uvicorn.run(app, host="127.0.0.1", port=http_port, log_level="info")


if __name__ == "__main__":
    main()
