<<<<<<< HEAD
# strategic_space
=======
<<<<<<< HEAD
# strategic_space
=======
# 战略空间 - 财经日历与数据服务工具

这是一个用于处理、筛选财经日历数据并提供相关数据服务的工具，可以获取历史和实时财经数据、市场价格数据，并进行处理、导出。

## 功能特点

- 获取历史财经事件数据
- 爬取实时财经事件数据
- 获取市场价格数据 (基于 `market_price_data` 模块)
- 按重要性级别筛选事件
- 按关键词筛选重要事件 (基于 `economic_calendar` 模块的配置和逻辑)
- 按货币类型筛选事件
- 支持导出到 CSV 格式
- 支持导出到 MT5 平台数据目录
- 提供数据服务 (通过 `run_data_service.py` 启动 `market_price_data` 模块的服务)

## 项目架构

**文件目录结构图:**

```plaintext
.
├── .venv/                     # Python 虚拟环境目录
├── .cursor/                   # Cursor IDE 特定配置目录
├── .qodo/                     # Qodo 相关配置或数据
├── cache/                     # 应用程序级别的临时缓存
├── config/                    # 全局或共享配置目录
│   ├── common.yaml            # **核心共享配置** (MT5 执行连接, 基础路径, 日志等)
│   └── config.yaml            # (特定/遗留配置) 应用或特定任务配置 (API服务, 脚本路径等)
├── data/                      # 主要数据存储目录 (由 common.yaml 中 paths.data_dir 定义)
│   ├── backups/               # 数据备份
│   ├── cache/                 # 数据处理过程中的缓存
│   ├── calendar/              # 财经日历相关数据 (子目录结构由 processing.yaml 定义)
│   ├── database/              # SQLite 数据库文件存放目录
│   ├── exports/               # 导出文件目录
│   ├── historical/            # (此目录结构由 market_price_data/config/updater.yaml 定义)
│   ├── logs/                  # 日志文件目录 (由 common.yaml 中 logging 配置指定)
│   ├── mt5_backup/            # MT5 数据备份
│   ├── mt5_data/              # 导出的 MT5 平台可用数据
│   ├── realtime/              # (此目录结构由 market_price_data/config/updater.yaml 定义)
│   └── db/                    # (economic_calendar 处理后的 SQLite DB, 由 processing.yaml 定义)
├── docs/                      # 项目文档目录
├── economic_calendar/         # 财经日历数据处理模块
│   ├── config/                # 财经日历模块特定配置
│   │   ├── processing.yaml    # **核心配置**: 定义处理流程、路径、筛选规则、下载参数等
│   │   ├── keywords.py        # **核心配置**: 定义详细的事件筛选关键词列表和结构
│   │   └── __init__.py
│   ├── data/                  # (旧) 模块内部数据 (可能已被根 data/ 目录取代)
│   ├── economic_calendar_history/ # 历史日历数据处理相关逻辑
│   ├── economic_calendar_realtime/ # 实时日历数据处理相关逻辑
│   ├── event_filter/          # 事件筛选逻辑 (使用 config/keywords.py)
│   ├── tasks/                 # 任务/工作流脚本
│   │   ├── run_history_workflow.py
│   │   ├── run_realtime_workflow.py
│   │   └── WORKFLOW_README.md
│   ├── utils/                 # 工具函数
│   ├── __init__.py
│   ├── main.py                # 模块主入口 (被根 run_economic_calendar.py 调用)
│   ├── README_CN.md           # 模块中文说明
│   ├── requirements.txt       # 模块特定依赖
│   └── run.bat                # 模块独立运行脚本
├── logs/                      # (旧/根级) 日志目录 (建议统一使用 common.yaml 配置的日志目录)
│   └── __init__.py
├── market_price_data/         # MT5 市场价格数据处理模块
│   ├── config/                # 市场价格模块特定配置
│   │   └── updater.yaml       # **核心配置**: 控制历史和实时数据更新的目标、频率、路径模式等
│   ├── exporters/             # 数据导出器
│   ├── scripts/               # 模块内部入口脚本
│   │   ├── batch/
│   │   ├── data_updater.py    # (推测) 数据更新器实现
│   │   ├── run_data_service.py # 被根目录同名脚本调用
│   │   ├── run_history.py     # 被根目录同名脚本调用
│   │   ├── run_realtime.py    # 被根目录同名脚本调用
│   │   └── README.md
│   ├── tools/                 # 工具脚本
│   ├── __init__.py
│   ├── history.py             # 历史数据处理核心逻辑
│   ├── realtime.py            # 实时数据处理核心逻辑
│   ├── utils.py               # **重要**: 包含共享的配置加载函数 `load_app_config`
│   ├── README.md              # 模块英文说明
│   └── README_CN.md           # 模块中文说明
├── strategies/                # 交易策略模块
│   ├── config/                # 策略模块特定配置
│   │   ├── strategies.yaml    # **核心配置**: 控制策略启用、执行引擎、策略参数、魔术数字等
│   │   └── config.py          # 提供策略代码内部的默认配置结构和值 (低优先级)
│   ├── core/                  # 策略核心框架 (包括 DataProvider)
│   ├── live/                  # 实盘/模拟执行引擎
│   ├── backtest/              # (推测) 与回测相关的策略辅助代码
│   ├── docs/                  # 策略文档
│   ├── *.py                   # 具体策略实现文件
│   ├── README.md              # 模块说明
│   └── requirements.txt       # 模块特定依赖
├── backtesting/               # 回测模块
│   ├── config/                # 回测模块特定配置
│   │   └── backtest.yaml      # **核心配置**: 控制回测引擎参数、时间范围、资金、成本、分析器参数等
│   ├── __init__.py
│   ├── engine.py              # 回测引擎核心逻辑
│   ├── analyzer.py            # 回测结果分析器
│   └── requirements.txt       # 模块特定依赖
├── src/                       # (可能包含) Web 服务及其他核心代码
│   ├── __init__.py
│   └── web/                   # Web 服务实现 (示例结构)
│       ├── backend/           # 后端 API 服务 (FastAPI)
│       └── frontend/          # 前端应用 (Node.js)
├── .gitignore                 # Git 忽略文件配置
├── MT5量化交易系统使用手册.md   # MT5 系统手册
├── README.md                  # 项目主说明文件 (本文件)
├── requirements.txt           # 项目全局 Python 依赖
├── run_backtest.py            # (入口) 运行策略回测
├── run_data_service.py        # (入口) 启动 MT5 市场数据服务 (调用 market_price_data)
├── run_economic_calendar.py   # (入口) 运行财经日历处理 (调用 economic_calendar)
├── run_economic_data.bat      # (入口) 运行财经日历相关任务的批处理脚本
├── run_historical_data.bat    # (入口) 运行历史数据相关任务的批处理脚本
├── run_history_update.py      # (入口) 运行 MT5 历史数据更新 (调用 market_price_data)
├── run_mt5_data_updater.bat   # (入口) 运行 MT5 数据更新任务的批处理脚本
├── run_realtime_update.py     # (入口) 运行 MT5 实时数据更新 (调用 market_price_data)
├── 战略空间交易系统说明文档.md # 交易系统说明文档
└── 开发文档.md                # 开发相关文档
```

本项目架构围绕两大核心数据领域构建：财经日历数据和 MT5 市场价格数据，并通过配置驱动、模块化和可能的 Web 服务进行组织。

1.  **配置管理 (使用 `OmegaConf`)**:
    *   项目采用 **分层配置**，由 Python 库 `OmegaConf` 进行加载、合并和变量解析。
    *   **核心共享配置**位于根目录的 **`config/common.yaml`**，定义了基础设置，如日志 (`logging`)、基础数据目录 (`paths.data_dir`)、以及**关键的 MT5 执行连接信息 (`execution.mt5`)**，供需要连接 MT5 的模块（`market_price_data`, `strategies`, `backtesting`）使用。
    *   **模块特定配置**位于各模块目录下的 **`config/*.yaml`** 文件 (如 `market_price_data/config/updater.yaml`, `backtesting/config/backtest.yaml`, `strategies/config/strategies.yaml`, `economic_calendar/config/processing.yaml`)。这些文件包含模块运行所需的具体参数，它们会**覆盖或合并** `common.yaml` 中的同名设置（`OmegaConf` 默认行为）。
    *   根目录的 `config/config.yaml` 文件包含一些特定于顶层任务或遗留的配置（如 API 服务参数、旧脚本路径），其作用相对有限，**`common.yaml` 是主要的共享配置文件**。
    *   配置加载通过共享的 `load_app_config` 函数（主要位于 `market_price_data/utils.py`）实现，该函数负责读取 `common.yaml` 和指定的模块 YAML 文件，并返回合并后的 `DictConfig` 对象。
    *   `strategies` 模块还有一个 `config.py` 文件，它定义了代码内部的**默认配置结构和值**，但运行时参数优先来自 YAML 文件。

2.  **财经日历数据处理 (`economic_calendar` 模块)**:
    *   **配置**: 由 **`economic_calendar/config/processing.yaml`** (定义处理流程、相对路径、筛选规则、下载参数、文件复制目标等) 和 **`economic_calendar/config/keywords.py`** (定义详细的筛选关键词列表和结构) 控制。配置加载时会自动合并 `common.yaml`。
    *   **核心逻辑**: 封装在 `economic_calendar` Python 包内，包括数据下载 (例如 `economic_calendar_realtime/download_investing_calendar.py` 从 `processing.yaml` 获取 URL)、处理、筛选 (`event_filter/logic.py` 使用 `keywords.py` 中的定义) 和存储。
    *   **数据路径**: 基于 `common.yaml` 的 `paths.data_dir` 和 `processing.yaml` 中定义的相对路径 (`economic_calendar.paths.*`)。
    *   **触发方式**: 通过根目录的 `run_economic_calendar.py` (调用模块内 `main.py`) 或 `run_economic_data.bat` (批处理脚本) 启动。

3.  **MT5 市场价格数据处理 (`market_price_data` 模块)**:
    *   **配置**: 由 **`market_price_data/config/updater.yaml`** 控制历史和实时数据更新的目标品种、时间周期、频率、数据存储路径/文件名模式等。配置加载时会自动合并 `common.yaml`。
    *   **核心逻辑**: 封装在 `market_price_data` Python 包内 (`history.py`, `realtime.py`)。
    *   **功能**: 连接 MT5 交易终端 (根据 **`config/common.yaml` 中 `execution.mt5`** 的配置)，获取和存储历史及实时 K 线数据。
    *   **便捷入口**: 根目录下的 `run_history_update.py` (历史数据)、`run_realtime_update.py` (实时数据) 和 `run_data_service.py` (综合服务，调用模块内 `scripts/run_data_service.py`) 提供命令行接口。
    *   **数据存储**: 获取的数据根据 `common.yaml` 的 `paths.data_dir` 和 `updater.yaml` 中的路径/文件名模式存储。

4.  **策略验证 (`backtesting` 模块)**:
    *   **配置**: 主要由 **`backtesting/config/backtest.yaml`** 控制回测引擎参数（时间范围、初始资金、交易成本、分析器参数等）。配置加载时会自动合并 `common.yaml`。
    *   **核心逻辑**: 封装在 `backtesting` 包内 (`engine.py`, `analyzer.py`)。
    *   **依赖**: 需要 `strategies` 模块提供 `DataProvider` 和策略类实例，可能需要 `economic_calendar` 提供事件数据。
    *   **执行**: 通过根目录的 `run_backtest.py` 脚本启动，该脚本负责加载合并后的配置并传递给 `BacktestEngine`。

5.  **交易策略 (`strategies` 模块)**:
    *   **配置**: 由 **`strategies/config/strategies.yaml`** 控制策略启用、调度器、执行引擎选择 (`mt5` 或 `sandbox`) 和各策略的具体运行参数 (`strategy_params`, 包括 `magic_number`)。配置加载时会自动合并 `common.yaml`。`strategies/config.py` 提供代码内部默认值。
    *   **核心逻辑**: 包含策略核心框架 (`core/`, 提供 `DataProvider`)、实盘/模拟执行引擎 (`live/`) 和具体的策略实现文件 (*.py)。
    *   **执行**: 通常由回测脚本 (`run_backtest.py`) 或未来的实盘运行脚本调用。

6.  **Web 服务 (`src/web/`)**:
    *   (结构基于推测) 可能包含 FastAPI 后端和 Node.js 前端。
    *   后端 API 可能用于提供财经日历事件、市场价格等数据查询接口。
    *   其配置可能部分来源于 `config/config.yaml` (如 API host/port)。

7.  **数据存储 (`data/`, `cache/`, `logs/`)**:
    *   `data/` 目录是主要的数据中心，由 **`config/common.yaml` 的 `paths.data_dir`** 定义基础路径，各模块的 YAML 文件定义其下的具体子目录结构和文件名。
    *   `cache/` 目录用于存放临时缓存文件。
    *   `logs/` 目录存放由 `common.yaml` 的 `logging` 配置指定的日志文件。

**架构示意图 (Mermaid):**

```mermaid
graph LR
    subgraph 配置中心 (OmegaConf)
        CommonYaml["config/common.yaml<br/>(共享配置,<br/>含 execution.mt5, paths.data_dir)"] --> ModuleYaml;
        ModuleYaml["模块配置 YAML<br/>(e.g., updater.yaml, backtest.yaml, <br/>strategies.yaml, processing.yaml) <br/>覆盖/合并 common.yaml"];
        KeywordsPy["economic_calendar/config/keywords.py<br/>(详细关键词定义)"];
        StrategiesConfigPy["strategies/config.py<br/>(代码内默认值) - 低优先级"];
        ConfigYaml["config/config.yaml<br/>(特定/遗留配置?)"]
    end

    subgraph 财经日历处理 (economic_calendar 模块)
        direction LR
        EC_Entry[入口脚本<br/>(run_economic_calendar.py <br/>或 .bat)] --> EC_Main(economic_calendar/main.py);
        EC_Main -- 加载配置 --> ModuleYaml; # processing.yaml
        EC_Main -- 内部逻辑调用 --> KeywordsPy; # 筛选逻辑使用
        EC_Main --> EC_Logic(下载/处理/筛选逻辑);
        EC_Logic --> EC_Storage(日历数据存储<br/>基于 paths.data_dir + processing.yaml 路径);
        EC_Storage --> DataDir;
    end

    subgraph MT5 市场价格处理 (market_price_data 模块)
        direction TB
        MP_EntryPoints["根目录入口脚本<br/>(run_history/realtime/data_service.py)"] --> MP_Logic(market_price_data 模块<br/>history.py / realtime.py);
        MP_Logic -- 加载配置 --> ModuleYaml; # updater.yaml
        MP_Logic -- 连接 (使用 execution.mt5) --> MT5(MT5 终端);
        MT5 --> MP_Logic;
        MP_Logic --> MP_Storage(市场价格存储<br/>基于 paths.data_dir + updater.yaml 路径);
        MP_Storage --> DataDir;
    end

    subgraph 回测 (backtesting 模块)
        direction TB
        BT_Entry[run_backtest.py] --> BT_Engine(backtesting/engine.py);
        BT_Entry -- 加载配置 --> ModuleYaml; # backtest.yaml
        BT_Engine -- 传递合并后配置 --> BT_Logic;
        BT_Engine -- 依赖 --> SP_Core(strategies/core);
        BT_Engine -- 依赖 --> EC_Logic; # 获取事件数据
        BT_Logic -- 使用 DataProvider --> SP_Core;
        BT_Logic -- 获取事件 --> EC_Logic;
        BT_Logic --> BT_Results(回测结果存储);
        BT_Results --> DataDir;
    end

    subgraph 策略 (strategies 模块)
        direction TB
        StrategyEntry[回测/实盘入口] --> StrategyCore(strategies/core);
        StrategyEntry -- 加载配置 --> ModuleYaml; # strategies.yaml
        StrategyCore -- 传递合并后配置 --> SpecificStrategy(具体策略实现);
        SpecificStrategy -- 使用 DataProvider --> StrategyCore;
        SpecificStrategy -- 使用执行引擎 --> StrategyLive(strategies/live);
        StrategyLive -- 连接 (使用 execution.mt5) --> MT5;
        StrategyLive -- 读取配置 --> ModuleYaml; # strategies.yaml
    end

    subgraph Web 服务 (src/web/)
        direction TB
        Web_Frontend[前端 (Node.js)] <-- API --> Web_Backend(后端 API<br/>FastAPI - app.py);
        Web_Backend -- 获取数据 (推测) --> EC_Logic;
        Web_Backend -- 获取数据 (推测) --> MP_Logic;
        Web_Backend -- 读取配置? --> ConfigYaml; # API Host/Port from config.yaml?
        Web_Backend -- 读取配置? --> CommonYaml;
    end

    subgraph 存储
        DataDir[data/ 目录]
        LogsDir[logs/ 目录]
        CacheDir[cache/ 目录]
    end

    CommonYaml --> DataDir;
    CommonYaml --> LogsDir;
    CommonYaml --> CacheDir;
    KeywordsPy --> EC_Logic;

    %% 连接关系
    EC_Entry -- 调用 --> EC_Main
    MP_EntryPoints -- 调用 --> MP_Logic
    BT_Entry -- 调用 --> BT_Engine
    Web_Frontend -- 用户交互 --> A[用户]
    A -- 启动 --> MP_EntryPoints
    A -- 启动 --> EC_Entry
    A -- 启动 --> BT_Entry

```
*注意：此图基于现有文件分析和推断，特别是 Web 服务的具体数据获取方式和配置来源可能需要进一步确认。*

## 系统要求

- Python 3.8+
- Windows操作系统（MT5交互功能需要）
- 依赖库：见根目录 `requirements.txt` 及各模块下的 `requirements.txt`。**请确保所有依赖都已安装。**

## 安装步骤

1.  **克隆仓库** (如果尚未完成)
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```
2.  **创建并激活虚拟环境** (推荐)
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    # source .venv/bin/activate
    ```
3.  **安装全局依赖**
    ```bash
    pip install -r requirements.txt
    ```
4.  **安装各模块依赖** (如果模块有独立的 `requirements.txt` 且未包含在全局中)
    ```bash
    pip install -r economic_calendar/requirements.txt
    pip install -r market_price_data/requirements.txt
    pip install -r strategies/requirements.txt
    pip install -r backtesting/requirements.txt
    # 如果 src/web/backend 有依赖
    # pip install -r src/web/backend/requirements.txt
    ```
    *注意：理想情况下，所有 Python 依赖应统一管理在根目录的 `requirements.txt` 中。*

## 配置说明

1.  **核心配置:** 主要修改 **`config/common.yaml`** 文件，特别是 `paths.data_dir` (数据存储根目录) 和 `execution.mt5` (用于连接 MT5 的账户信息)。**强烈建议将 `execution.mt5.password` 留空，并通过设置名为 `MT5_PASSWORD` 的环境变量来提供密码。**
2.  **模块配置:** 根据需要调整各模块 `config/` 目录下的 YAML 文件：
    *   `economic_calendar/config/processing.yaml`: 配置日历数据处理流程、路径、筛选条件等。关键词定义在 `economic_calendar/config/keywords.py`。
    *   `market_price_data/config/updater.yaml`: 配置需要更新的市场数据品种、周期、存储路径等。
    *   `strategies/config/strategies.yaml`: 配置启用的策略、执行方式、策略参数（如魔术数字）等。
    *   `backtesting/config/backtest.yaml`: 配置回测的时间范围、初始资金、交易成本、回测品种等。
3.  **环境变量:** (重要) 设置 `MT5_PASSWORD` 环境变量来安全地存储 MT5 密码。

## 运行说明

项目提供了多个入口脚本和批处理文件，用于执行不同的任务：

-   **财经日历处理:**
    *   `python run_economic_calendar.py` 或运行 `run_economic_data.bat`
-   **市场数据更新:**
    *   历史数据: `python run_history_update.py` 或运行 `run_historical_data.bat` / `run_mt5_data_updater.bat`
    *   实时数据: `python run_realtime_update.py`
    *   综合服务: `python run_data_service.py`
-   **策略回测:**
    *   `python run_backtest.py --config backtesting/config/backtest.yaml` (指定回测配置文件)
-   **Web 服务** (如果实现):
    *   根据 `src/web/` 下的具体实现启动后端和前端服务。

**日志:** 运行日志会根据 `config/common.yaml` 中的配置写入指定的日志文件（默认为 `logs/` 目录下）。

## 注意事项

- 确保 MT5 终端已安装，并且 `config/common.yaml` 中的 `terminal_path` 配置正确。
- 运行前务必检查并按需修改配置文件。
- 依赖库可能需要更新，定期运行 `pip install -r requirements.txt --upgrade`。
- 环境变量 `MT5_PASSWORD` 需要在运行脚本的会话中可用。
>>>>>>> 874f65ea (Initial commit)
>>>>>>> d2779772 (Initial commit)
