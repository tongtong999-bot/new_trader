# 部署检查清单

## ✅ 代码修改完成

### 1. 币安支持
- [x] 添加币安交易所支持（`live_trading_v52.py`）
- [x] 添加币安杠杆设置功能
- [x] 添加交易对格式转换（币安格式：BTCUSDT）
- [x] 修改配置类支持币安（`LiveTradingConfig`）

### 2. 交互环节检查
- [x] 检查所有Python文件，确认无 `input()` 调用
- [x] 所有配置通过环境变量
- [x] 无交互式提示

### 3. Docker配置
- [x] 更新 `Dockerfile`
- [x] 更新 `docker-compose.yml` 支持币安配置
- [x] 创建 `.env.example` 文件

### 4. 文档
- [x] 创建 `BINANCE_SETUP.md` 配置指南
- [x] 更新 `README.md`

---

## 📋 部署前检查

### 1. 环境变量配置

确保 `.env` 文件包含所有必要配置：

```bash
# 交易所
EXCHANGE=binance

# 币安API
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret

# 交易配置
LEVERAGE=10
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
```

### 2. 代码检查

- [ ] 确认所有文件已提交到Git
- [ ] 确认 `.env` 文件已添加到 `.gitignore`
- [ ] 确认无敏感信息泄露

### 3. Docker检查

- [ ] 测试Docker构建：`docker-compose build`
- [ ] 测试Docker运行：`docker-compose up -d`
- [ ] 检查日志：`docker-compose logs -f`

---

## 🚀 部署步骤

### 1. 克隆代码

```bash
git clone https://github.com/your-username/my_trading_system.git
cd my_trading_system
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入API密钥
```

### 3. Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 4. 验证运行

- [ ] 检查日志无错误
- [ ] 检查API连接成功
- [ ] 检查交易信号生成正常

---

## ⚠️ 注意事项

1. **API密钥安全**：
   - 不要提交 `.env` 到Git
   - 不要开启"提现"权限
   - 定期检查API使用情况

2. **测试建议**：
   - 先用测试网测试（`USE_DEMO_TRADING=true`）
   - 小资金实盘测试
   - 降低杠杆测试（5倍）

3. **监控建议**：
   - 设置PushPlus通知
   - 定期检查交易记录
   - 监控账户余额

---

## 📝 文件清单

### 已修改的文件
- `live_trading_v52.py` - 添加币安支持
- `docker-compose.yml` - 更新环境变量
- `.env.example` - 添加币安配置示例

### 新增的文件
- `BINANCE_SETUP.md` - 币安配置指南
- `DEPLOYMENT_CHECKLIST.md` - 部署检查清单

### 需要检查的文件
- `.gitignore` - 确保包含 `.env`
- `requirements.txt` - 确保包含所有依赖

---

## 🔍 验证清单

部署后验证：

- [ ] 代码无语法错误
- [ ] 环境变量正确加载
- [ ] 交易所连接成功
- [ ] 杠杆设置成功
- [ ] 交易信号生成正常
- [ ] 日志记录正常
- [ ] 通知功能正常（如配置）

---

## 📞 问题排查

### 连接失败
- 检查API密钥是否正确
- 检查网络连接
- 检查代理配置（如需要）

### 杠杆设置失败
- 检查币安账户是否开通合约
- 检查杠杆倍数是否在允许范围内（1-125）

### 交易失败
- 检查账户余额是否充足
- 检查币种格式是否正确
- 检查交易对是否存在
