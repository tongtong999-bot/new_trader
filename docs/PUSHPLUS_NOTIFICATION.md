# PushPlus Webhook 交易通知配置

## 功能说明

代码已集成 PushPlus Webhook 通知功能，会在以下情况发送通知：

1. **开仓**：当策略发出开仓信号并成功下单时
2. **平仓**：当策略平仓时（包含盈亏信息）
3. **止损触发**：当价格触发止损时
4. **止盈触发**：当价格触发止盈时

## 配置方式

### 方式1：PushPlus Token（推荐）

1. 访问 [PushPlus 官网](http://www.pushplus.plus/) 注册账号
2. 获取你的 Token
3. （可选）创建群组并获取群组ID或群组名称
4. 在 `.env` 文件中配置：

```bash
PUSHPLUS_WEBHOOK=你的Token
PUSHPLUS_TOPIC=你的群组ID或群组名称  # 可选，如果不配置则发送到个人
```

代码会自动识别 Token 格式，使用 PushPlus API 发送通知。如果配置了 `PUSHPLUS_TOPIC`，消息会发送到指定的群组。

### 方式2：自定义 Webhook URL

如果你有自己的 Webhook 服务，可以直接配置完整 URL：

```bash
PUSHPLUS_WEBHOOK=https://your-webhook-url.com/api/notify
```

代码会向该 URL 发送 POST 请求，JSON 格式：

```json
{
  "title": "📈 开仓成功 - BTC/USDT:USDT",
  "content": "交易对: BTC/USDT:USDT\n模式: 模拟交易\n...",
  "type": "entry",
  "symbol": "BTC/USDT:USDT",
  "mode": "模拟交易",
  "timestamp": "2025-12-17T12:00:00"
}
```

## Docker Compose 配置

在 `.env` 文件中添加：

```bash
# PushPlus 通知（可选）
PUSHPLUS_WEBHOOK=你的Token或Webhook URL
PUSHPLUS_TOPIC=你的群组ID或群组名称  # 可选，发送到群组
```

然后重启容器：

```bash
docker compose down
docker compose up -d
```

## 群组配置说明

### 如何获取群组ID或群组名称

1. 登录 PushPlus 官网
2. 进入"群组管理"或"消息推送"页面
3. 创建或选择一个群组
4. 获取群组ID（通常是数字）或群组名称

### 群组配置示例

```bash
# 发送到个人（默认）
PUSHPLUS_WEBHOOK=你的Token

# 发送到群组（使用群组ID）
PUSHPLUS_WEBHOOK=你的Token
PUSHPLUS_TOPIC=123456

# 发送到群组（使用群组名称）
PUSHPLUS_WEBHOOK=你的Token
PUSHPLUS_TOPIC=交易通知群
```

**注意**：如果不配置 `PUSHPLUS_TOPIC`，消息会发送到个人；如果配置了，消息会发送到指定的群组。

## 通知内容示例

### 开仓通知

```
【交易通知】📈 开仓成功 - BTC/USDT:USDT

交易对: BTC/USDT:USDT
模式: 模拟交易
时间: 2025-12-17 12:00:00

方向: LONG
订单ID: 12345678
入场价: 50000.00
数量: 0.01
止损: 49000.00
止盈: 55000.00
仓位: 500.00 USDT
市场状态: trending_up
大趋势: bullish
```

### 平仓通知

```
【交易通知】📉 平仓成功 - BTC/USDT:USDT

交易对: BTC/USDT:USDT
模式: 模拟交易
时间: 2025-12-17 14:00:00

原因: 止盈
订单ID: 12345679
入场价: 50000.00
出场价: 55000.00
盈亏: ✅ +5000.00 (+10.00%)
```

### 止损/止盈触发通知

```
【交易通知】🛑 止损触发 - BTC/USDT:USDT

交易对: BTC/USDT:USDT
模式: 模拟交易
时间: 2025-12-17 13:00:00

触发: 止损
入场价: 50000.00
止损价: 49000.00
盈亏: ❌ -1000.00 (-2.00%)
```

## 注意事项

1. **不配置则不发送**：如果未设置 `PUSHPLUS_WEBHOOK`，代码会跳过通知，不影响交易
2. **失败不影响交易**：如果通知发送失败，只会记录警告日志，不会影响交易执行
3. **隐私安全**：不要将 Token 提交到 GitHub，只放在 `.env` 文件中（已在 `.gitignore` 中忽略）

## 测试通知

配置后，当有交易发生时，会自动发送通知。你也可以在代码中添加测试通知来验证配置是否正确。
