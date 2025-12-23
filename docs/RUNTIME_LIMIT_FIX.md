# 运行时长限制修复说明

## 问题

原代码中设置了 `max_runtime_hours = 24`，导致机器人运行24小时后自动停止。这对于云端长期部署不适用。

## 修复

### 1. 添加环境变量支持

现在可以通过环境变量 `MAX_RUNTIME_HOURS` 配置运行时长限制：

- `MAX_RUNTIME_HOURS=0` 或 `MAX_RUNTIME_HOURS=-1`：无限制（永久运行）
- `MAX_RUNTIME_HOURS=24`：运行24小时后停止（默认）
- `MAX_RUNTIME_HOURS=168`：运行一周后停止

### 2. Docker Compose 配置

在 `docker-compose.yml` 中已设置默认值为 `0`（无限制）：

```yaml
MAX_RUNTIME_HOURS: ${MAX_RUNTIME_HOURS:-0}  # 0 = unlimited
```

### 3. 使用方式

#### 方式1：环境变量（推荐）

在 `.env` 文件中：

```bash
# 无限制运行（推荐用于云端部署）
MAX_RUNTIME_HOURS=0

# 或运行一周后停止
MAX_RUNTIME_HOURS=168
```

#### 方式2：Docker Compose

```bash
# 无限制
MAX_RUNTIME_HOURS=0 docker compose up -d

# 或修改 .env 文件
```

#### 方式3：systemd（如果使用 systemd 部署）

在 systemd service 文件中添加：

```ini
Environment=MAX_RUNTIME_HOURS=0
```

## 注意事项

- **云端部署建议**：设置 `MAX_RUNTIME_HOURS=0`（无限制），让 Docker/systemd 管理进程重启
- **测试环境**：可以设置较短的时间限制，如 `MAX_RUNTIME_HOURS=1`（1小时）
- **代码逻辑**：如果 `max_runtime_hours <= 0`，代码不会检查运行时长，会一直运行直到手动停止或进程被终止
