"""启动所有演示 A2A 服务器的脚本。"""

import os
import signal
import subprocess
import sys

import uvicorn


def main():
    """启动所有 A2A 服务器。"""

    print("启动演示 A2A 服务器...")

    processes = []

    # 启动天气 Agent
    print("\n🌤️  启动天气 Agent (端口 8001)...")
    weather_proc = subprocess.Popen(
        [sys.executable, "weather_agent.py"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    processes.append(("Weather Agent", weather_proc, 8001))
    print(f"   天气 Agent PID: {weather_proc.pid}")

    # 等待一下
    import time
    time.sleep(1)

    # 启动计算器 Agent
    print("\n🔢 启动计算器 Agent (端口 8002)...")
    calc_proc = subprocess.Popen(
        [sys.executable, "calculator_agent.py"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    processes.append(("Calculator Agent", calc_proc, 8002))
    print(f"   计算器 Agent PID: {calc_proc.pid}")

    # 保存 PID
    with open(".weather_agent.pid", "w") as f:
        f.write(str(weather_proc.pid))
    with open(".calculator_agent.pid", "w") as f:
        f.write(str(calc_proc.pid))

    print("\n" + "=" * 50)
    print("所有 A2A 服务器已启动！")
    print("=" * 50)
    print("天气 Agent:   http://localhost:8001")
    print("计算器 Agent: http://localhost:8002")
    print("\n按 Ctrl+C 停止所有服务器\n")

    # 等待进程
    try:
        for name, proc, port in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\n\n正在停止服务器...")
        for name, proc, port in processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                proc.kill()

        # 清理 PID 文件
        for f in [".weather_agent.pid", ".calculator_agent.pid"]:
            try:
                os.remove(f)
            except:
                pass

        print("服务器已停止")


if __name__ == "__main__":
    main()
