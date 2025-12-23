# v5.2 实盘/模拟盘快速开始（脱敏版）

## 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置密钥（只用环境变量）

```bash
export OKX_API_KEY="YOUR_OKX_API_KEY"
export OKX_API_SECRET="YOUR_OKX_API_SECRET"
export OKX_PASSPHRASE="YOUR_OKX_PASSPHRASE"  # 如果没有可留空
```

## 3. 启动

```bash
python3 live_trading_v52.py
```

## 4. 多币种

```bash
python3 multi_symbol_trading.py
```

## 5. 查看日志

```bash
tail -f live_trading_v52.log
```
