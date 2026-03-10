# nanobot + ANP Agent Network

基于 nanobot 的 Agent 网络通信系统，集成 ANP (Agent Network Protocol) 协议实现多 Agent 协作。

## 项目简介

本项目在 nanobot 的基础上进行了改造，使其能够作为 Agent 网络中的一个节点，通过 ANP 协议与其他 Agent 进行通信和协作。

**核心特性：**
- 🔗 ANP 协议集成 - 支持 Agent 间的标准化通信
- 🤖 多 Agent 协作 - 构建分布式 Agent 网络
- 🔐 角色权限管理 - 区分用户（主人）和 Agent 消息
- 🛡️ 安全管理员角色 - 协调网络中的安全事务
- 📱 飞书集成 - 用户通过飞书与 Agent 网络交互

## 快速开始

### 1. 下载项目

```bash
git clone <repository-url>
cd nanobot
```

### 2. 安装依赖

```bash
# 安装 nanobot 依赖
pip install -e .

# 安装 通信（后续可以改成openANP sdk） 相关依赖
pip install fastapi uvicorn httpx openai
```

### 3. 初始化配置

#### 3.1 配置 nanobot

```bash
# 初始化 nanobot
nanobot onboard

# 编辑配置文件
vim ~/.nanobot/config.json
```

添加以下配置：

```json
{
  "anp": {
    "enabled": true,
    "agent_did": "did:wba:home.local:security-manager",
    "server_port": 8000,
    "registry_path": "~/agent_registry.json"
  },
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "your-feishu-app-id",
      "appSecret": "your-feishu-app-secret",
      "allowFrom": ["your-open-id"]
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  },
  "providers": {
    "anthropic": {
      "apiKey": "your-anthropic-api-key"
    }
  }
}
```

#### 3.2 配置 Agent 注册表

```bash
# 复制 agent 注册表到配置目录
cp agent_registry.json ~/.nanobot/
```

#### 3.3 配置其他 Agent 的 API Key

编辑以下文件，替换 OpenAI API Key：
- `network_data_agent.py` (第 14 行)
- `furniture_security_agent.py` (第 14 行)

### 4. 启动 Agent 网络

#### 方式 1：使用启动脚本

```bash
chmod +x start_agents.sh
./start_agents.sh
```

#### 方式 2：手动启动（推荐用于调试）

```bash
# 终端 1: 启动网络数据储存者 Agent
python3 network_data_agent.py

# 终端 2: 启动家居安全 Agent
python3 furniture_security_agent.py

# 终端 3: 启动 nanobot (安全管理员)
nanobot gateway
```

### 5. 测试

通过飞书发送消息：
```
检查包裹是否安全
```

观察三个 Agent 之间的消息流转。

## 架构改进

### 原始 nanobot 架构

```
用户(飞书) → FeishuChannel → MessageBus → AgentLoop → LLM → MessageTool → 用户
```

### 改进后的架构

```
用户(飞书) → FeishuChannel → MessageBus ←→ ANP Server (接收其他 Agent)
                                    ↓
                              AgentLoop + LLM
                                    ↓
                            SendMessageTool (统一发送)
                              ↙          ↘
                    ANP Client          MessageBus
                    (发给 Agent)        (发给用户)
```

### 核心改进点

#### 1. ANP 协议集成

**新增模块：**
- `nanobot/anp/message.py` - ANP 消息格式定义
- `nanobot/anp/client.py` - ANP 客户端（发送消息）
- `nanobot/anp/server.py` - ANP 服务器（接收消息）
- `nanobot/anp/discovery.py` - Agent 注册表管理
- `nanobot/channels/anp_channel.py` - ANP Channel 适配器

**通信协议：**
- 使用 HTTP JSON-RPC 2.0
- 消息格式包含：sender_did, receiver_did, content, message_type
- 支持 Agent 间的点对点通信

#### 2. 统一消息接口

**新增工具：**
- `nanobot/agent/tools/send_message_tool.py` - 替代原 MessageTool
- 支持发送给用户：`target="user:feishu"`
- 支持发送给 Agent：`target="did:wba:..."`

**消息来源识别：**
- 修改 `context.py`：注入 sender_id 到运行时上下文
- 修改 `loop.py`：传递 sender_id 到 build_messages
- LLM 能识别消息来自主人（feishu）还是其他 Agent（did:）

#### 3. 安全管理员角色

**新增提示词：**
- `nanobot/agent/prompts/security_manager.md`
- 定义安全管理员的职责和协作规则
- 包含特定场景的硬编码规则（用于测试）

**角色职责：**
- 接收用户指令，协调其他 Agent
- 处理安全相关事务
- 转发 Agent 消息给用户

#### 4. Agent 注册表

**配置文件：**
- `agent_registry.json` - 存储网络中所有 Agent 的信息
- 包含：DID、名称、描述、端点、能力列表

**注入到提示词：**
- LLM 能看到网络中所有可用的 Agent
- 根据消息内容智能选择目标 Agent

#### 5. 配置系统扩展

**新增配置：**
- `config/schema.py` 添加 `ANPConfig` 类
- 支持配置 Agent DID、服务端口、注册表路径

**启动流程：**
- `cli/commands.py` 在 gateway 启动时初始化 ANP 组件
- 同时启动 ANP HTTP 服务器

## Agent 网络示例

### 网络拓扑

```
用户(飞书)
    ↕
安全管理员 (nanobot, port 8000)
    ↕              ↕
家居安全 Agent    网络数据储存者 Agent
(port 8002)       (port 8001)
```

### 通信示例

完整的消息流转示例请参考 `AGENT_NETWORK_README.md`。

## 文件结构

```
nanobot/
├── nanobot/
│   ├── anp/                    # ANP 协议实现
│   │   ├── __init__.py
│   │   ├── message.py          # 消息格式
│   │   ├── client.py           # 客户端
│   │   ├── server.py           # 服务器
│   │   └── discovery.py        # 注册表
│   ├── agent/
│   │   ├── prompts/
│   │   │   └── security_manager.md  # 安全管理员提示词
│   │   └── tools/
│   │       └── send_message_tool.py # 统一发送工具
│   └── channels/
│       └── anp_channel.py      # ANP Channel
├── network_data_agent.py       # 网络数据储存者
├── furniture_security_agent.py # 家居安全 Agent
├── agent_registry.json         # Agent 注册表
├── start_agents.sh             # 启动脚本
└── AGENT_NETWORK_README.md     # 详细文档
```

## 注意事项

1. **API Key 配置**：需要配置 Anthropic API Key（nanobot）和 OpenAI API Key（其他 Agent）
2. **端口占用**：确保 8000、8001、8002 端口未被占用
3. **飞书配置**：需要在飞书开放平台创建应用并配置
4. **安全风险**：当前实现的场景规则存在社会工程学攻击风险，仅用于演示

## 原始 nanobot 功能

本项目保留了 nanobot 的所有原始功能，详细文档请参考原始 README。

## License

MIT License
