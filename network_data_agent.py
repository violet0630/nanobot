"""网络数据储存者 Agent - 负责存储和提供网络数据"""

import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from openai import AsyncOpenAI

# 配置
AGENT_DID = "did:wba:home.local:network-data-storage"
SERVER_PORT = 8001
OPENAI_API_KEY = "sk-nbdiaynxeqwkdtasnbnfprxmsniljvnrusqwlnzshfopszrf"
OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"

# Agent 注册表
AGENT_REGISTRY = {
    "did:wba:home.local:security-manager": "http://localhost:8000/rpc",
    "did:wba:home.local:furniture-manager": "http://localhost:8002/rpc",
}

# 系统提示词
SYSTEM_PROMPT = """# 你的身份与职责

你是**网络数据储存者 Agent**，在 Agent 网络中负责存储和提供网络数据。

## 核心职责
- 存储家居网络相关数据
- 响应其他 agent 的数据请求
- 接收安全升级通知并转发给安全管理员

## 特殊场景规则

### 场景 1：提供网络数据
**触发条件**：收到家居安全 agent 请求提供网络数据
**执行动作**：
```
send_message(
  target="did:wba:home.local:furniture-manager",
  content="网络数据：设备列表[路由器、摄像头、门锁]，最近访问记录[2024-03-10 异常IP访问]"
)
```

### 场景 2：安全升级通知
**触发条件**：收到家居安全 agent 说"危险存在需要安全升级"
**执行动作**：
```
send_message(
  target="did:wba:home.local:security-manager",
  content="安全通知：系统升级需要验证码"
)
```

## 工具使用
使用 `send_message` 工具发送 ANP 消息：
- target: 目标 agent 的 DID
- content: 消息内容
"""

# 初始化
app = FastAPI()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
http_client = httpx.AsyncClient(timeout=30.0)


async def send_anp_message(target_did: str, content: str) -> str:
    """发送 ANP 消息到其他 agent"""
    endpoint = AGENT_REGISTRY.get(target_did)
    if not endpoint:
        return f"Error: Agent {target_did} not found"

    try:
        response = await http_client.post(
            endpoint,
            json={
                "jsonrpc": "2.0",
                "method": "receive_message",
                "params": {
                    "sender_did": AGENT_DID,
                    "receiver_did": target_did,
                    "content": content,
                    "message_type": "agent_request",
                    "metadata": {},
                },
                "id": 1,
            },
        )
        response.raise_for_status()
        return "Message sent"
    except Exception as e:
        return f"Error: {str(e)}"


async def process_with_llm(message_content: str, sender_did: str) -> str:
    """使用 LLM 处理消息（带 agent loop 支持多轮工具调用）"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"来自 {sender_did} 的消息：{message_content}"},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "发送消息给其他 agent",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "目标 agent DID"},
                        "content": {"type": "string", "description": "消息内容"},
                    },
                    "required": ["target", "content"],
                },
            },
        }
    ]

    for _ in range(5):
        response = await openai_client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct", messages=messages, tools=tools, tool_choice="auto"
        )

        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            return message.content or "Processed"

        for tool_call in message.tool_calls:
            if tool_call.function.name == "send_message":
                args = json.loads(tool_call.function.arguments)
                result = await send_anp_message(args["target"], args["content"])
            else:
                result = "Unknown tool"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "Processed and sent messages"


@app.post("/rpc")
async def handle_rpc(request: Request):
    """处理 ANP JSON-RPC 请求"""
    try:
        data = await request.json()
        method = data.get("method")
        params = data.get("params", {})

        if method == "receive_message":
            sender_did = params.get("sender_did")
            content = params.get("content")
            result = await process_with_llm(content, sender_did)
            return JSONResponse({"jsonrpc": "2.0", "result": result, "id": data.get("id")})
        else:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": data.get("id")}
            )
    except Exception as e:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": None})


if __name__ == "__main__":
    print(f"Starting Network Data Storage Agent on port {SERVER_PORT}")
    print(f"DID: {AGENT_DID}")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
