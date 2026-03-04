# 演示 A2A 服务器

这个目录包含两个简单的 A2A (Agent-to-Agent) 协议服务器，用于演示 nanobot 的 A2A 客户端集成功能。

## 服务器列表

### 1. 天气 Agent (`weather_agent.py`)
- **端口**: 8001
- **功能**: 模拟天气查询服务
- **技能**: `get_weather` - 查询城市天气信息

支持的城市：北京、上海、广州、深圳、杭州、成都、西安、武汉

### 2. 计算器 Agent (`calculator_agent.py`)
- **端口**: 8002
- **功能**: 数学计算服务
- **技能**: `calculate` - 执行基本数学运算

支持运算：加减乘除、平方、立方

## 安装依赖

```bash
cd /public/gongxiayu/study/demo_agents
pip install -r requirements.txt
```

## 启动服务器

### 方式 1: 使用启动脚本（推荐）

```bash
python start_all.py
```

这会同时启动两个服务器。

### 方式 2: 单独启动

```bash
# 终端 1 - 天气 Agent
python weather_agent.py

# 终端 2 - 计算器 Agent
python calculator_agent.py
```

### 方式 3: 指定端口

```bash
PORT=8010 python weather_agent.py
PORT=8011 python calculator_agent.py
```

## 配置 Nanobot

在 `~/.nanobot/config.json` 中添加：

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

## 测试

### 通过 Nanobot CLI

```bash
# 启动 nanobot
nanobot agent -m "北京今天天气怎么样"

# 或交互模式
nanobot agent
> 计算 123 乘以 456
> 查询上海的天气
```

### 通过 Gateway

```bash
nanobot gateway
```

然后在配置的聊天渠道（如 Telegram、Feishu）发送消息。

## 验证 A2A 连接

启动 nanobot 后，应该看到类似的日志：

```
INFO - Connecting to A2A server 'weather_agent' at http://localhost:8001
INFO - Fetched Agent Card for 'weather_agent': Weather Agent (skills: 1)
INFO - Connected to A2A server 'weather_agent'
INFO - Connecting to A2A server 'calculator_agent' at http://localhost:8002
INFO - Fetched Agent Card for 'calculator_agent': Calculator Agent (skills: 1)
INFO - Connected to A2A server 'calculator_agent'
INFO - A2A client connected with 2 servers
```

## Agent Card 示例

访问 `http://localhost:8001/.well-known/agent-card.json` 可以查看天气 Agent 的 Agent Card：

```json
{
  "name": "Weather Agent",
  "description": "提供天气查询服务的 A2A 代理",
  "url": "http://localhost:8001/a2a/jsonrpc",
  "skills": [
    {
      "id": "get_weather",
      "name": "天气查询",
      "description": "查询指定城市的天气信息",
      "tags": ["天气", "weather", "温度", "气温"]
    }
  ]
}
```

## 停止服务器

在启动脚本的终端按 `Ctrl+C`，或手动 kill 进程：

```bash
# 如果保存了 PID 文件
kill $(cat .weather_agent.pid) $(cat .calculator_agent.pid)
```
