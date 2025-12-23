# 云端部署快速指南

## 项目位置

**文件夹**：`new trader`

**路径**：`/Users/cast/my_trading_system/new trader`

## 默认配置

✅ **默认非交互模式**：项目已配置为默认非交互模式，适合云端部署

✅ **支持币安和OKX**：通过 `EXCHANGE` 环境变量选择

✅ **Docker就绪**：完整的Docker配置，可直接部署

## 快速部署（3步）

### 1. 配置环境变量

```bash
cd "/Users/cast/my_trading_system/new trader"
cp .env.example .env
nano .env  # 编辑配置文件
```

**币安配置示例：**
```bash
EXCHANGE=binance
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
LEVERAGE=10
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
```

### 2. Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务（默认非交互模式）
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 3. 验证运行

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs --tail=50
```

## 直接运行（非Docker）

```bash
# 设置环境变量
export EXCHANGE=binance
export BINANCE_API_KEY=your_key
export BINANCE_SECRET_KEY=your_secret
export LEVERAGE=10

# 运行（默认非交互模式）
python3 live_trading_v52.py
# 或
python3 multi_symbol_trading.py
```

## 重要提示

### 默认非交互模式

- ✅ 项目默认使用非交互模式
- ✅ 无需添加 `--non-interactive` 参数
- ✅ 所有配置通过环境变量
- ✅ 适合云端部署

### 如需交互模式（不推荐云端）

```bash
# 设置环境变量
export NON_INTERACTIVE=0

# 运行
python3 live_trading_v52.py
```

## 文档

- **`DOCKER_DEPLOYMENT_GUIDE.md`** - 完整Docker部署指南
- `DEFAULT_NON_INTERACTIVE.md` - 默认非交互模式说明
- `BINANCE_SETUP.md` - 币安配置指南
- `PROJECT_INFO.md` - 项目信息

---

**创建时间**：2025-12-21
**默认模式**：非交互模式（适合云端部署）
