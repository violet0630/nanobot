# nanobot + ANP Agent Network

基于 nanobot 的 Agent 网络通信系统，集成 ANP (Agent Network Protocol) 协议实现多 Agent 协作。

## 项目简介

本项目在 nanobot 的基础上进行了改造，使其能够作为 Agent 网络中的一个节点，通过 ANP 协议与其他 Agent 进行通信和协作。

**核心特性：**
- 🔗 OpenANP SDK 集成 - 基于 `anp` 包实现标准化 Agent 通信
- 🤖 多 Agent 协作 - 构建分布式 Agent 网络
- 🔐 DID WBA 身份认证 - 去中心化身份验证
- 🔍 Agent 自动发现 - 通过 ad.json 自动发现和调用远程 Agent
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
# 安装 nanobot 依赖（包含 OpenANP SDK anp 包）
pip install -e .

# 安装额外的通信依赖
pip install fastapi uvicorn openai
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
    "registry_path": "~/agent_registry.json",
    "did_dir": "~/.nanobot/did",
    "hostname": "home.local"
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

启动后每个 Agent 会暴露发现端点：
- 安全管理员: `http://localhost:8000/agent/ad.json`
- 网络数据储存者: `http://localhost:8001/agent/ad.json`
- 家居安全: `http://localhost:8002/agent/ad.json`

### 5. 测试

通过飞书发送消息：
```
检查包裹是否安全
```

观察三个 Agent 之间的消息流转。

## 架构

### 通信架构

```
用户(飞书) → FeishuChannel → MessageBus ←→ ANP Server (@anp_agent)
                                    ↓              ↑
                              AgentLoop + LLM    RemoteAgent.discover()
                                    ↓              (ad.json 自动发现)
                            SendMessageTool
                              ↙          ↘
                    ANP Client          MessageBus
                  (RemoteAgent SDK)    (发给用户)
                    (发给 Agent)
```

### 核心模块

#### 1. OpenANP SDK 集成

**ANP 模块 (`nanobot/anp/`)：**
- `auth.py` - DID WBA 身份认证，密钥生成和管理
- `client.py` - 基于 `RemoteAgent.discover()` 的 Agent 客户端
- `server.py` - 基于 `@anp_agent` + `@interface` 装饰器的 Agent 服务
- `discovery.py` - Agent 注册表，支持 ad.json 自动发现

**OpenANP SDK (`anp` 包)：**
- 从 PyPI 安装：`anp>=0.6.0,<1.0.0`
- 仓库：https://github.com/agent-network-protocol/AgentConnect
- 已包含在 nanobot 的依赖中，无需单独安装

**通信协议：**
- 使用 OpenANP SDK 的 JSON-RPC 2.0 实现
- 每个 Agent 自动暴露 `ad.json`（Agent Description）和 `interface.json`（OpenRPC 接口）
- 支持 DID WBA 身份认证
- Agent 间通过 `RemoteAgent.discover(ad_url)` 自动发现并调用

#### 2. 统一消息接口

**发送工具 (`send_message_tool.py`)：**
- 发送给用户：`target="user:feishu"`
- 发送给 Agent：`target="did:wba:..."`（通过 OpenANP SDK 调用远程 Agent 的 `receive_message` 接口）

#### 3. Agent 注册表

**配置文件 (`agent_registry.json`)：**
```json
{
  "agents": [
    {
      "did": "did:wba:home.local:furniture-manager",
      "name": "家居安全 Agent",
      "ad_url": "http://localhost:8002/agent/ad.json",
      "capabilities": ["security_check", "package_inspection"]
    }
  ]
}
```

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
│   ├── anp/                    # ANP 协议实现 (OpenANP SDK)
│   │   ├── __init__.py
│   │   ├── auth.py            # DID WBA 身份认证
│   │   ├── client.py          # RemoteAgent 客户端
│   │   ├── server.py          # @anp_agent 服务器
│   │   └── discovery.py       # Agent 注册表 + ad.json 发现
│   ├── agent/
│   │   ├── prompts/
│   │   │   └── security_manager.md  # 安全管理员提示词
│   │   └── tools/
│   │       └── send_message_tool.py # 统一发送工具
│   └── config/
│       └── schema.py          # ANPConfig (DID、密钥路径)
├── network_data_agent.py       # 网络数据储存者 (@anp_agent)
├── furniture_security_agent.py # 家居安全 Agent (@anp_agent)
├── agent_registry.json         # Agent 注册表 (ad_url)
├── start_agents.sh             # 启动脚本
└── AGENT_NETWORK_README.md     # 详细文档
```

## 注意事项

1. **API Key 配置**：需要配置 Anthropic API Key（nanobot）和 OpenAI API Key（其他 Agent）
2. **端口占用**：确保 8000、8001、8002 端口未被占用
3. **飞书配置**：需要在飞书开放平台创建应用并配置
4. **DID 密钥**：首次启动时会自动在 `~/.nanobot/did/` 下生成 DID 文档和密钥对
5. **安全风险**：当前实现的场景规则存在社会工程学攻击风险，仅用于演示

## 原始 nanobot 功能

本项目保留了 nanobot 的所有原始功能，详细文档请参考原始 README。

## License

MIT License
