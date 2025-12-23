# Docker 云端部署完整指南

## 目录

1. [准备工作](#准备工作)
2. [服务器环境要求](#服务器环境要求)
3. [部署步骤](#部署步骤)
4. [配置说明](#配置说明)
5. [运行和管理](#运行和管理)
6. [监控和日志](#监控和日志)
7. [常见问题](#常见问题)
8. [安全建议](#安全建议)

---

## 准备工作

### 1. 获取API密钥

#### 币安API密钥

1. 登录币安
2. 进入"API管理"
3. 创建新API密钥
4. **重要**：只开启"合约交易"权限，**不要开启"提现"权限**
5. 保存API Key和Secret Key

#### OKX API密钥

1. 登录OKX
2. 进入"API管理"
3. 创建新API密钥
4. 设置Passphrase（记住，后续需要用到）
5. **重要**：只开启"交易"权限，**不要开启"提现"权限**

### 2. 准备服务器

- 云服务器（推荐：Ubuntu 20.04+ / CentOS 7+）
- 至少2GB内存
- 至少10GB磁盘空间
- 稳定的网络连接

---

## 服务器环境要求

### 1. 安装Docker

**Ubuntu/Debian:**

```bash
# 更新系统
sudo apt-get update

# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
```

**CentOS/RHEL:**

```bash
# 安装Docker
sudo yum install -y docker

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
```

### 2. 安装Docker Compose

```bash
# 下载Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 添加执行权限
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

### 3. 安装Git（如果还没有）

```bash
# Ubuntu/Debian
sudo apt-get install -y git

# CentOS/RHEL
sudo yum install -y git
```

---

## 部署步骤

### 步骤1：克隆代码

```bash
# 创建项目目录
mkdir -p ~/trading_system
cd ~/trading_system

# 克隆代码（替换为你的GitHub仓库地址）
git clone https://github.com/your-username/my_trading_system.git .

# 或者如果代码已经在服务器上，直接进入目录
cd /path/to/my_trading_system
```

### 步骤2：配置环境变量

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑环境变量文件
nano .env
# 或使用 vim
vim .env
```

**配置示例（币安）：**

```bash
# 交易所配置
EXCHANGE=binance

# 币安API配置
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here

# 交易配置
TRADING_MODE=live
USE_DEMO_TRADING=false
LEVERAGE=10
MAX_RUNTIME_HOURS=0

# 币种列表（每个币种10U）
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT,LTC/USDT:USDT,BCH/USDT:USDT,AVAX/USDT:USDT,ADA/USDT:USDT,DOT/USDT:USDT,BNB/USDT:USDT,SUI/USDT:USDT,AAVE/USDT:USDT,LINK/USDT:USDT,UNI/USDT:USDT,ICP/USDT:USDT

# 通知配置（可选）
PUSHPLUS_WEBHOOK=your_pushplus_token
PUSHPLUS_TOPIC=your_topic

# 代理配置（如果需要）
# HTTP_PROXY=http://proxy.example.com:8080
# HTTPS_PROXY=http://proxy.example.com:8080
```

**配置示例（OKX）：**

```bash
# 交易所配置
EXCHANGE=okx

# OKX API配置
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_secret_key_here
OKX_PASSPHRASE=your_okx_passphrase_here

# 交易配置
TRADING_MODE=live
USE_DEMO_TRADING=false
LEVERAGE=10
MAX_RUNTIME_HOURS=0

# 币种列表
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT

# 通知配置（可选）
PUSHPLUS_WEBHOOK=your_pushplus_token
PUSHPLUS_TOPIC=your_topic
```

### 步骤3：构建Docker镜像

```bash
# 在项目根目录执行
docker-compose build

# 如果构建成功，会看到类似输出：
# Successfully built xxxxxx
# Successfully tagged my_trading_system_bot:latest
```

### 步骤4：启动服务

```bash
# 启动服务（后台运行）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 应该看到类似输出：
# NAME                    STATUS              PORTS
# my_trading_system_bot   Up X seconds
```

### 步骤5：验证运行

```bash
# 查看日志（实时）
docker-compose logs -f

# 应该看到类似输出：
# 2025-12-21 10:00:00 - INFO - 交易机器人初始化完成
# 2025-12-21 10:00:01 - INFO - ✓ 交易所连接成功
# 2025-12-21 10:00:02 - INFO - 开始监控交易信号...
```

---

## 配置说明

### 环境变量详解

| 变量名 | 说明 | 示例 | 必填 |
|--------|------|------|------|
| `EXCHANGE` | 交易所（binance/okx） | `binance` | ✅ |
| `BINANCE_API_KEY` | 币安API Key | `your_key` | 币安必填 |
| `BINANCE_SECRET_KEY` | 币安Secret Key | `your_secret` | 币安必填 |
| `OKX_API_KEY` | OKX API Key | `your_key` | OKX必填 |
| `OKX_API_SECRET` | OKX Secret Key | `your_secret` | OKX必填 |
| `OKX_PASSPHRASE` | OKX Passphrase | `your_passphrase` | OKX必填 |
| `TRADING_MODE` | 交易模式（live/paper/demo） | `live` | ✅ |
| `USE_DEMO_TRADING` | 是否使用测试网 | `false` | ✅ |
| `LEVERAGE` | 杠杆倍数 | `10` | 可选 |
| `MAX_RUNTIME_HOURS` | 最大运行时长（0=无限制） | `0` | 可选 |
| `SYMBOLS` | 币种列表（逗号分隔） | `BTC/USDT:USDT,ETH/USDT:USDT` | ✅ |
| `PUSHPLUS_WEBHOOK` | PushPlus Token | `your_token` | 可选 |
| `PUSHPLUS_TOPIC` | PushPlus群组 | `your_topic` | 可选 |
| `HTTP_PROXY` | HTTP代理 | `http://proxy:8080` | 可选 |
| `HTTPS_PROXY` | HTTPS代理 | `http://proxy:8080` | 可选 |

### 单币种 vs 多币种

**单币种模式（默认）：**

```bash
# docker-compose.yml 中默认使用（默认非交互模式）
command: ["python", "-u", "live_trading_v52.py"]
```

**多币种模式：**

修改 `docker-compose.yml`：

```yaml
command: ["python", "-u", "multi_symbol_trading.py"]
```

**注意**：项目默认使用非交互模式，无需添加 `--non-interactive` 参数。

并在 `.env` 中配置 `SYMBOLS`：

```bash
SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
```

---

## 运行和管理

### 启动服务

```bash
# 启动服务
docker-compose up -d

# 启动并查看日志
docker-compose up
```

### 停止服务

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

### 重启服务

```bash
# 重启服务
docker-compose restart

# 重新构建并启动
docker-compose up -d --build
```

### 更新代码

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker-compose build

# 重启服务
docker-compose restart
```

### 查看服务状态

```bash
# 查看容器状态
docker-compose ps

# 查看容器资源使用
docker stats my_trading_system_bot

# 进入容器（调试用）
docker-compose exec bot bash
```

---

## 监控和日志

### 查看日志

```bash
# 实时查看日志
docker-compose logs -f

# 查看最近100行日志
docker-compose logs --tail=100

# 查看特定时间的日志
docker-compose logs --since="2025-12-21T10:00:00"

# 查看日志文件（在宿主机上）
tail -f logs/multi_symbol_*.log
tail -f live_trading_v52.log
```

### 日志文件位置

- **容器内**：`/app/logs/` 和 `/app/live_trading_v52.log`
- **宿主机**：`./logs/` 和 `./live_trading_v52.log`（通过volume挂载）

### 监控资源使用

```bash
# 查看容器资源使用
docker stats my_trading_system_bot

# 查看磁盘使用
docker system df

# 查看容器详细信息
docker inspect my_trading_system_bot
```

### 设置日志轮转

创建 `logrotate` 配置（可选）：

```bash
# 创建logrotate配置
sudo nano /etc/logrotate.d/trading-system
```

内容：

```
/path/to/my_trading_system/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
```

---

## 常见问题

### 1. 容器无法启动

**问题**：容器启动后立即退出

**排查步骤**：

```bash
# 查看容器日志
docker-compose logs

# 查看容器退出代码
docker-compose ps -a

# 检查环境变量
docker-compose config
```

**常见原因**：
- API密钥配置错误
- 环境变量缺失
- 网络连接问题

**解决方案**：
- 检查 `.env` 文件配置
- 确认API密钥正确
- 检查网络连接

### 2. 无法连接交易所

**问题**：日志显示连接失败

**排查步骤**：

```bash
# 查看详细日志
docker-compose logs | grep -i "连接\|connect\|error"

# 测试网络连接
docker-compose exec bot ping api.binance.com
```

**常见原因**：
- 网络问题
- 需要代理
- API密钥错误

**解决方案**：
- 配置代理（如果需要）
- 检查API密钥
- 检查防火墙设置

### 3. 杠杆设置失败

**问题**：日志显示杠杆设置失败

**排查步骤**：

```bash
# 查看杠杆设置相关日志
docker-compose logs | grep -i "杠杆\|leverage"
```

**常见原因**：
- 币安账户未开通合约
- 杠杆倍数超出限制
- API权限不足

**解决方案**：
- 确认账户已开通合约交易
- 检查杠杆倍数（1-125）
- 确认API权限正确

### 4. 内存不足

**问题**：容器频繁重启，日志显示OOM

**排查步骤**：

```bash
# 查看内存使用
docker stats my_trading_system_bot

# 查看系统内存
free -h
```

**解决方案**：
- 增加服务器内存
- 减少币种数量
- 优化代码

### 5. 磁盘空间不足

**问题**：日志显示磁盘空间不足

**排查步骤**：

```bash
# 查看磁盘使用
df -h

# 查看Docker占用
docker system df

# 清理Docker
docker system prune -a
```

**解决方案**：
- 清理日志文件
- 清理Docker镜像
- 增加磁盘空间

### 6. 时区问题

**问题**：日志时间不正确

**解决方案**：

在 `docker-compose.yml` 中设置时区：

```yaml
environment:
  TZ: Asia/Shanghai  # 或你的时区
```

或在 `.env` 中设置：

```bash
TZ=Asia/Shanghai
```

---

## 安全建议

### 1. API密钥安全

- ✅ 不要将 `.env` 文件提交到Git
- ✅ 定期更换API密钥
- ✅ 只开启必要的API权限（合约交易）
- ✅ **不要开启"提现"权限**

### 2. 服务器安全

- ✅ 使用SSH密钥登录，禁用密码登录
- ✅ 配置防火墙，只开放必要端口
- ✅ 定期更新系统和Docker
- ✅ 使用非root用户运行Docker（可选）

### 3. 网络安全

- ✅ 使用HTTPS代理（如果需要）
- ✅ 配置VPN（如果需要）
- ✅ 监控异常网络活动

### 4. 数据备份

- ✅ 定期备份日志文件
- ✅ 备份配置文件（不含密钥）
- ✅ 使用Git管理代码版本

### 5. 监控告警

- ✅ 配置PushPlus通知
- ✅ 监控容器运行状态
- ✅ 设置资源使用告警

---

## 高级配置

### 1. 使用systemd管理（可选）

创建systemd服务文件：

```bash
sudo nano /etc/systemd/system/trading-bot.service
```

内容：

```ini
[Unit]
Description=Trading Bot Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/my_trading_system
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

### 2. 自动重启策略

Docker Compose已配置 `restart: unless-stopped`，容器会自动重启。

### 3. 资源限制

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  bot:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 4. 健康检查

添加健康检查（可选）：

```yaml
services:
  bot:
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

---

## 快速参考

### 常用命令

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看状态
docker-compose ps

# 更新代码
git pull && docker-compose build && docker-compose restart

# 进入容器
docker-compose exec bot bash

# 查看资源使用
docker stats my_trading_system_bot
```

### 配置文件位置

- 环境变量：`.env`
- Docker配置：`docker-compose.yml`
- 日志文件：`./logs/` 和 `./live_trading_v52.log`

---

## 故障排查流程

1. **检查容器状态**
   ```bash
   docker-compose ps
   ```

2. **查看日志**
   ```bash
   docker-compose logs --tail=100
   ```

3. **检查环境变量**
   ```bash
   docker-compose config
   ```

4. **测试网络连接**
   ```bash
   docker-compose exec bot ping api.binance.com
   ```

5. **检查资源使用**
   ```bash
   docker stats my_trading_system_bot
   ```

6. **查看系统日志**
   ```bash
   journalctl -u docker -n 50
   ```

---

## 总结

完成以上步骤后，你的交易系统应该已经在云端服务器上运行了。

**关键点**：
- ✅ 确保API密钥正确配置
- ✅ 确保网络连接正常
- ✅ 定期检查日志
- ✅ 监控资源使用
- ✅ 保持代码更新

**下一步**：
- 监控交易运行情况
- 根据实际情况调整参数
- 定期检查账户余额
- 关注交易信号和通知

---

**最后更新：** 2025-12-21

如有问题，请查看日志文件或联系技术支持。
