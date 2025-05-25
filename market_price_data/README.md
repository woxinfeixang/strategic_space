# MT5 数据更新器模块 (market_price_data)

## 模块概述

`market_price_data` 是一个 Python 模块，设计用于与 MetaTrader 5 (MT5) 平台交互，以实现市场数据的获取、更新和存储。它支持历史 K 线数据的下载与增量更新，以及实时 K 线数据的轮询监控。

该模块旨在相对独立，但**依赖于项目 `core` 模块中的共享工具 (`core.utils`)** 来处理配置加载、日志记录、MT5 连接管理等通用任务。

## 模块内部架构

本模块遵循配置驱动和关注点分离的设计原则：

1.  **核心引擎 (`HistoryUpdater` & `RealtimeUpdater`):** 模块包含两个主要的工作引擎类，分别负责处理历史数据的批量下载/更新和实时数据的持续监控/写入。
2.  **配置驱动:** 模块的行为高度依赖于配置文件 (`config/updater.yaml` 与 `config/common.yaml` 的合并结果)。引擎类在初始化时加载配置，决定了操作目标（品种、周期）、数据存储位置、更新频率、重试逻辑等关键参数。
3.  **核心依赖 (`core.utils`):** 底层的、通用的功能（如 MT5 连接管理、日志记录、配置文件加载、文件路径构建、时间帧解析）被委托给项目共享的 `core.utils` 模块。这使得核心引擎可以专注于数据处理逻辑，提高了代码的可维护性和复用性。
4.  **数据流:** 数据从外部 MetaTrader 5 平台流入，经过核心引擎的处理（历史数据进行增量合并与原子写入，实时数据进行快照覆盖写入），最终存储在本地文件系统（当前为 CSV 格式，配置指定路径）。
5.  **并发模型 (`RealtimeUpdater`):** 为了高效处理多个品种和时间周期的实时监控，`RealtimeUpdater` 采用了多线程模型，为每个监控目标启动一个独立的 `threading.Thread`，实现并发轮询和数据写入。
6.  **辅助组件:**
    *   `exporters`: 提供将内部数据格式（DataFrame）转换为外部格式（MT5 CSV）的功能。
    *   `tools`: 包含一系列独立的、用于检查 MT5 状态的命令行脚本。
    *   `scripts`: 作为模块功能的执行入口，封装了实例化核心引擎类并调用其方法的逻辑，方便用户通过命令行或批处理文件启动更新任务。

## 核心组件详解

### 1. 历史数据更新 (`history.py` - `HistoryUpdater`)

此类负责从 MT5 获取并维护本地的历史 K 线数据 CSV 文件。其核心工作流程由 `run_update_cycle()` 方法驱动，该方法首先利用 `core.utils.initialize_mt5` 建立连接（如果需要），然后遍历配置 (`self.config`) 中 `historical.symbols` 和 `historical.timeframes` 指定的所有组合，并为每个组合调用 `update_symbol_timeframe`。

**针对单个品种-时间周期 (`update_symbol_timeframe`) 的详细更新步骤:**

1.  **确定数据获取起点 (`_get_fetch_start_time`):**
    *   首先，利用配置 (`self.config`) 中的路径模式和 `core.utils.get_filepath` 确定本地历史数据文件的路径。
    *   检查文件是否存在。如果存在且非空，读取最后一行以确定增量更新的起始时间戳。
    *   如果文件不存在或为空，根据配置 (`self.config`) 中的 `historical.start_date` 或 `historical.default_start_offsets` 确定首次下载的起始时间。

2.  **分块获取数据 (`_fetch_historical_data_chunked`):**
    *   根据起始时间和当前时间，以及配置 (`self.config.historical.batch_size_days`) 确定下载批次。
    *   循环调用 `mt5.copy_rates_range` 获取每个批次的数据。
    *   应用配置 (`self.config.historical`) 中定义的请求间隔和重试逻辑 (`_fetch_single_chunk_with_retries`)。

3.  **合并与原子化写入 (`_update_historical_file`):**
    *   读取旧数据（如果存在）。
    *   合并新旧数据，去重并排序。
    *   通过写入临时文件再重命名的原子操作，将最终数据写回磁盘，确保数据一致性。

4.  **数据校验 (`_verify_data_integrity` - 可选):**
    *   如果配置 (`self.config.historical.verify_integrity`) 启用，则对写入后的文件进行时间戳连续性等检查。

**总结:** `HistoryUpdater` 通过读取配置、调用核心工具、执行分块获取和原子写入，实现了高效且健壮的历史数据维护。

### 2. 实时数据采集 (`realtime.py` - `RealtimeUpdater`)

此类负责持续监控 MT5 的最新价格变动，并将 K 线数据的快照保存到本地。

**详细工作流程:**

1.  **启动 (`start_updater`):**
    *   检查交易日。
    *   调用 `core.utils.initialize_mt5` 建立连接 (依赖 `self.config.execution.mt5` 配置)。
    *   写入 PID 文件 (`_write_pid_file`)。
    *   根据配置 (`self.config.realtime.symbols`, `self.config.realtime.timeframes`)，利用 `threading.Thread` 为每个监控目标启动独立的 `_monitor_symbol_timeframe` 监控循环。

2.  **监控循环 (单个线程 - `_monitor_symbol_timeframe`):**
    *   检查停止信号 (`self._stop_event` 或 `STOP_REALTIME.flag` 文件)。
    *   调用 `mt5.copy_rates_from_pos` 获取最新的 `N` 条 K 线 (N 来自 `self.config.realtime.fetch_bars_count`)。
    *   数据转换 (NumPy 到 DataFrame, 时间戳处理)。
    *   利用配置 (`self.config.realtime`) 中的路径模式和 `core.utils.get_filepath` 确定输出文件路径。
    *   **覆盖写入** 最新的 N 条 K 线快照到 CSV 文件。
    *   根据配置 (`self.config.realtime.poll_intervals`, `self.config.realtime.default_poll_interval_seconds`) 确定轮询间隔，并使用 `self._stop_event.wait()` 进行等待，以便能及时响应停止信号。

3.  **停止 (`stop_updater`):**
    *   设置 `self._stop_event` 通知所有线程退出。
    *   等待线程结束 (`thread.join`)。
    *   调用 `core.utils.shutdown_mt5` 断开连接。
    *   删除 PID 文件 (`_delete_pid_file`)。

**总结:** `RealtimeUpdater` 利用配置、核心工具和多线程并发模型，实现了对多个目标的可配置轮询间隔的实时数据快照采集，并包含进程管理机制。

### 3. 命令行工具 (`scripts/data_updater.py`)

这是一个基于 `argparse` 的命令行界面 (CLI) 工具，提供了方便的方式来手动触发数据更新任务。

*   **`history` 子命令:**
    *   运行 `python -m market_price_data.scripts.data_updater history`。
    *   会实例化 `HistoryUpdater` 并执行一次完整的历史数据更新周期 (`run_update_cycle`)。
    *   这是**独立运行历史数据更新**的标准和推荐方式。
*   **`realtime` 子命令:**
    *   运行 `python -m market_price_data.scripts.data_updater realtime`。
    *   会实例化 `RealtimeUpdater` 并调用 `start_updater()` 启动实时监控。
    *   脚本会保持前台运行，直到超时（通过 `--timeout` 参数设置）或收到停止信号 (`Ctrl+C`)。它内部处理了 `Ctrl+C` 以调用 `stop_updater()` 实现优雅停止。
    *   **主要用途:** **单独测试和调试 `RealtimeUpdater`** 的功能。**不推荐**用此命令启动生产环境的实时数据服务（应使用 `run_live_strategy.py`）。

### 4. 配置 (`config/updater.yaml`)

此文件包含了 `HistoryUpdater` 和 `RealtimeUpdater` 所需的特定配置，与项目根目录下的 `config/common.yaml` (包含共享配置如 MT5 凭据、基础路径、默认日志设置等) 合并使用。

*   **`historical` 部分:** 控制历史数据更新，包括启用标志、品种列表、时间周期、起始日期、批次大小、延迟、重试、路径模式等。
*   **`realtime` 部分:** 控制实时数据监控，包括启用标志、品种列表、时间周期、**各周期轮询间隔 (`poll_intervals`)**、默认间隔、获取K线数、路径模式、重试等。
*   **`logging` 部分 (可选):** 可以为历史和实时更新指定单独的日志文件名，或覆盖 `common.yaml` 中的日志级别等设置。

### 5. 数据导出 (`exporters/exporter.py`)

提供将 `pandas.DataFrame` 格式的 K 线数据导出为 MetaTrader 5 历史数据中心兼容的 CSV 格式的功能 (`export_to_mt5_format`)。这对于需要将外部数据导入 MT5 进行回测的场景非常有用。

### 6. 辅助脚本与工具

*   **`scripts/run_updates.py`:** 一个简单的脚本，直接实例化并运行 `HistoryUpdater` 和 `RealtimeUpdater`，可用于简单的集成或测试场景。
*   **`scripts/batch/`:** 包含一些 Windows 批处理脚本，提供了另一种（可能更方便 Windows 用户）手动触发历史更新 (`update_history_data.bat`) 或设置定时历史更新任务 (`run_history_update_scheduled.bat`) 的方式。
*   **`tools/`:** 包含一些独立的 Python 脚本，用于检查 MT5 连接状态 (`check_mt5.py`)、账户信息 (`mt5_info.py`)、自动交易设置 (`enable_mt5_trading.py`, `check_trading.py`) 等，作为辅助工具使用。

## 与策略执行的集成 (`run_live_strategy.py`)

如前所述，启动实盘交易和相关数据服务的**推荐方式**是使用项目根目录下的 `run_live_strategy.py` 脚本。

**该脚本的核心职责:**

1.  加载并合并 `common.yaml` 和 `strategies/config/module.yaml` 配置。
2.  检查是否为交易日以及 MT5 终端是否在运行。
3.  **自动管理 `RealtimeUpdater`:**
    *   通过检查 `data/realtime_updater.pid` 文件判断 `RealtimeUpdater` 是否已运行。
    *   如果在交易日且 MT5 已运行但 `RealtimeUpdater` 未运行，则在后台启动 `RealtimeUpdater` 进程。
4.  初始化 `strategies` 模块的 `DataProvider` (配置为读取实时 CSV 文件) 和 `MT5ExecutionEngine`。
5.  调用 `MT5ExecutionEngine.connect()` 连接 MT5。
6.  初始化并运行 `StrategyOrchestrator` 开始执行策略逻辑。
7.  **退出时自动清理:** 使用 `atexit` 确保在脚本退出时，会创建 `data/STOP_REALTIME.flag` 文件来**自动停止**由它启动的 `RealtimeUpdater` 进程，并调用 `MT5ExecutionEngine.disconnect()` 断开连接。

**标准实盘运行流程:**

1.  启动并登录 MT5 终端。
2.  在项目根目录运行 `python run_live_strategy.py`。

## 总结

`market_price_data` 模块提供了健壮的历史数据维护和灵活的实时数据采集功能。通过与项目根目录的 `run_live_strategy.py` 脚本结合，可以实现数据服务与策略执行的自动化管理和协调。请务必仔细阅读并根据需要调整 `config/updater.yaml` 和 `config/common.yaml` 中的配置项。

## 文件结构 (更新后)

```
market_price_data/
├── __init__.py           # 模块入口，导出主要类和核心工具函数
├── history.py           # 历史数据更新核心实现 (HistoryUpdater 类)
├── realtime.py          # 实时数据监控核心实现 (RealtimeUpdater 类)
├── requirements.txt     # 模块特定的 Python 依赖
├── config/              # 配置文件目录
│   └── updater.yaml     # 模块特定配置 (品种, 周期, 路径模式, 启用标志等)
├── scripts/             # 可执行脚本目录
│   ├── data_updater.py  # 命令行工具入口 (使用子命令 'history' 和 'realtime')
│   ├── run_updates.py   # 直接启动历史和实时更新器的脚本
│   ├── batch/           # (Windows) 批处理脚本
│   │   ├── update_history_data.bat        # 手动运行历史更新
│   │   └── run_history_update_scheduled.bat # 设置历史更新计划任务
│   └── README.md        # scripts 子目录的说明文档 (可能需要更新)
├── exporters/           # 数据导出相关功能
│   └── exporter.py      # 将 DataFrame 导出为 MT5 兼容 CSV 的函数
├── tools/               # MT5 相关辅助工具
│   ├── check_mt5.py     # 检查 MT5 连接
│   ├── check_trading.py # 检查自动交易状态
│   ├── enable_mt5_trading.py # 尝试启用自动交易
│   └── mt5_info.py      # 显示 MT5 账户/终端信息
└── README.md            # 主模块说明文档 (本文件)

# 依赖的共享模块 (位于项目根目录下的 core/)
core/
├── utils.py             # 提供共享工具函数 (配置加载, 日志, MT5连接等)
└── ...

# 依赖的共享配置 (位于项目根目录下的 config/)
config/
├── common.yaml          # 项目全局共享配置 (MT5连接信息, 基础路径等)
└── ...
```

## 依赖

### Python 库

本模块运行所需的 Python 库在 `requirements.txt` 中列出，主要包括：

-   `MetaTrader5`: 与 MT5 平台交互的核心库。
-   `pandas`: 用于处理和存储 K 线数据。
-   `pytz`: 处理时区信息。
-   `omegaconf`: 用于加载和管理 YAML 配置文件。

请在**激活的虚拟环境**中使用以下命令安装：

```bash
pip install -r market_price_data/requirements.txt
```

### 共享模块 (`core.utils`)

本模块严重依赖 `core/utils.py` 提供的以下功能：

-   `load_app_config`: 加载 `common.yaml` 和 `updater.yaml` 并合并。
-   `setup_logging`: 初始化日志系统，支持文件和控制台输出。
-   `initialize_mt5`: 建立与 MT5 终端的连接，处理认证和路径查找。
-   `shutdown_mt5`: 断开与 MT5 的连接。
-   `parse_timeframes`: 将配置文件中的时间周期字符串转换为 MT5 常量。
-   `get_filepath`: 根据配置模式构建数据文件的完整路径。
-   `get_utc_timezone`: 获取 UTC 时区对象。
-   `MT5_AVAILABLE`: 检查 MT5 库是否成功导入。

确保 `core` 模块位于 Python 的搜索路径中。

## 使用方法

### 通过脚本运行 (推荐的实盘启动方式已更新)

-   **更新历史数据:**
    ```bash
    # 使用 data_updater.py (主要命令行方式)
    python -m market_price_data.scripts.data_updater history

    # 或者使用简单的 run_updates.py (会同时尝试启动实时更新)
    python market_price_data/scripts/run_updates.py

    # 或者使用 Windows 批处理
    # (进入 market_price_data/scripts/batch/ 目录后运行)
    update_history_data.bat
    ```
-   **启动实时监控 (重要更新):**
    -   **不推荐**再直接运行 `python -m market_price_data.scripts.data_updater realtime` 或 `python market_price_data/scripts/run_updates.py` 来**独立启动**生产环境的实时监控。
    -   **推荐的方式**是使用项目根目录下的 **`run_live_strategy.py`** 脚本。该脚本作为实盘交易的统一入口，会自动管理 `RealtimeUpdater` 的生命周期。请参考 `run_live_strategy.py` 的文档或代码。
    -   如果确实需要**单独测试** `RealtimeUpdater`，仍然可以使用以下命令，但请注意手动管理其生命周期和 PID 文件：
      ```bash
      # 仅用于测试或特殊场景
      python -m market_price_data.scripts.data_updater realtime
      ```

-   **定时任务:** 如果需要定时更新历史数据，可以使用 Windows 任务计划程序或类似工具，**仅调度历史数据更新命令** (`python -m market_price_data.scripts.data_updater history` 或使用 `run_history_update_scheduled.bat`)。

### 在代码中调用 (实时部分逻辑已外部化)

可以直接在其他 Python 代码中导入并使用 `HistoryUpdater`。
对于 `RealtimeUpdater`，由于其生命周期现在推荐由 `run_live_strategy.py` 管理，直接在代码中实例化和管理它的场景变得较少，除非您需要构建自定义的服务管理逻辑。

```python
from market_price_data import HistoryUpdater
import logging

# 配置日志 (示例，实际应使用 core.utils.setup_logging)
logging.basicConfig(level=logging.INFO)

# --- 历史数据更新 ---
print("运行历史数据更新...")
history_updater = HistoryUpdater() # 使用默认配置路径
if history_updater and history_updater.updater_enabled:
    history_updater.run_update_cycle()
    print("历史数据更新完成。")
else:
    print("历史数据更新器未启用或初始化失败。")

# --- 实时数据监控 (概念性) ---
# 对于实时监控，请参考 run_live_strategy.py 的实现方式。
# 直接调用 RealtimeUpdater 需要手动处理更多细节 (进程管理, PID, 信号等)。
print("对于实时数据监控，请使用 run_live_strategy.py 进行管理。")

```

## 配置说明

模块的行为由 YAML 配置文件控制：

-   `config/common.yaml`: 存储项目全局共享配置，例如：
    -   `execution.mt5`: MT5 登录凭据 (账号、密码(推荐环境变量)、服务器、终端路径)。
    -   `paths.data_dir`: 数据存储的基础目录。
    -   `logging`: 默认的日志配置 (级别、格式、基础日志目录)。
-   `market_price_data/config/updater.yaml`: 存储模块特定配置，会覆盖 `common.yaml` 中的同名项，例如：
    -   `historical.enabled`: 是否启用历史数据更新。
    -   `historical.symbols`, `historical.timeframes`: 更新的历史数据范围。
    -   `historical.start_date`, `historical.default_start_offsets`: 获取历史数据的起始点。
    -   `historical.data_directory_pattern`, `historical.filename_pattern`: 历史数据文件存储模式。
    -   `historical.batch_size_days`, `historical.delay_between_requests_ms`: 数据获取参数。
    -   `historical.retry_attempts`, `historical.retry_delay_seconds`: 历史数据获取重试逻辑。
    -   `realtime.enabled`: 是否启用实时数据监控。
    -   `realtime.symbols`, `realtime.timeframes`: 监控的实时数据范围。
    -   `realtime.poll_intervals`: (字典) 为特定时间周期指定轮询间隔（秒）。例如 `M1: 15`。
    -   `realtime.default_poll_interval_seconds`: (整数) 未在 `poll_intervals` 中指定的周期的默认轮询间隔（秒）。
    -   `realtime.fetch_bars_count`: 每次获取的 K 线数量。
    -   `realtime.data_directory_pattern`, `realtime.filename_pattern`: 实时数据文件存储模式。
    -   `realtime.retry_attempts`, `realtime.retry_delay_seconds`: 实时数据获取重试逻辑。
    -   `logging.history_log_filename`, `logging.realtime_log_filename`: 指定模块特定的日志文件名 (会覆盖 `common.yaml` 中可能存在的默认日志名)。
    -   `logging.level`: 可以覆盖 `common.yaml` 中的默认日志级别。

**注意:** 配置项的修改应直接编辑对应的 YAML 文件。

## 异常处理

模块内部实现了完善的异常处理机制，包括：

1.  MT5 连接失败自动重试
2.  数据下载失败自动重试
3.  文件存储错误恢复 (通过原子写入避免文件损坏)
4.  实时模式下的自动重连

所有错误和警告都会记录到日志文件中。

## 扩展开发

如需扩展模块功能，可以：

1.  在 `utils.py` 中添加通用工具函数
2.  继承 `HistoryUpdater` 或 `RealtimeUpdater` 类并重写相关方法
3.  在配置文件中添加新的配置项，并在代码中处理

### 未来优化方向：数据库存储

当前的历史数据更新机制（读取、合并、写回 CSV）在目前每个品种数据量较小（例如几十 MB）的情况下是可行的。然而，当历史数据文件变得非常大（例如接近或超过 GB 级别）时，性能可能会显著下降，更新过程可能变得缓慢且消耗大量内存。

如果未来遇到历史数据更新的性能瓶颈，推荐将历史数据存储迁移到数据库中。推荐使用 **SQLite**（Python 内置，简单易用）或 **DuckDB**（性能优异，尤其适合数据分析和 Pandas 集成）。

迁移到数据库大致需要以下步骤：

1.  **数据库选择与配置:**
    *   **选择数据库:** 根据需求选择 SQLite 或 DuckDB。
    *   **配置修改 (`config/common.yaml` 或 `market_price_data/config/updater.yaml`):**
        *   添加配置项指定数据库类型（如 `historical.storage_type: "sqlite"` 或 `"duckdb"`）。
        *   添加配置项指定数据库文件的存储路径（例如 `historical.db_path: "${paths.data_dir}/historical_market_data.db"`）。可以考虑为每个品种/周期单独创建数据库文件，或使用单一文件并在表中区分。

2.  **数据库表结构设计:**
    *   需要定义一个或多个数据库表来存储 K 线数据。
    *   **核心列:** `symbol` (文本), `timeframe` (文本), `time` (整数型 Unix 时间戳，**设为主键或联合主键的一部分**), `open` (浮点数), `high` (浮点数), `low` (浮点数), `close` (浮点数), `tick_volume` (整数), `spread` (整数), `real_volume` (整数)。
    *   **索引:** 为了提高查询效率（尤其是获取最后时间戳和按时间范围查询），应在 `symbol`, `timeframe`, `time` 列上创建索引（例如，联合索引 `(symbol, timeframe, time)`）。

3.  **代码修改 (`market_price_data/history.py`):**
    *   **`__init__`:** 根据配置加载数据库类型和路径，初始化数据库连接（例如使用 `sqlite3.connect()` 或 `duckdb.connect()`）。
    *   **`_get_fetch_start_time`:** 修改此方法，使其不再读取 CSV 文件最后一行，而是执行 SQL 查询（类似 `SELECT MAX(time) FROM klines WHERE symbol = ? AND timeframe = ?`）来获取数据库中对应品种和周期的最后一个时间戳。
    *   **`_fetch_historical_data_chunked`:** 此方法获取数据的逻辑基本不变，但返回的 DataFrame 将用于数据库写入。
    *   **`_update_historical_file` (需重命名或重构):** **完全替换此方法**的逻辑。新的逻辑将是：
        *   将获取到的 `new_data` DataFrame 写入数据库。
        *   可以使用 Pandas 的 `to_sql` 方法（`if_exists='append'`）配合数据库的唯一约束（在 `time` 列或联合主键上）来高效地插入新数据并自动忽略重复项。
        *   或者，对于更精细的控制或更新操作（如果需要），可以使用数据库连接执行 `INSERT OR IGNORE` 或 `INSERT ... ON CONFLICT DO UPDATE` (Upsert) 语句。
    *   **`_verify_data_integrity` (可能需要调整):** 验证逻辑需要修改为查询数据库，例如检查时间戳的连续性或查找重复的时间戳。

4.  **数据消费者代码修改 (例如 `strategies`, `backtesting` 模块):**
    *   任何之前直接读取历史 CSV 文件来获取数据的模块，都需要修改为连接数据库并执行 SQL 查询来获取所需的数据。这可能需要调整 `DataProvider` 等组件。

迁移到数据库虽然增加了初始的复杂性，但能显著提升处理大规模历史数据的性能和效率，并提供更灵活的数据访问方式。

## 故障排除

- **MT5 连接问题**：确保 MetaTrader 5 终端已启动并登录
- **历史数据不完整**：尝试增加 `retry_attempts` 值并检查 MT5 是否有权限访问此类数据
- **实时数据延迟**：考虑减小 `poll_interval_seconds` 值以获取更实时的数据
- **高内存使用**：减小 `fetch_bars_count` 以减少内存占用 