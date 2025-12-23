# OKX 模拟交易（Demo Trading）配置

## 必须先做的事（避免密钥泄露）

- 不要把 `apiKey/secret/passphrase` 写进代码或提交到 GitHub。
- 只用环境变量注入密钥。

## 环境变量配置

在终端执行（把占位符替换成你自己的）：

```bash
export OKX_API_KEY="YOUR_OKX_API_KEY"
export OKX_API_SECRET="YOUR_OKX_API_SECRET"
export OKX_PASSPHRASE="YOUR_OKX_PASSPHRASE"  # 如果没有可留空
```

## 运行（单币种）

```bash
cd /path/to/github_upload
python3 live_trading_v52.py
```

## 运行（多币种）

```bash
cd /path/to/github_upload
python3 multi_symbol_trading.py
```

## 日志

- `live_trading_v52.log`
- `logs/multi_symbol_YYYYMMDD.log`
