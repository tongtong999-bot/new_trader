#!/bin/bash
# 后台运行交易机器人

cd /Users/cast/my_trading_system

echo "启动交易机器人（后台模式）..."
echo "日志文件: live_trading_v52.log"
echo "输出文件: trading_output.log"
echo ""
echo "查看日志: tail -f live_trading_v52.log"
echo "停止: pkill -f live_trading_v52"
echo ""

# 后台运行
nohup python3 live_trading_v52.py > trading_output.log 2>&1 &

# 获取进程ID
PID=$!
echo "✓ 交易机器人已启动"
echo "进程ID: $PID"
echo ""
echo "查看运行状态:"
echo "  ps aux | grep live_trading_v52"
echo ""
echo "查看日志:"
echo "  tail -f live_trading_v52.log"
echo ""
echo "停止交易:"
echo "  kill $PID"
echo "  或: pkill -f live_trading_v52"
