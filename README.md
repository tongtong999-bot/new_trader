# 交易系统

基于v5.2策略的自动化交易系统，支持币安和OKX交易所。

## 功能特性

- ✅ 支持币安和OKX交易所
- ✅ 支持合约交易（可配置杠杆）
- ✅ 多币种同时交易
- ✅ 趋势交易和网格交易策略
- ✅ 自动风险控制
- ✅ PushPlus通知
- ✅ Docker部署支持
- ✅ 无交互模式（适合云端部署）

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入API密钥。

### 3. 运行

**单币种（默认非交互模式）：**
```bash
python3 live_trading_v52.py
```

**多币种（默认非交互模式）：**
```bash
python3 multi_symbol_trading.py
```

**注意**：默认已启用非交互模式，适合云端部署。如需交互模式，可设置环境变量 `NON_INTERACTIVE=0`。

## Docker部署

### 1. 配置环境变量

创建 `.env` 文件（不要提交到Git）：

```bash
EXCHANGE=binance  # 或 okx
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
LEVERAGE=10
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
# NON_INTERACTIVE=1  # 默认已启用非交互模式
```

### 2. 构建和运行

```bash
docker-compose build
docker-compose up -d
```

### 3. 查看日志

```bash
docker-compose logs -f
```

**注意**：项目默认使用非交互模式，适合云端部署，无需手动配置。

## 文档

### 部署文档
- **`DOCKER_DEPLOYMENT_GUIDE.md`** - Docker云端部署完整指南 ⭐
- `BINANCE_SETUP.md` - 币安配置指南
- `DEPLOYMENT_CHECKLIST.md` - 部署检查清单
- `DEPLOYMENT_SUMMARY.md` - 部署总结

### 使用文档
- `docs/QUICK_START_LIVE.md` - 快速开始
- `docs/OKX_DEMO_SETUP.md` - OKX配置
- `docs/LIVE_TRADING_V52_GUIDE.md` - 交易指南

## 重要提示

⚠️ **风险警告**：
- 杠杆交易风险极大，可能导致资金损失
- 建议先用测试网/模拟环境测试
- 小资金实盘测试，逐步增加

⚠️ **安全提示**：
- 不要提交 `.env` 文件到Git
- 不要开启API密钥的"提现"权限
- 定期检查API使用情况
