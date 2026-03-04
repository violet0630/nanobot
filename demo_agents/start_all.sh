#!/bin/bash
# 启动所有演示 A2A 服务器

echo "启动演示 A2A 服务器..."

# 在后台启动天气 Agent
echo "启动天气 Agent (端口 8001)..."
python weather_agent.py &
WEATHER_PID=$!
echo "天气 Agent PID: $WEATHER_PID"

sleep 1

# 在后台启动计算器 Agent
echo "启动计算器 Agent (端口 8002)..."
python calculator_agent.py &
CALC_PID=$!
echo "计算器 Agent PID: $CALC_PID"

# 保存 PID 到文件
echo $WEATHER_PID > .weather_agent.pid
echo $CALC_PID > .calculator_agent.pid

echo ""
echo "========================================="
echo "所有 A2A 服务器已启动！"
echo "========================================="
echo "天气 Agent: http://localhost:8001"
echo "计算器 Agent: http://localhost:8002"
echo ""
echo "按 Ctrl+C 停止所有服务器"
echo ""

# 等待中断信号
cleanup() {
    echo ""
    echo "正在停止服务器..."
    kill $WEATHER_PID 2>/dev/null
    kill $CALC_PID 2>/dev/null
    rm -f .weather_agent.pid .calculator_agent.pid
    echo "服务器已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持脚本运行
wait
