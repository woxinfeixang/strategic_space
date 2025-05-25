# 经济日历数据处理模块

## 1. 模块概述 (Overview)

本模块旨在提供一个健壮、可配置且自动化的解决方案，用于从外部来源（如金十数据）获取、处理、筛选和存储经济日历数据。它支持实时数据流和历史数据回补，并具有灵活的事件过滤机制和数据导出选项。模块利用 `loguru` 实现了标准化的日志记录，便于监控和调试。

## 2. 主要功能 (Main Features)

*   **实时数据获取:** 使用 Playwright 从 Investing.com 抓取当天的经济日历事件。
*   **历史数据处理:** 支持处理本地存储的历史 HTML 文件 (需要 `process_calendar.py` 脚本，当前未包含在自动工作流中)。
*   **统一事件过滤:** **使用相同的核心逻辑 (`apply_memory_filters`) 和配置**，根据用户定义的规则（重要性、货币、时间窗口、关键词等）筛选实时和历史事件。
*   **数据导出:** 将处理和筛选后的数据导出为 CSV 文件和 SQLite 数据库。
*   **任务自动化:** 提供清晰的工作流脚本 (`tasks/`)，方便通过任务调度程序（如 Windows 任务计划程序或 `cron`）运行。
*   **配置管理:** 使用 YAML 文件 (`config/processing.yaml`) 进行灵活配置。
*   **标准化日志:** 使用标准 `logging` 模块进行日志记录 (或根据 `core.utils.setup_logging` 的实现)。

## 3. 文件结构 (File Structure)

```
economic_calendar/
├── main.py                    # 命令行接口，用于执行历史筛选流程 (action=filter)
├── README_CN.md               # 本文档
├── __init__.py                # 包初始化文件
│
├── config/                    # 配置文件目录
│   ├── processing.yaml        # 模块核心处理逻辑配置 (合并通用配置)
│   └── __init__.py
│
├── data/                      # 数据存储目录 (结构见 data/README.md)
│   ├── raw/
│   ├── processed/
│   ├── filtered/
│   └── logs/                  # 日志文件 (通常在项目根目录/logs)
│
├── economic_calendar_realtime/ # 实时数据下载逻辑
│   ├── download_investing_calendar.py # 核心下载脚本
│   └── README.md              # 实时下载子模块说明
│
├── event_filter/              # 事件过滤核心逻辑
│   ├── logic.py               # 包含 apply_memory_filters 函数
│   └── __init__.py
│
├── tasks/                     # 工作流任务脚本
│   ├── run_realtime_workflow.py # 完整的实时处理流程
│   ├── run_history_workflow.py  # 完整的历史处理流程
│   ├── filter_data_step.py      # 被实时工作流调用的筛选步骤脚本
│   └── __init__.py
│
└── data/                      # (重复提及) 数据加载与导出工具
    ├── loader.py              # 加载数据的函数 (如 load_input_file)
    ├── exporter.py            # 导出数据的函数 (如 export_to_csv, export_to_sqlite)
    └── __init__.py

```

**注意:**
*   实际的数据和日志路径可能由项目根目录的 `config/common.yaml` 控制。
*   根目录的 `requirements.txt` 包含了整个项目（包括此模块）的所有依赖。
*   `config/processing.yaml` 通常会加载并合并项目根目录 `config/common.yaml` 的设置。

## 4. 配置说明 (Configuration)

模块的行为主要由 `config/processing.yaml` 文件驱动，该文件可能合并自项目根目录的 `config/common.yaml`。

关键配置项包括：

*   `economic_calendar.paths`: 定义模块内部使用的各种数据子目录路径（相对于基础数据路径）。
    *   `raw_live_dir`: 实时原始 CSV 存放目录。
    *   `processed_history_dir`: 处理后的历史 CSV 存放目录。
    *   `filtered_live_dir`: 筛选后的实时 CSV 存放目录。
    *   `filtered_history_dir`: 筛选后的历史 CSV 存放目录。
    *   `db_dir`: SQLite 数据库文件存放目录。
*   `economic_calendar.files`: 定义各种输入输出文件的名称。
    *   `raw_live_csv`: 实时下载脚本输出的 CSV 文件名 (默认 `upcoming.csv`)。
    *   `processed_history_csv`: 历史处理脚本输出的 CSV 文件名 (默认 `economic_calendar_history.csv`)。
    *   `filtered_csv_prefix`: 筛选后实时 CSV 文件名的前缀 (默认 `filtered_`)。
    *   `events_db`: SQLite 数据库文件名 (默认 `economic_calendar.db`)。
*   `economic_calendar.download`: 实时数据下载的相关参数（如 `target_url`, `timeout_seconds`）。
*   `economic_calendar.filtering`: 通用的筛选参数（见下节详细说明）。
*   `economic_calendar.currencies`: 需要关注的货币列表。
*   `economic_calendar.keywords_config`: 用于关键词筛选的详细配置（见下节）。
*   `economic_calendar.export`: 数据导出相关设置 (如 `csv_encoding`)。
*   `scripts`: 工作流脚本 (`tasks/`) 用来定位和执行子脚本的配置。

请在使用前仔细检查 `config/common.yaml` 和 `config/processing.yaml` 文件中的路径和参数。

## 5. 核心筛选逻辑 (`apply_memory_filters`)

历史数据和实时数据的筛选最终都依赖于 `economic_calendar/event_filter/logic.py` 文件中的核心函数 `apply_memory_filters`。这确保了无论数据来源如何，筛选规则和处理方式都是**完全一致的**。

该函数接收事件数据（一个字典列表 `List[Dict]`）和一系列从 `config/processing.yaml` 读取的参数，并按以下顺序应用筛选：

1.  **时间窗口筛选 (Time Window Filter):**
    *   由 `economic_calendar.filtering.time_filter_enabled` 控制是否启用。
    *   如果启用，则只保留事件时间 (`Time` 字段) 落在 `economic_calendar.filtering.start_time` 和 `economic_calendar.filtering.end_time` 之间（包含边界）的事件。
    *   时间格式应为 `HH:MM`。

2.  **重要性筛选 (Importance Filter):**
    *   根据 `economic_calendar.filtering.min_importance` 参数进行筛选。
    *   只保留 `Importance` 值（数值类型）**大于或等于** `min_importance` 的事件。

3.  **货币筛选 (Currency Filter):**
    *   只保留 `Currency` 字段的值存在于 `economic_calendar.currencies` 列表中的事件。

4.  **关键词筛选 (Keyword Filter):**
    *   由 `economic_calendar.filtering.use_keywords_filter` 控制是否启用。
    *   如果启用，则根据 `economic_calendar.keywords_config` 中的规则进行复杂的筛选：
        *   **CRITICAL_EVENTS:** 包含在此列表中的关键词（精确匹配 `Event` 字段）会被无条件保留，**忽略**其他所有筛选条件（重要性、货币、时间）。
        *   **IMPORTANT_SPEAKERS:** 包含在此列表中的关键词（精确匹配 `Event` 字段）会被无条件保留，**忽略**其他所有筛选条件。
        *   **HIGH_IMPACT_KEYWORDS:** 如果事件的 `Event` 字段包含此列表中的**任何一个关键词**（大小写不敏感的部分匹配），则该事件会被保留，前提是它已经通过了重要性、货币和时间筛选。
        *   **CURRENCY_SPECIFIC_2STAR_KEYWORDS:** 这是一个字典，键是货币代码（如 "USD", "EUR"），值是特定于该货币的关键词列表。如果一个事件的 `Importance` **等于 2**，并且其 `Currency` 匹配字典中的一个键，并且其 `Event` 字段包含对应列表中的**任何一个关键词**（大小写不敏感的部分匹配），则该事件会被保留，前提是它已通过时间筛选。
        *   **优先级:** CRITICAL 和 SPEAKERS 具有最高优先级。如果一个事件不满足这两者，则会检查 HIGH_IMPACT。如果还不满足，并且重要性为 2，则会检查 CURRENCY_SPECIFIC_2STAR。
        *   **默认:** 如果启用了关键词筛选，但事件不满足以上任何关键词规则，则它会被**丢弃**（即使它满足重要性、货币、时间筛选）。

5.  **添加开盘事件 (Add Market Open Events):**
    *   由 `economic_calendar.filtering.add_market_open` 控制是否启用。
    *   如果启用，脚本会检查每个交易日（基于数据中的日期）的特定时间窗口（欧盘开盘：13:45-14:15 UTC；美盘开盘：21:15-21:45 UTC，考虑夏令时调整）内是否已有筛选后的事件。
    *   如果某个开盘窗口内**没有任何**已筛选出的事件，则会自动添加一个代表该市场开盘的虚拟事件（如 "欧盘开盘", "美盘开盘"）。

**数据准备一致性:**
*   为了确保 `apply_memory_filters` 接收到的数据格式一致，历史流程 (`main.py --action filter`) 和实时流程 (`filter_data_step.py`) 在调用此函数前，都会将从 CSV 加载的数据（可能是 DataFrame 或直接是列表）显式转换为标准的 Python 字典列表 (`List[Dict[str, Any]]`)。

## 6. 工作流执行 (Workflows)

推荐使用 `tasks/` 目录下的脚本来执行完整的数据处理流程，便于自动化调度。

1.  **运行实时工作流** (`tasks/run_realtime_workflow.py`):
    *   **命令**: `python economic_calendar/tasks/run_realtime_workflow.py`
    *   **流程**:
        1.  调用 `economic_calendar_realtime/download_investing_calendar.py` 抓取当天 Investing.com 数据并直接保存为 **原始 CSV 文件** 到 `data/calendar/raw/live/` (文件名由 `economic_calendar.files.raw_live_csv` 配置，默认 `upcoming.csv`)。日期列为运行当天，重要性为数字。
        2.  调用 `economic_calendar/tasks/filter_data_step.py`。
        3.  `filter_data_step.py` 加载上一步的原始 CSV，将其**转换为字典列表**。
        4.  `filter_data_step.py` 调用核心筛选函数 `apply_memory_filters` 进行统一筛选。
        5.  `filter_data_step.py` 将筛选结果（列表）写入最终的 CSV 文件 (`data/calendar/filtered/live/filtered_live.csv`) 和 SQLite 数据库 (`data/db/economic_calendar.db` 中的 `events_live` 表)。
    *   **主要输入**: Investing.com 网站实时页面。
    *   **主要输出**:
        *   **原始 CSV**: `data/calendar/raw/live/upcoming.csv` (示例)
        *   **最终筛选 CSV**: `data/calendar/filtered/live/filtered_live.csv`
        *   **最终数据库**: `data/db/economic_calendar.db` (表 `events_live`)

2.  **运行历史数据工作流** (`tasks/run_history_workflow.py`):
    *   **命令**: `python economic_calendar/tasks/run_history_workflow.py`
    *   **流程**:
        1.  (假设) 调用 `economic_calendar_history/scripts/process_calendar.py` 处理 `data/calendar/raw/history/` 目录下的所有 HTML 文件，生成**处理后的历史 CSV 文件** (`data/calendar/processed/history/economic_calendar_history.csv`)。
        2.  调用 `economic_calendar/main.py --action filter`。
        3.  `main.py --action filter` 加载上一步的处理后 CSV，将其**转换为字典列表**。
        4.  `main.py --action filter` 调用核心筛选函数 `apply_memory_filters` 进行统一筛选。
        5.  `main.py --action filter` 将筛选结果（列表）**转换回 DataFrame**。
        6.  `main.py --action filter` 将 DataFrame 写入最终的 CSV 文件 (`data/calendar/filtered/history/filtered_historical.csv`) 和 SQLite 数据库 (`data/db/economic_calendar.db` 中的 `events_history` 表)。
    *   **主要输入**: `data/calendar/raw/history/*.html` (需要 `process_calendar.py` 先处理)。
    *   **主要输出**:
        *   **处理后 CSV**: `data/calendar/processed/history/economic_calendar_history.csv`
        *   **最终筛选 CSV**: `data/calendar/filtered/history/filtered_historical.csv`
        *   **最终数据库**: `data/db/economic_calendar.db` (表 `events_history`)

## 7. 自动化运行 (批处理与任务计划)

为了方便自动化执行实时数据更新流程，项目提供了一个批处理文件：`run_realtime_calendar.bat` (位于项目根目录 `E:\Programming\strategic_space`)。

*   **功能**: 这个批处理文件封装了运行实时工作流所需的步骤：
    1.  自动切换到项目根目录 (`E:\Programming\strategic_space`)。
    2.  自动激活项目虚拟环境 (`.venv`)。
    3.  使用虚拟环境中的 Python 执行器运行 `economic_calendar/tasks/run_realtime_workflow.py` 脚本。
    4.  输出简单的执行信息和错误提示。
*   **使用**:
    *   **手动运行**: 直接双击 `run_realtime_calendar.bat` 文件即可运行实时工作流。
    *   **配合 Windows 任务计划程序**:
        1.  打开任务计划程序 (`taskschd.msc`)。
        2.  创建新任务。
        3.  设置触发器为"计算机启动时"或您希望的每日运行时间。
        4.  设置操作为"启动程序"。
        5.  在"程序/脚本"框中，填写批处理文件的**完整路径**: `E:\Programming\strategic_space\run_realtime_calendar.bat`。
        6.  "添加参数"和"起始于"框保持为空**，因为批处理文件内部已处理这些。
        7.  保存任务。
    这样可以实现开机自动运行或每日定时运行实时数据更新流程。

## 8. 数据存储 (Data Storage)

请参考 `economic_calendar/data/README.md` 获取详细的数据目录结构和文件说明。

## 9. 依赖管理 (Dependencies)

所有必需的依赖项都列在**项目根目录**的 `requirements.txt` 文件中。

请确保在运行本模块之前，已在你的 Python 环境（推荐使用虚拟环境 `.venv`）中安装了所有依赖：

```bash
# (激活虚拟环境)
# .\\.venv\\Scripts\\activate   # Windows

pip install -r requirements.txt
# 运行实时下载需要 Playwright
playwright install
```

主要依赖包括：

*   `pandas`: 用于数据处理。
*   `PyYAML` / `omegaconf`: 用于加载 YAML 配置。
*   `playwright`: 用于驱动浏览器抓取实时数据。
*   标准 `logging` 模块 (或根据 `core` 配置的日志库)。

## 10. 异常处理与日志 (Error Handling & Logging)

*   脚本包含基本的 `try...except` 块。
*   日志记录由 `core.utils.setup_logging` (如果存在) 或 Python 标准 `logging` 模块处理。检查工作流脚本或 `main.py` 的日志配置部分。
*   日志通常输出到控制台和/或项目根目录下的 `logs/` 文件夹。

## 11. 未来工作 (Future Work)

*   完善历史数据的自动下载和处理逻辑。
*   增强错误处理和重试机制。
*   提供更详细的文档和示例。 