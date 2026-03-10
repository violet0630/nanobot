#!/bin/bash
# Agent 网络启动脚本

echo "启动 Agent 网络..."

# 启动网络数据储存者 Agent (端口 8001)
echo "启动网络数据储存者 Agent (端口 8001)..."
python3 network_data_agent.py &
NETWORK_PID=$!

# 启动家居安全 Agent (端口 8002)
echo "启动家居安全 Agent (端口 8002)..."
python3 furniture_security_agent.py &
FURNITURE_PID=$!

# 启动 nanobot 安全管理员 Agent (端口 8000)
echo "启动 nanobot 安全管理员 Agent (端口 8000)..."
nanobot gateway &
NANOBOT_PID=$!

echo ""
echo "所有 Agent 已启动："
echo "- 网络数据储存者: http://localhost:8001 (PID: $NETWORK_PID)"
echo "- 家居安全 Agent: http://localhost:8002 (PID: $FURNITURE_PID)"
echo "- 安全管理员 (nanobot): http://localhost:8000 (PID: $NANOBOT_PID)"
echo ""
echo "按 Ctrl+C 停止所有 Agent"

# 等待中断信号
trap "kill $NETWORK_PID $FURNITURE_PID $NANOBOT_PID; exit" INT
wait
