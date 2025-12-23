#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析网格信号间隔
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / 'strategies'))
from box_strategy_v5_2 import StrategyConfig

# 读取之前检查的信号日志
# 或者重新运行检查，但这次记录详细信息

print("=" * 80)
print("网格信号间隔分析")
print("=" * 80)

# 从之前的输出可以看到，最近三个信号是：
signals = [
    {'time': '2025-12-22 14:00:00', 'price': 89979.85, 'grid_price': 89986.68, 'layer': 1},
    {'time': '2025-12-22 14:15:00', 'price': 89953.17, 'grid_price': 89986.68, 'layer': 1},
    {'time': '2025-12-22 14:30:00', 'price': 89832.27, 'grid_price': 89986.68, 'layer': 1},
]

print("\n最近3个信号:")
print("-" * 80)
for i, sig in enumerate(signals, 1):
    print(f"{i}. {sig['time']}")
    print(f"   当前价格: {sig['price']:.2f}")
    print(f"   网格价格: {sig['grid_price']:.2f}")
    print(f"   Layer: {sig['layer']}")
    print()

print("信号间隔分析:")
print("-" * 80)

# 计算间隔
for i in range(1, len(signals)):
    prev = signals[i-1]
    curr = signals[i]
    
    # 时间间隔（15分钟）
    time_diff = 15  # 15分钟K线
    
    # 价格间隔
    price_diff = abs(curr['grid_price'] - prev['grid_price'])
    price_diff_pct = price_diff / prev['grid_price'] * 100
    
    # 当前价格与网格价格的差异
    curr_price_diff = abs(curr['price'] - curr['grid_price'])
    curr_price_diff_pct = curr_price_diff / curr['grid_price'] * 100
    
    print(f"{i}. {prev['time']} -> {curr['time']}")
    print(f"   时间间隔: {time_diff} 分钟")
    print(f"   网格价格间隔: {price_diff_pct:.4f}%")
    print(f"   当前价格与网格价格差异: {curr_price_diff_pct:.4f}%")
    print()

print("问题分析:")
print("-" * 80)
print("1. 所有信号都是同一个Layer (Layer 1)")
print("2. 网格价格完全相同 (89986.68)")
print("3. 时间间隔只有15分钟（每根K线检查一次）")
print("4. 当前价格都在网格价格附近（在1%容差内）")
print()
print("原因:")
print("- 网格策略的容差是1%（代码第818行：price_tolerance = layer_price * 0.01）")
print("- 只要价格在网格层价格的1%范围内，就会触发信号")
print("- 每15分钟检查一次，如果价格一直在网格层附近，就会持续触发")
print("- 检查脚本中没有持仓记录，所以每次都认为可以开仓")
print()
print("实际交易中:")
print("- 如果已经开了Layer 1的持仓，应该不会再开（代码第814行检查）")
print("- 但检查脚本传入的existing_positions是空字典，所以没有这个限制")
print()
print("建议:")
print("- 检查云端是否有Layer 1的持仓")
print("- 如果有持仓，这是正常的（不会重复开仓）")
print("- 如果没有持仓但也没开单，可能是其他原因（资金、API等）")
