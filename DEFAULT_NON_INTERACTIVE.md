# 默认非交互模式说明

## 更新内容

项目已更新为**默认非交互模式**，适合云端部署。

### 主要变更

1. **默认非交互模式**
   - `live_trading_v52.py` 和 `multi_symbol_trading.py` 默认使用非交互模式
   - 环境变量 `NON_INTERACTIVE` 默认值为 `1`（非交互）
   - 无需手动添加 `--non-interactive` 参数

2. **运行方式**

   **之前（需要手动指定）：**
   ```bash
   python3 live_trading_v52.py --non-interactive
   ```

   **现在（默认非交互）：**
   ```bash
   python3 live_trading_v52.py
   ```

3. **环境变量**

   在 `.env` 文件中：
   ```bash
   # 默认非交互模式（已设置）
   NON_INTERACTIVE=1
   
   # 如需交互模式（不推荐云端部署）
   NON_INTERACTIVE=0
   ```

### 优势

- ✅ **适合云端部署**：无需手动交互，自动运行
- ✅ **简化操作**：无需每次添加 `--non-interactive` 参数
- ✅ **Docker友好**：容器启动后自动运行，不会阻塞

### 使用说明

1. **直接运行（默认非交互）**
   ```bash
   python3 live_trading_v52.py
   python3 multi_symbol_trading.py
   ```

2. **Docker部署（默认非交互）**
   ```bash
   docker-compose up -d
   ```

3. **如需交互模式（不推荐）**
   ```bash
   # 设置环境变量
   export NON_INTERACTIVE=0
   python3 live_trading_v52.py
   
   # 或使用命令行参数
   python3 live_trading_v52.py --interactive  # 如果支持
   ```

### 配置说明

- **环境变量 `NON_INTERACTIVE`**：
  - `1` 或 `true` 或 `yes`：非交互模式（默认）
  - `0` 或 `false` 或 `no`：交互模式（不推荐云端部署）

- **命令行参数 `--non-interactive`**：
  - 如果指定，强制使用非交互模式
  - 如果未指定，使用环境变量默认值（`1`）

### 注意事项

⚠️ **云端部署必须使用非交互模式**
- 交互模式需要用户输入，不适合云端部署
- 默认非交互模式确保云端部署的稳定性

⚠️ **本地测试**
- 如需本地测试交互功能，可设置 `NON_INTERACTIVE=0`
- 但建议使用环境变量配置，而不是交互模式

---

**最后更新：** 2025-12-21
