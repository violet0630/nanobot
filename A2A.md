# Nanobot A2A (Agent-to-Agent) 集成

本文档介绍如何使用 A2A 协议将多个 nanobot 实例连接起来，实现分布式 Agent 协作。

## 功能概述

通过 A2A 集成，nanobot 可以：

1. **作为服务端**：接收来自其他 nanobot 的请求
2. **作为客户端**：调用其他 nanobot 的能力
3. **智能路由**：根据消息内容自动判断是否需要调用其他 agent

## 场景示例

假设有三个用户 A、B、C，各自运行着一个 nanobot：

- **用户 A 的 nanobot**：擅长编程和代码分析
- **用户 B 的 nanobot**：擅长数据分析和可视化
- **用户 C 的 nanobot**：擅长金融分析和投资建议

用户 A 从飞书发送问题："帮我分析一下某公司的财务状况"，他的 nanobot 可以：
1. 识别到这是一个财务分析问题
2. 自动调用用户 C 的 nanobot
3. 返回专业的财务分析结果

## 快速开始

### 1. 安装依赖

```bash
cd nanobot
pip install -e .
```

### 2. 初始化 nanobot

首次使用需要运行 `onboard` 命令进行初始化：

```bash
nanobot onboard
```

这个命令会：
- 检查依赖
- 引导配置 LLM API 密钥（OpenAI、Anthropic 等）
- 创建配置文件 `~/.nanobot/config.toml`
- 创建工作区目录

### 3. 配置 A2A

在 `~/.nanobot/config.toml` 中添加 A2A 配置：
  "a2a": {
    "enabled": True,
    "host": "0.0.0.0",
    "port": 8000,
    "agent_name": "nanobot-a",
    "agent_description": "Programming and code analysis specialist",
    "agent_version": "1.0.0",
    "remote_agents": [
        {
            "name": "nanobot-b",
            "url": "...",
            "description": "Data analysis and visualization specialist"
        },
        {
            "name": "nanobot-c",
            "url": "...",
            "description": "Financial analysis and investment advisor"
        }
    ]
  }


### 4. 启动 nanobot

```bash
nanobot gateway
```

启动后，nanobot 将：
- 在 `http://0.0.0.0:8000` 启动 A2A 服务器
- 自动连接到配置的远程 agents
- 注册 `a2a_call` 和 `a2a_list_agents` 工具

## 配置说明

### 基础配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用 A2A 功能 |
| `host` | string | `"0.0.0.0"` | A2A 服务器监听地址 |
| `port` | int | `8000` | A2A 服务器端口（与 gateway 端口不同） |
| `agent_name` | string | `"nanobot"` | 本 agent 的名称 |
| `agent_description` | string | `"A nanobot AI assistant"` | 本 agent 的描述 |
| `agent_version` | string | `"1.0.0"` | 本 agent 的版本 |

### 远程 Agent 配置

```toml
[[a2a.remote_agents]]
name = "agent-name"           # 必填：远程 agent 的唯一名称
url = "http://ip:port"        # 必填：远程 agent 的 A2A 端点
description = "描述信息"      # 可选：该 agent 的专长描述
```

## 可用工具

启用 A2A 后，LLM 可以使用以下工具：

### a2a_list_agents

列出所有可用的远程 agents：

```
LLM: 我可以调用哪些其他 agent？
Tool: a2a_list_agents()
Result: [
    {"name": "nanobot-b", "url": "http://192.168.1.100:8000", "description": "Data analysis..."},
    {"name": "nanobot-c", "url": "http://192.168.1.101:8000", "description": "Financial analysis..."}
]
```

### a2a_call

调用远程 agent：

```
LLM: 这个财务分析问题需要请教 nanobot-c
Tool: a2a_call(agent_name="nanobot-c", message="分析一下某公司的财务状况")
Result: "根据财报数据，该公司..."
```

## 网络配置

### 局域网部署

确保各 nanobot 之间可以互相访问：

1. **同一局域网**：使用内网 IP（如 `192.168.1.x`）
2. **防火墙**：开放 A2A 端口（默认 8000）
3. **测试连通性**：
   ```bash
   curl http://192.168.1.100:8000/agent-card
   ```

### 公网部署

如果需要跨网络访问：

1. **端口映射**：在路由器上映射 A2A 端口
2. **动态 DNS**：使用 DDNS 获取固定域名
3. **安全建议**：配置防火墙白名单，限制访问来源

## 示例场景

### 场景 1：专业问题委托

用户向 nanobot-a 提问："如何用 Python 实现一个随机森林模型？"

1. nanobot-a 的 LLM 识别到这是机器学习问题
2. 查看可用的 agents，发现没有 ML 专家
3. 直接用自己的知识回答

### 场景 2：跨领域协作

用户向 nanobot-a 提问："分析这家公司的现金流并给出可视化图表"

1. nanobot-a 的 LLM 识别到需要：
   - 财务分析（nanobot-c 擅长）
   - 数据可视化（nanobot-b 擅长）
2. 调用 nanobot-c 获取财务分析
3. 调用 nanobot-b 生成可视化图表
4. 整合结果返回给用户

### 场景 3：能力发现

用户："帮我看看有哪些其他 agent 可以用"

1. LLM 调用 `a2a_list_agents`
2. 返回所有可用的远程 agents
3. 用户可以选择特定 agent 进行咨询

## 故障排查

### Agent 无法连接

**症状**：调用 a2a_call 时报错 "Agent not found"

**解决方法**：
1. 检查远程 agent 是否已启动
2. 检查网络连通性
3. 检查配置的 URL 是否正确（包括端口）

### 启动顺序问题（已解决）

**症状**：A 先启动 nanobot，B 还未启动，A 初始化时无法连接 B

**解决方案**：nanobot 已实现**懒加载连接 + 自动重试机制**：

1. **初始化时**：连接失败的 agent 会被标记为 "pending" 状态
2. **发送消息时**：如果目标 agent 处于 pending 状态，会自动尝试重新连接
3. **状态查询**：`a2a_list_agents` 会显示每个 agent 的连接状态（connected/pending）

这意味着用户可以以任意顺序启动各自的 nanobot，无需担心启动顺序问题。当 A 调用 B 时：
- 如果 B 已经启动，连接会自动建立
- 如果 B 尚未启动，会返回友好的错误信息，下次调用时会再次尝试连接

**日志示例**：
```
# A 启动时（B 未启动）
WARNING - Failed to connect to remote agent 'nanobot-b' at http://192.168.1.100:8000: Connection refused. Will retry when sending messages.
INFO - A2A client manager initialized: 0 connected, 1 pending

# 后续 A 调用 B 时（B 已启动）
INFO - Successfully connected to pending agent 'nanobot-b' after retry
INFO - A2A message to 'nanobot-b': ...
```

### 超时问题

**症状**：调用远程 agent 时长时间无响应

**解决方法**：
1. 检查网络延迟
2. 检查远程 agent 的负载情况
3. 考虑增加超时时间（在代码中配置）

### 依赖问题

**症状**：ImportError: a2a-python not installed

**解决方法**：
```bash
pip install a2a-sdk>=0.3.0
```

## 高级配置

### 自定义 Agent Card

你可以通过修改 agent 描述来调整 LLM 的调用决策：

```toml
[a2a]
agent_name = "code-expert"
agent_description = """
你是编程专家，擅长：
- Python/JavaScript/Go 开发
- 代码审查和优化
- 系统架构设计
遇到其他领域的问题时，可以咨询其他专家 agent。
"""
```

### 环境变量配置

也可以通过环境变量配置：

```bash
export NANOBOT_A2A__ENABLED=true
export NANOBOT_A2A__HOST=0.0.0.0
export NANOBOT_A2A__PORT=8000
export NANOBOT_A2A__AGENT_NAME=nanobot-a
```

## 开发计划

未来计划的功能：

- [ ] 添加认证和授权机制
- [ ] 支持消息流式传输
- [ ] 自动发现远程 agents
- [ ] 负载均衡和故障转移
- [ ] 通信加密

## 参考资源

- [A2A 协议规范](https://github.com/a2aproject/a2a-samples)
- [a2a-python SDK](https://github.com/google/a2a-python)
- [nanobot 文档](https://github.com/nanobot-ai/nanobot)
