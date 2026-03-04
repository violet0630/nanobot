"""简单的天气 A2A 服务器。

模拟天气查询功能，用于演示 nanobot 的 A2A 集成。
"""

import asyncio
import logging
import os
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
logger = logging.getLogger("WeatherAgent")


# 模拟天气数据
MOCK_WEATHER_DATA = {
    "北京": {"temp": 22, "condition": "晴", "humidity": 45, "wind": "微风"},
    "上海": {"temp": 26, "condition": "多云", "humidity": 65, "wind": "东南风3级"},
    "广州": {"temp": 30, "condition": "阵雨", "humidity": 80, "wind": "南风2级"},
    "深圳": {"temp": 31, "condition": "阴", "humidity": 75, "wind": "微风"},
    "杭州": {"temp": 25, "condition": "小雨", "humidity": 70, "wind": "东风2级"},
    "成都": {"temp": 24, "condition": "阴", "humidity": 60, "wind": "微风"},
    "西安": {"temp": 23, "condition": "晴", "humidity": 40, "wind": "西北风3级"},
    "武汉": {"temp": 27, "condition": "多云", "humidity": 68, "wind": "东南风2级"},
}


class WeatherAgentExecutor(AgentExecutor):
    """天气 Agent 执行器。"""

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
        """执行天气查询任务。"""
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

        logger.info("[WeatherAgent] 收到查询: %s", user_text)

        # 发送 working 状态
        working_status = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    role="agent",
                    message_id=str(uuid.uuid4()),
                    parts=[TextPart(text="正在查询天气信息...")],
                    task_id=task_id,
                    context_id=context_id,
                ),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_status)

        # 模拟处理延迟
        await asyncio.sleep(1)

        # 生成天气回复
        reply = self._generate_weather_response(user_text)

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

    def _generate_weather_response(self, query: str) -> str:
        """生成天气回复。"""
        query_lower = query.lower()

        # 查找提到的城市
        for city, data in MOCK_WEATHER_DATA.items():
            if city in query:
                return (
                    f"🌍 {city}天气信息：\n"
                    f"🌡️ 温度：{data['temp']}°C\n"
                    f"☁️ 天气：{data['condition']}\n"
                    f"💧 湿度：{data['humidity']}%\n"
                    f"🌬️ 风力：{data['wind']}"
                )

        # 未找到城市，返回通用回复
        cities = "、".join(list(MOCK_WEATHER_DATA.keys())[:5])
        return (
            f"抱歉，我没有找到您查询的城市信息。目前支持查询：{cities}等城市。\n"
            "请告诉我您想查询哪个城市的天气？"
        )


def main() -> None:
    """启动天气 A2A 服务器。"""
    http_port = int(os.environ.get("PORT", "8001"))

    agent_card = AgentCard(
        name="Weather Agent",
        description="提供天气查询服务的 A2A 代理",
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
                "id": "get_weather",
                "name": "天气查询",
                "description": "查询指定城市的天气信息，包括温度、天气状况、湿度和风力",
                "tags": ["天气", "weather", "温度", "气温"],
                "examples": [
                    "北京今天天气怎么样",
                    "上海天气",
                    "查询广州的天气",
                    "明天深圳会下雨吗",
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
        agent_executor=WeatherAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build(rpc_url=JSONRPC_URL)

    logger.info(f"🌤️  天气 A2A 服务器启动在 http://localhost:{http_port}")
    uvicorn.run(app, host="127.0.0.1", port=http_port, log_level="info")


if __name__ == "__main__":
    main()
