# 交互式输入修复总结

## 问题

原代码在 `live_trading_v52.py` 和 `multi_symbol_trading.py` 的 `main()` 函数中使用了 `input()`，在 Docker/云端部署时会阻塞等待用户输入。

## 修复内容

### 1. `live_trading_v52.py`

- 添加 `argparse` 支持命令行参数
- 添加 `--non-interactive` 标志（或环境变量 `NON_INTERACTIVE=1`）
- 支持环境变量配置：
  - `TRADING_SYMBOL`: 交易对
  - `TRADING_MODE`: 模式（demo/paper/live）
- 保持向后兼容（无参数时仍使用交互模式）

### 2. `multi_symbol_trading.py`

- 添加 `argparse` 支持命令行参数
- 添加 `--non-interactive` 标志（或环境变量 `NON_INTERACTIVE=1`）
- 支持环境变量配置：
  - `TRADING_SYMBOLS`: 币种列表（逗号分隔）
  - `TRADING_MODE`: 模式（demo/paper/live）
- 保持向后兼容（无参数时仍使用交互模式）

### 3. `docker-compose.yml`

- 添加 `NON_INTERACTIVE=1` 环境变量
- 添加 `TRADING_SYMBOL` 和 `TRADING_MODE` 环境变量
- 默认命令使用 `--non-interactive` 标志

## 使用方式

### 单币种（非交互）

```bash
# 方式1：环境变量
export NON_INTERACTIVE=1
export TRADING_SYMBOL=ETH/USDT:USDT
export TRADING_MODE=demo
python3 live_trading_v52.py

# 方式2：命令行参数
python3 live_trading_v52.py --non-interactive --symbol ETH/USDT:USDT --demo

# 方式3：Docker Compose（自动使用非交互模式）
docker compose up -d
```

### 多币种（非交互）

```bash
# 方式1：环境变量
export NON_INTERACTIVE=1
export TRADING_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
export TRADING_MODE=demo
python3 multi_symbol_trading.py

# 方式2：命令行参数
python3 multi_symbol_trading.py --non-interactive --symbols BTC/USDT:USDT ETH/USDT:USDT --demo

# 方式3：Docker Compose（修改 docker-compose.yml 中的 command）
```

## 向后兼容

如果不使用 `--non-interactive` 或 `NON_INTERACTIVE` 环境变量，代码仍会使用原来的交互模式，保持向后兼容。
