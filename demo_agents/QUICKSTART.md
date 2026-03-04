# A2A 集成快速启动指南

## 一、安装依赖

### 1. 安装 Nanobot (带 A2A 支持)

```bash
cd /public/gongxiayu/study/nanobot
pip install -e ".[a2a]"
```

### 2. 安装演示 Agent 依赖

```bash
cd /public/gongxiayu/study/demo_agents
pip install -r requirements.txt
```

## 二、启动演示 A2A 服务器

```bash
cd /public/gongxiayu/study/demo_agents
python start_all.py
```

你应该看到：

```
启动演示 A2A 服务器...

🌤️  启动天气 Agent (端口 8001)...
   天气 Agent PID: xxxxx

🔢 启动计算器 Agent (端口 8002)...
   计算器 Agent PID: xxxxx

==================================================
所有 A2A 服务器已启动！
==================================================
天气 Agent:   http://localhost:8001
计算器 Agent: http://localhost:8002

按 Ctrl+C 停止所有服务器
```

## 三、配置 Nanobot

编辑 `~/.nanobot/config.json`，添加 A2A 配置：

```json
{
  "a2a": {
    "enabled": true,
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

## 四、测试

### 方式 1: 命令行模式

```bash
# 测试天气查询
nanobot agent -m "北京今天天气怎么样"

# 测试计算
nanobot agent -m "123 乘以 456"
```

### 方式 2: 交互模式

```bash
nanobot agent
```

然后输入：
- `帮我查一下上海的天气`
- `计算 100 除以 4`
- `深圳会下雨吗`
- `12 的平方是多少`

## 五、预期结果

Nanobot 会自动识别请求类型并委托给对应的 A2A 服务器：

```
用户: 北京今天天气怎么样
Nanobot: [检测到 weather_agent 有天气技能]
       🌍 北京天气信息：
       🌡️ 温度：22°C
       ☁️ 天气：晴
       💧 湿度：45%
       🌬️ 风力：微风

用户: 123 乘以 456
Nanobot: [检测到 calculator_agent 有计算技能]
       🔢 计算结果：
       123 * 456 = 56088
```

## 故障排除

### 1. A2A 服务器未连接

检查服务器是否运行：
```bash
curl http://localhost:8001/.well-known/agent-card.json
curl http://localhost:8002/.well-known/agent-card.json
```

应该返回 JSON 格式的 Agent Card。

### 2. Nanobot 没有使用 A2A 服务器

检查配置文件中的 `a2a.enabled` 是否为 `true`。

查看 Nanobot 日志，应该有：
```
INFO - A2A client connected with 2 servers
```

### 3. 找不到 a2a-sdk

确保安装了 A2A 依赖：
```bash
pip install 'nanobot-ai[a2a]'
```

## 文件结构

```
/public/gongxiayu/study/
├── A2A_INTEGRATION.md          # 详细集成说明
├── demo_agents/
│   ├── weather_agent.py        # 天气 A2A 服务器
│   ├── calculator_agent.py     # 计算器 A2A 服务器
│   ├── start_all.py            # 启动脚本 (Python)
│   ├── start_all.sh            # 启动脚本 (Bash)
│   ├── requirements.txt        # Python 依赖
│   └── README.md               # 演示服务器说明
└── nanobot/
    └── nanobot/
        ├── a2a/                # A2A 客户端模块
        └── agent/tools/a2a.py  # A2A 工具
```
