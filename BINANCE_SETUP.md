# 币安实盘交易配置指南

## 一、快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 使用币安交易所
EXCHANGE=binance

# 币安API密钥
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here

# 交易配置
TRADING_MODE=live
USE_DEMO_TRADING=false  # false=实盘, true=测试网
LEVERAGE=10

# 币种列表（每个币种10U）
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
```

### 2. 创建币安API密钥

1. 登录币安
2. 进入"API管理"
3. 创建新API密钥
4. **重要**：只开启"合约交易"权限，**不要开启"提现"权限**
5. 保存API Key和Secret Key

### 3. 运行

**Docker方式（推荐）：**

```bash
docker-compose up -d
```

**直接运行：**

```bash
python multi_symbol_trading.py
```

---

## 二、Docker部署

### 1. 准备环境变量文件

创建 `.env` 文件（不要提交到Git）：

```bash
EXCHANGE=binance
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
LEVERAGE=10
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
```

### 2. 构建和运行

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 3. 更新配置

修改 `.env` 文件后，重启服务：

```bash
docker-compose restart
```

---

## 三、资金分配

### 总资金：200 USDT

**分配方式：**
- 每个币种：10 USDT
- 支持币种数：20个币种
- 杠杆倍数：10倍
- **实际交易金额**：每个币种100 USDT（10U × 10倍）

**每个币种的资金池分配：**
- 趋势资金池：5 USDT（实际可交易50 USDT）
- 网格资金池：5 USDT（实际可交易50 USDT）

---

## 四、重要注意事项

### ⚠️ 风险警告

1. **杠杆风险极大**：
   - 10倍杠杆意味着10倍收益，也意味着10倍亏损
   - 如果价格反向移动10%，你的10U本金就全部亏完
   - **强烈建议先用5倍杠杆测试**

2. **资金管理**：
   - 200U分成20个币种，每个币种只有10U
   - 如果某个币种亏损，最多亏10U
   - 但如果有多个币种同时亏损，总亏损可能超过预期

3. **合约风险**：
   - 合约交易有强制平仓风险
   - 如果保证金不足，会被强制平仓
   - **建议设置止损，控制风险**

### ⚠️ 安全建议

1. **API密钥安全**：
   - 不要提交 `.env` 文件到Git
   - 不要开启"提现"权限
   - 定期检查API密钥使用情况

2. **测试建议**：
   - 先用币安测试网测试（`USE_DEMO_TRADING=true`）
   - 小资金实盘测试（50U，5个币种）
   - 降低杠杆测试（5倍杠杆）

3. **监控建议**：
   - 设置PushPlus通知
   - 定期检查交易记录
   - 监控账户余额

---

## 五、环境变量说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `EXCHANGE` | 交易所（binance/okx） | `binance` |
| `BINANCE_API_KEY` | 币安API Key | `your_key` |
| `BINANCE_SECRET_KEY` | 币安Secret Key | `your_secret` |
| `TRADING_MODE` | 交易模式（live/paper） | `live` |
| `USE_DEMO_TRADING` | 是否使用测试网 | `false` |
| `LEVERAGE` | 杠杆倍数 | `10` |
| `SYMBOLS` | 币种列表（逗号分隔） | `BTC/USDT:USDT,ETH/USDT:USDT` |
| `PUSHPLUS_WEBHOOK` | PushPlus Token | `your_token` |
| `PUSHPLUS_TOPIC` | PushPlus群组 | `your_topic` |

---

## 六、常见问题

### Q1: 如何测试币安连接？

**A:** 设置 `USE_DEMO_TRADING=true` 使用币安测试网。

### Q2: 杠杆如何设置？

**A:** 通过环境变量 `LEVERAGE=10` 设置。币安会自动为每个币种设置杠杆。

### Q3: 如何添加更多币种？

**A:** 修改 `.env` 文件中的 `SYMBOLS`，添加更多币种（逗号分隔）。

### Q4: 如何查看交易日志？

**A:** 
- Docker: `docker-compose logs -f`
- 直接运行: 查看 `logs/` 目录

### Q5: 如何停止交易？

**A:** 
- Docker: `docker-compose down`
- 直接运行: `Ctrl+C`

---

## 七、技术支持

如有问题，请检查：
1. API密钥是否正确
2. 网络连接是否正常
3. 日志文件中的错误信息
