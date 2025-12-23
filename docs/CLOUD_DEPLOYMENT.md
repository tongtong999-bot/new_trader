# 云服务器部署指南（Ubuntu 22.04/24.04）

本文档适用于当前仓库结构（核心文件：`live_trading_v52.py`、`multi_symbol_trading.py`、`strategies/box_strategy_v5_2.py`）。

## 0. 前置要求

- 一台 Ubuntu 云服务器（建议 2C/4G 起）
- 已开放 SSH 登录
- 服务器能访问 `api.okx.com`（必要时配置代理）

## 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

## 2. 拉取代码

把仓库拉到服务器某个目录（示例：`/opt/my_trading_system`）：

```bash
sudo mkdir -p /opt/my_trading_system
sudo chown -R $USER:$USER /opt/my_trading_system

cd /opt
git clone https://github.com/tongtong999-bot/my_trading_system.git
cd /opt/my_trading_system
```

## 3. 创建虚拟环境并安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. 配置环境变量（不要写进代码/不要提交）

### 4.1 OKX 密钥

必须通过环境变量提供：

```bash
export OKX_API_KEY="YOUR_OKX_API_KEY"
export OKX_API_SECRET="YOUR_OKX_API_SECRET"
export OKX_PASSPHRASE="YOUR_OKX_PASSPHRASE"  # 没有可留空
```

### 4.2 代理（可选）

如果服务器需要代理才能访问 OKX：

```bash
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

说明：如果你使用的是本机代理转发到服务器，需要你自己在服务器上部署对应的代理服务或隧道。

## 5. 直接运行验证（前台）

### 5.1 单币种

```bash
cd /opt/my_trading_system
source venv/bin/activate
python3 live_trading_v52.py
```

### 5.2 多币种

```bash
cd /opt/my_trading_system
source venv/bin/activate
python3 multi_symbol_trading.py
```

## 6. 长期运行（systemd 守护进程，推荐）

### 6.1 创建 systemd service（单币种示例）

创建文件：`/etc/systemd/system/my_trading_system.service`

```ini
[Unit]
Description=my_trading_system v5.2 trading bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/my_trading_system
ExecStart=/opt/my_trading_system/venv/bin/python3 /opt/my_trading_system/live_trading_v52.py
Restart=always
RestartSec=10

# 关键：通过环境变量注入密钥（不要写在代码里）
Environment=OKX_API_KEY=YOUR_OKX_API_KEY
Environment=OKX_API_SECRET=YOUR_OKX_API_SECRET
Environment=OKX_PASSPHRASE=YOUR_OKX_PASSPHRASE

# 可选：代理
# Environment=HTTP_PROXY=http://127.0.0.1:7890
# Environment=HTTPS_PROXY=http://127.0.0.1:7890

# 日志
StandardOutput=append:/opt/my_trading_system/live_trading_v52.log
StandardError=append:/opt/my_trading_system/live_trading_v52.log

[Install]
WantedBy=multi-user.target
```

注意：把 `YOUR_...` 替换为真实值。

### 6.2 启动与自启

```bash
sudo systemctl daemon-reload
sudo systemctl enable my_trading_system
sudo systemctl start my_trading_system
```

### 6.3 查看状态与日志

```bash
sudo systemctl status my_trading_system --no-pager

# systemd 日志
journalctl -u my_trading_system -f

# 业务日志（文件）
tail -f /opt/my_trading_system/live_trading_v52.log
```

### 6.4 停止/重启

```bash
sudo systemctl stop my_trading_system
sudo systemctl restart my_trading_system
```

## 7. 更新代码（不丢服务）

```bash
cd /opt/my_trading_system
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart my_trading_system
```

## 8. 安全清单（必须遵守）

- 不要给 API 开启提币权限
- 不要把真实密钥写进仓库、脚本、文档
- 仅在服务器上以环境变量或 systemd Environment 注入
- 建议为服务器开启防火墙，仅放行 SSH（以及你确实需要的端口）

## 9. 常见故障

- 连接超时/无法访问 OKX：确认服务器网络与 DNS；必要时配置代理
- 认证失败：检查 `OKX_API_KEY/OKX_API_SECRET/OKX_PASSPHRASE` 是否正确，且 passphrase 使用半角字符
- 进程自动退出：用 `journalctl -u my_trading_system -f` 看退出原因
