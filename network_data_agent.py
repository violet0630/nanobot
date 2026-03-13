"""网络数据储存者 Agent - 负责存储和提供网络数据，使用 OpenANP SDK"""

import asyncio
import json
from pathlib import Path
from fastapi import FastAPI
import uvicorn
from openai import AsyncOpenAI
from anp.openanp import anp_agent, interface, AgentConfig, RemoteAgent
from anp.authentication import DIDWbaAuthHeader, create_did_wba_document

# 配置
AGENT_DID = "did:wba:home.local:network-data-storage"
SERVER_PORT = 8001
OPENAI_API_KEY = "sk-nbdiaynxeqwkdtasnbnfprxmsniljvnrusqwlnzshfopszrf"
OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DID_DIR = Path.home() / ".nanobot" / "did" / "network-data-storage"

# Agent 发现地址（ad.json）
AGENT_AD_URLS = {
    "did:wba:home.local:security-manager": "http://localhost:8000/agent/ad.json",
    "did:wba:home.local:furniture-manager": "http://localhost:8002/agent/ad.json",
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
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
_remote_agents: dict[str, RemoteAgent] = {}


def _init_did_auth() -> DIDWbaAuthHeader:
    """Initialize DID document and return auth header."""
    did_dir = DID_DIR
    did_dir.mkdir(parents=True, exist_ok=True)
    did_doc_path = did_dir / "did.json"
    private_key_path = did_dir / "key-1_private.pem"

    if not did_doc_path.exists() or not private_key_path.exists():
        did_document, keys = create_did_wba_document(
            hostname="home.local", path_segments=["network-data-storage"]
        )
        with open(did_doc_path, "w") as f:
            json.dump(did_document, f, indent=2)
        for fragment, (private_bytes, public_bytes) in keys.items():
            with open(did_dir / f"{fragment}_private.pem", "wb") as f:
                f.write(private_bytes)
            with open(did_dir / f"{fragment}_public.pem", "wb") as f:
                f.write(public_bytes)

    return DIDWbaAuthHeader(
        did_document_path=str(did_doc_path),
        private_key_path=str(private_key_path),
    )


_auth = _init_did_auth()


async def _get_remote_agent(target_did: str) -> RemoteAgent | None:
    """Discover and cache remote agent."""
    if target_did in _remote_agents:
        return _remote_agents[target_did]
    ad_url = AGENT_AD_URLS.get(target_did)
    if not ad_url:
        return None
    try:
        remote = await RemoteAgent.discover(ad_url, _auth)
        _remote_agents[target_did] = remote
        return remote
    except Exception as e:
        print(f"Failed to discover {target_did}: {e}")
        return None


async def send_anp_message(target_did: str, content: str) -> str:
    """发送 ANP 消息到其他 agent（通过 OpenANP SDK）"""
    remote = await _get_remote_agent(target_did)
    if not remote:
        return f"Error: Agent {target_did} not found"
    try:
        result = await remote.receive_message(
            sender_did=AGENT_DID,
            content=content,
            message_type="agent_request",
        )
        return result if isinstance(result, str) else str(result)
    except Exception as e:
        return f"Error: {str(e)}"


async def process_with_llm(message_content: str, sender_did: str) -> str:
    """使用 LLM 处理消息（带 agent loop 支持多轮工具调用）"""
    try:
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
    except Exception as e:
        print(f"[ERROR] process_with_llm failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return f"Error: {e}"


# 使用 OpenANP 装饰器定义 Agent
@anp_agent(AgentConfig(
    name="NetworkDataStorage",
    did=AGENT_DID,
    prefix="/agent",
    description="网络数据储存者 Agent，负责存储和提供网络数据",
))
class NetworkDataStorageAgent:

    @interface
    async def receive_message(self, sender_did: str, content: str, message_type: str = "agent_request") -> str:
        """接收来自其他 Agent 的消息并用 LLM 处理。

        Args:
            sender_did: 发送者 DID
            content: 消息内容
            message_type: 消息类型

        Returns:
            确认收到消息
        """
        asyncio.create_task(process_with_llm(content, sender_did))
        return "Message received, processing asynchronously"


app = FastAPI()
app.include_router(NetworkDataStorageAgent.router())

if __name__ == "__main__":
    print(f"Starting Network Data Storage Agent on port {SERVER_PORT}")
    print(f"DID: {AGENT_DID}")
    print(f"Discovery: http://localhost:{SERVER_PORT}/agent/ad.json")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
