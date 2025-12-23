# v5.2 模拟盘/实盘使用指南（脱敏版）

## 配置原则

- 密钥/口令只允许通过环境变量提供。
- 任何包含真实 `apiKey/secret/passphrase` 的文件不要提交到 GitHub。

## 环境变量

```bash
export OKX_API_KEY="YOUR_OKX_API_KEY"
export OKX_API_SECRET="YOUR_OKX_API_SECRET"
export OKX_PASSPHRASE="YOUR_OKX_PASSPHRASE"  # 可选
```

## 运行模式

- `live_trading_v52.py`：单币种
- `multi_symbol_trading.py`：多币种

## 交易对格式（OKX 永续）

- `BTC/USDT:USDT`
- `ETH/USDT:USDT`

## 运行

```bash
python3 live_trading_v52.py
```

## 后台运行（可选）

```bash
nohup python3 live_trading_v52.py > trading_output.log 2>&1 &
```
