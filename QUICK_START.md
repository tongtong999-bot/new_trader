# 快速开始交易

## ✅ 连接已成功！

OKX模拟交易连接已成功，可以开始交易。

---

## 🚀 立即开始

### 1. 单币种交易（推荐先测试）

```bash
cd /Users/cast/my_trading_system
python3 live_trading_v52.py
# 选择 1 - 使用当前配置启动
```

### 2. 多币种交易

```bash
python3 multi_symbol_trading.py
# 选择 1 - 使用默认币种列表
```

---

## 📊 查看交易日志

### 实时查看

```bash
# 实时查看最新日志
tail -f live_trading_v52.log
```

### 查看交易记录

```bash
# 查看所有交易
grep "开仓\|平仓" live_trading_v52.log

# 查看盈利交易
grep "盈亏: +" live_trading_v52.log
```

### 使用查看工具

```bash
python3 view_trades.py
```

---

## 📁 日志文件位置

- **单币种日志**: `live_trading_v52.log`
- **多币种日志**: `logs/multi_symbol_YYYYMMDD.log`

---

## 🔍 查看交易了什么

### 方式1: 查看日志

```bash
# 查看所有交易记录
grep "开仓\|平仓\|交易" live_trading_v52.log | tail -20
```

### 方式2: 查看OKX网站

1. 登录OKX网站
2. 进入"模拟交易"账户
3. 查看"交易历史"

### 方式3: 使用查看工具

```bash
python3 view_trades.py
```

---

## 🔄 多币种配置

### 默认币种

- BTC/USDT:USDT
- ETH/USDT:USDT
- SOL/USDT:USDT
- LINK/USDT:USDT
- AVAX/USDT:USDT
- XRP/USDT:USDT

### 自定义币种

运行 `python3 multi_symbol_trading.py`，选择选项2，输入币种列表。

---

## ⚠️ 重要提示

1. **当前是模拟交易** - 使用OKX模拟资金
2. **真实下单** - 订单会真实提交到OKX
3. **监控日志** - 定期查看日志确保正常运行
4. **网络稳定** - 确保网络连接稳定

---

## 📖 详细文档

查看 `TRADING_GUIDE.md` 获取完整指南。
