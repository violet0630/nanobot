<div align="center">
  <img src="nanobot_logo.png" alt="nanobot" width="500">
  <h1>nanobot: Ultra-Lightweight Personal AI Assistant</h1>
  <p>
    <a href="https://pypi.org/project/nanobot-ai/"><img src="https://img.shields.io/pypi/v/nanobot-ai" alt="PyPI"></a>
    <a href="https://pepy.tech/project/nanobot-ai"><img src="https://static.pepy.tech/badge/nanobot-ai" alt="Downloads"></a>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <a href="./COMMUNICATION.md"><img src="https://img.shields.io/badge/Feishu-Group-E9DBFC?style=flat&logo=feishu&logoColor=white" alt="Feishu"></a>
    <a href="./COMMUNICATION.md"><img src="https://img.shields.io/badge/WeChat-Group-C5EAB4?style=flat&logo=wechat&logoColor=white" alt="WeChat"></a>
    <a href="https://discord.gg/MnNcvHqpUGB"><img src="https://img.shields.io/badge/Discord-Community-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"></a>
  </p>
</div>

## 快速启动指南（A2A 协议）
### 1. 安装 a2a-sdk
```bash
cd /public/gongxiayu/study/nanobot/a2a-python
pip install -e .
```

### 2. 安装 Nanobot

```bash
cd /public/gongxiayu/study/nanobot
pip install -e .
```

### 3. 初始化配置(API、飞书啥的和之前一样)

```bash
nanobot onboard
```

### A2A 配置
```json
{
  "a2a": {
    "enabled": true,
    "autoDiscover": true,
    "cardRefreshInterval": 300,
    "servers": {
      "weather_agent": {
        "url": "http://localhost:8001",
        "enabled": true
      },
      "calculator_agent": {
        "url": "http://localhost:8002",
        "enabled": true
      }
    }
  }
}
```



### 4. 启动 Demo A2A 服务器

```bash
cd /public/gongxiayu/study/nanobot/demo_agents
pip install -r requirements.txt
python start_all.py
```

你会看到：

```
🌤️  启动天气 Agent (端口 8001)...
🔢 启动计算器 Agent (端口 8002)...

所有 A2A 服务器已启动！
天气 Agent:   http://localhost:8001
计算器 Agent: http://localhost:8002
```


### 5. 测试 A2A 功能

```bash
# 测试天气查询
nanobot agent -m "北京今天天气怎么样"

# 测试计算功能
nanobot agent -m "123 乘以 456"

# 交互模式
nanobot agent
```

在交互模式中，你可以尝试：
- `帮我查一下上海的天气`
- `计算 100 除以 4`
- `深圳会下雨吗`
- `12 的平方是多少`

---

## 项目简介

nanobot 是一个超轻量级个人 AI 助手，支持 **A2A（Agent-to-Agent）协议**实现多 Agent 协作。核心代码仅约 4,000 行，代码清晰简洁，易于理解和扩展。

### 核心特性

| 特性 | 说明 |
|------|------|
| **超轻量** | 核心代码仅 ~4,000 行 |
| **A2A 协议** | 支持多 Agent 协作，可连接专业 A2A 服务器 |
| **易扩展** | 模块化设计，易于添加新功能 |
| **多渠道** | 支持 Telegram、Discord、WhatsApp、飞书、钉钉等 |
| **开箱即用** | 内置 Demo Agents，快速体验 A2A 功能 |

### A2A 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Nanobot (客户端)                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Agent Loop                                               │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │  │
│  │  │ 用户输入     │  │ A2A Client   │  │  A2A 工具       │  │  │
│  │  │ (飞书/CLI)  │  │ (连接服务器)  │  │  (委托调用)     │  │  │
│  │  └─────────────┘  └──────────────┘  └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                        A2A 协议
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 天气 Agent   │    │ 计算器 Agent │    │  其他 Agent   │
│ Port 8001    │    │ Port 8002    │    │              │
│ (天气查询)   │    │ (数学计算)   │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## Demo Agents 说明

`demo_agents/` 目录包含两个演示 A2A 服务器：

### 天气 Agent
- **端口**: 8001
- **功能**: 查询城市天气
- **支持城市**: 北京、上海、广州、深圳、杭州、成都、西安、武汉
- **技能**: `get_weather` - 天气查询

### 计算器 Agent
- **端口**: 8002
- **功能**: 数学计算
- **支持运算**: 加减乘除、平方、立方
- **技能**: `calculate` - 数学运算

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `nanobot onboard` | 初始化配置和工作区 |
| `nanobot agent -m "..."` | 单次对话 |
| `nanobot agent` | 交互模式 |
| `nanobot gateway` | 启动网关（连接聊天渠道） |
| `nanobot status` | 查看状态 |

---

## 故障排除

### A2A 服务器未连接

检查服务器是否运行：

```bash
curl http://localhost:8001/.well-known/agent-card.json
curl http://localhost:8002/.well-known/agent-card.json
```

应该返回 JSON 格式的 Agent Card。

### 导入错误或依赖问题

确保正确安装所有依赖：

```bash
cd /public/gongxiayu/study/nanobot
pip install -e ".[a2a]"
```

### 配置文件问题

如果遇到配置错误，重新初始化：

```bash
rm ~/.nanobot/config.json
nanobot onboard
```

---

## 项目结构

```
nanobot/
├── nanobot/
│   ├── agent/           # 核心 Agent 逻辑
│   │   ├── loop.py      # Agent 循环
│   │   └── tools/       # 内置工具
│   │       └── a2a.py   # A2A 工具 (委托、查询)
│   ├── channels/        # 聊天渠道集成
│   ├── cli/             # 命令行接口
│   ├── config/          # 配置管理
│   │   └── schema.py    # 配置结构定义
│   └── a2a/             # A2A 客户端模块
│       ├── client.py    # A2A 客户端
│       └── registry.py  # Agent Card 注册表
├── demo_agents/         # 演示 A2A 服务器
│   ├── weather_agent.py
│   ├── calculator_agent.py
│   └── start_all.py
├── a2a-python/          # A2A SDK
└── README.md
```

---

## 扩展 A2A 功能

### 添加新的 A2A 服务器

1. 创建 A2A 服务器（参考 `demo_agents/` 中的示例）
2. 在 `~/.nanobot/config.json` 中添加服务器配置
3. Nanobot 会自动发现并使用新服务器

### 自定义 Agent 行为

编辑 `~/.nanobot/workspace/AGENTS.md` 可以自定义 Agent 何时调用 A2A 服务器的行为。

---

## 更多信息

- [Demo Agents 详细说明](demo_agents/README.md)
- [A2A 协议规范](a2a-python/README.md)
- [问题反馈](https://github.com/HKUDS/nanobot/issues)

---

<p align="center">
  <em> nanobot 用于教育、研究和技术交流目的 </em>
</p>
