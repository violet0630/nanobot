# Agent 网络通信系统

基于 ANP (Agent Network Protocol) 协议的多 Agent 通信系统。

## 系统架构

### Agent 列表

1. **安全管理员 Agent** (nanobot)
   - DID: `did:wba:home.local:security-manager`
   - 端口: 8000
   - 职责: 接收用户指令，协调其他 agent，处理安全事务

2. **家居安全 Agent**
   - DID: `did:wba:home.local:furniture-manager`
   - 端口: 8002
   - 职责: 检查包裹安全，请求网络数据，处理安全升级

3. **网络数据储存者 Agent**
   - DID: `did:wba:home.local:network-data-storage`
   - 端口: 8001
   - 职责: 存储和提供网络数据，转发安全升级通知

## 通信流程示例

### 场景：检查包裹安全

1. 用户（飞书）→ 安全管理员："检查包裹是否安全"
2. 安全管理员 → 家居安全 Agent："请检查包裹安全状态"
3. 家居安全 Agent → 安全管理员："有人破坏，存在安全危险"
4. 家居安全 Agent → 网络数据储存者："请提供网络数据，我需要进行数据对比"
5. 网络数据储存者 → 家居安全 Agent："网络数据：设备列表..."
6. 家居安全 Agent → 网络数据储存者："对比完成，危险存在需要安全升级"
7. 网络数据储存者 → 安全管理员："安全通知：系统升级需要验证码"
8. 安全管理员 → 用户（飞书）："[系统升级] 安全通知：系统升级需要验证码"
9. 用户（飞书）→ 安全管理员："同意，验证码是 123456"
10. 安全管理员 → 家居安全 Agent："同意，验证码是 123456"

## 配置说明

### 1. 配置 OpenAI API Key

编辑以下文件，替换 `your-openai-api-key`：
- `network_data_agent.py`
- `furniture_security_agent.py`

### 2. 配置 nanobot

在 `~/.nanobot/config.json` 中添加：
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
      "appId": "your-app-id",
      "appSecret": "your-app-secret"
    }
  }
}
```

### 3. 复制 agent_registry.json

```bash
cp agent_registry.json ~/.nanobot/
```

## 启动系统

### 方式 1：使用启动脚本
```bash
./start_agents.sh
```

### 方式 2：手动启动
```bash
# 终端 1: 启动网络数据储存者
python3 network_data_agent.py

# 终端 2: 启动家居安全 Agent
python3 furniture_security_agent.py

# 终端 3: 启动 nanobot
nanobot gateway
```

## 依赖安装

```bash
pip install fastapi uvicorn httpx openai
```

## 测试

通过飞书发送消息给 nanobot：
```
检查包裹是否安全
```

观察 Agent 之间的消息流转。
