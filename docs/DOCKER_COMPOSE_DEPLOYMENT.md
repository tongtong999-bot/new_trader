# Docker Compose 部署（云端）

本项目是一个常驻运行的交易机器人。Docker/Compose 只负责进程托管与重启，不会提供任何密钥管理。

## 1. 服务器准备

- Ubuntu 22.04/24.04
- 安装 Docker 与 Compose Plugin

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

（可选）免 sudo：

```bash
sudo usermod -aG docker $USER
# 重新登录后生效
```

## 2. 拉取代码

```bash
git clone https://github.com/tongtong999-bot/my_trading_system.git
cd my_trading_system
```

## 3. 配置环境变量（不要提交到仓库）

在仓库目录创建 `.env`（此文件已被 `.gitignore`/`.dockerignore` 忽略）：

```bash
cat > .env <<'EOF'
# OKX 密钥（必需）
OKX_API_KEY=YOUR_OKX_API_KEY
OKX_API_SECRET=YOUR_OKX_API_SECRET
OKX_PASSPHRASE=YOUR_OKX_PASSPHRASE

# 交易配置（单币种模式）
TRADING_SYMBOL=BTC/USDT:USDT
TRADING_MODE=demo  # demo=OKX模拟交易, paper=本地模拟盘, live=实盘

# 运行时长限制（小时）：0或负数=无限制（推荐云端部署），默认24小时
MAX_RUNTIME_HOURS=0  # 0=无限制，24=24小时后停止，168=一周后停止

# 交易配置（多币种模式，如果使用 multi_symbol_trading.py）
# TRADING_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT

# 可选：代理
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890

# 可选：时区
TZ=Asia/Shanghai
EOF
```

## 4. 启动（单币种，默认，非交互模式）

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f --tail=200
```

停止：

```bash
docker compose down
```

**注意**：代码已修复交互问题，使用 `--non-interactive` 标志和环境变量，不会阻塞等待用户输入。

## 5. 切换为多币种

编辑 `docker-compose.yml`，修改 `command` 行：

```yaml
command: ["python", "-u", "multi_symbol_trading.py", "--non-interactive"]
```

并在 `.env` 中配置 `TRADING_SYMBOLS`（见上方示例）。

然后重启：

```bash
docker compose up -d
```

## 6. 命令行参数（可选）

你也可以通过命令行参数覆盖环境变量：

```bash
# 单币种，指定交易对
docker compose run --rm bot python -u live_trading_v52.py --non-interactive --symbol ETH/USDT:USDT --demo

# 多币种，指定币种列表
docker compose run --rm bot python -u multi_symbol_trading.py --non-interactive --symbols BTC/USDT:USDT ETH/USDT:USDT --demo
```

## 7. 更新代码

```bash
git pull
docker compose up -d --build
```

## 8. 关键风险

- 任何提交到 GitHub 的 `.env` 都是泄露。
- 机器人需要持续网络；容器重启不会恢复交易所端的风控设置。
