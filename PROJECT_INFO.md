# 项目信息

## 项目位置

**文件夹名称**：`new trader`

**完整路径**：`/Users/cast/my_trading_system/new trader`

## 项目特点

### ✅ 默认非交互模式

- 所有脚本默认使用非交互模式
- 适合云端部署，无需手动交互
- 所有配置通过环境变量

### ✅ 支持币安和OKX

- 通过 `EXCHANGE` 环境变量选择交易所
- 币安和OKX配置示例已包含

### ✅ Docker部署就绪

- 完整的Docker配置
- 详细的部署文档
- 默认非交互模式，容器启动后自动运行

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
nano .env  # 编辑配置文件
```

### 2. 直接运行

```bash
# 单币种（默认非交互）
python3 live_trading_v52.py

# 多币种（默认非交互）
python3 multi_symbol_trading.py
```

### 3. Docker部署

```bash
docker-compose build
docker-compose up -d
docker-compose logs -f
```

## 文档

- `DOCKER_DEPLOYMENT_GUIDE.md` - Docker云端部署完整指南
- `DEFAULT_NON_INTERACTIVE.md` - 默认非交互模式说明
- `BINANCE_SETUP.md` - 币安配置指南
- `README.md` - 项目说明

## 重要提示

⚠️ **默认非交互模式**
- 项目已配置为默认非交互模式
- 适合云端部署，无需手动交互
- 如需交互模式，设置 `NON_INTERACTIVE=0`（不推荐）

⚠️ **安全提示**
- 不要提交 `.env` 文件到Git
- 不要开启API密钥的"提现"权限
- 定期检查API使用情况

---

**创建时间**：2025-12-21
**默认模式**：非交互模式（适合云端部署）
