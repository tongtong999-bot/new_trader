# 复利模式回测说明

## 回测配置

- **模式**: 复利模式（盈利后资金增加，后续交易使用更大的资金）
- **风险控制**: RISK_PER_TRADE=3%（以风险控制仓位，不固定每笔仓位）
- **最大仓位限制**: 42%（不变）
- **时间范围**: 2022年1月 - 2025年11月
- **初始资金**: 每个币种 20,000 USDT（趋势10,000 + 网格10,000）

## 关键修改

1. **移除资金增长限制**：
   - 移除了 `grid_balance_max` 限制
   - 允许 `trend_balance` 和 `grid_balance` 自由增长（复利）

2. **风险控制仓位**：
   - 使用 `RISK_PER_TRADE=3%` 控制每笔交易的风险
   - 仓位大小 = 风险金额 / (入场价 - 止损价)
   - 不再固定每笔仓位金额

3. **多年份数据合并**：
   - 自动合并2022-2025年11月的数据
   - 支持分半年数据格式（如2023h1, 2023h2）

## 查看进度

```bash
# 查看日志
tail -f backtest_compound.log

# 查看已完成的币种
ls -lh backtest_compound_results/*.csv

# 检查脚本是否还在运行
ps aux | grep backtest_compound_2022_2025.py
```

## 结果文件

- `backtest_compound_summary.csv` - 所有币种的总结表格
- `backtest_{SYMBOL}_USDT_compound_trades.csv` - 各币种的交易记录
- `backtest_{SYMBOL}_USDT_compound_equity.csv` - 各币种的权益曲线

## 注意事项

- 复利模式下，资金会持续增长，收益可能远高于固定资金模式
- 回测时间较长（多年份连续数据），请耐心等待
- 所有结果将保存在 `backtest_compound_results/` 目录
