# 工作流入口脚本说明

本文件说明 `economic_calendar/tasks` 目录下的主要工作流入口脚本。
这些脚本是推荐的自动化运行经济日历数据处理流程的方式。

## 配置文件结构

工作流脚本依赖于以下 YAML 配置文件，通过 `core.utils.load_app_config` 函数加载和合并：

1.  **`config/common.yaml` (项目根目录)**: 包含项目共享配置，如基础路径 (`paths.data_dir`, `paths.log_dir`)。
2.  **`economic_calendar/config/processing.yaml`**: 包含本模块特定的配置，如数据子目录路径 (`economic_calendar.paths`)、文件名 (`economic_calendar.files`)、筛选参数 (`economic_calendar.filtering`, `economic_calendar.currencies`, `economic_calendar.keywords_config`)、下载参数 (`economic_calendar.download`) 和 MT5 数据复制设置 (`economic_calendar.mt5_data_copy`)。

请在使用前确保配置文件中的路径等信息是正确的。

## 历史数据工作流 (`run_history_workflow.py`)

*   **目的**: 自动化处理本地存储的历史 HTML 文件，生成最终筛选后的历史事件数据。
*   **执行命令**: `python economic_calendar/tasks/run_history_workflow.py`
*   **流程**:
    1.  **加载配置**: 加载并合并 `common.yaml` 和 `processing.yaml`。
    2.  **处理 HTML**: 调用 `economic_calendar_history/scripts/process_calendar.py` 脚本。
        *   **输入**: `data/calendar/raw/history/` 目录下的所有 `.html` 文件。
        *   **输出**: 合并后的中间 CSV 文件 `data/calendar/processed/history/economic_calendar_history.csv`。
    3.  **筛选数据**: 调用 `economic_calendar/tasks/filter_data_step.py` (使用 `event_filter/logic.py`)。
        *   **输入**: 上一步生成的 `economic_calendar_history.csv` 文件。
        *   **输出**: 最终筛选结果写入 `data/calendar/filtered/history/filtered_historical.csv` 和数据库 `data/db/economic_events.db` (表 `events_history`)。

## 实时数据工作流 (`run_realtime_workflow.py`)

*   **目的**: 下载最新的经济日历页面 HTML，解析并筛选事件，并将结果（可选）复制到指定的 MT5 目录。
*   **执行命令**: `python economic_calendar/tasks/run_realtime_workflow.py`
*   **流程** (已更新):
    1.  **加载配置**: 加载并合并 `common.yaml` 和 `processing.yaml`。
    2.  **下载 HTML**: 调用 `economic_calendar_realtime/download_investing_calendar.py` 脚本。
        *   **输入**: Investing.com 网站实时页面。
        *   **输出**: 原始 HTML 源码保存到 `data/calendar/raw/live/` (文件名可在配置中修改，如 `realtime_calendar.html`)。
    3.  **处理 HTML**: 调用 `economic_calendar/tasks/process_realtime_html.py` 脚本。
        *   **输入**: 上一步下载的 HTML 文件。
        *   **输出**: 解析并初步清理后的中间 CSV 文件保存到 `data/calendar/processed/live/` (文件名可在配置中修改，如 `processed_live.csv`)。
    4.  **筛选数据**: 调用 `economic_calendar/tasks/filter_data_step.py` (使用 `event_filter/logic.py`)。
        *   **输入**: 上一步生成的中间 CSV 文件 (`processed_live.csv`)。
        *   **输出**: 最终筛选结果写入 `data/calendar/filtered/live/filtered_live.csv` 和数据库 `data/db/economic_events.db` (表 `events_live`)。
    5.  **(可选) 复制到 MT5**: 如果 `processing.yaml` 中 `economic_calendar.mt5_data_copy.copy_enabled` 为 `true`，则将 `filtered_live.csv` 文件复制到 `active_profile` 指定的 MT5 `MQL5/Files` 目录。

## 核心筛选逻辑 (`filter_data_step.py`)

`run_history_workflow.py` 和 `run_realtime_workflow.py` 都使用 `filter_data_step.py` 来执行核心的筛选逻辑。该脚本根据传入的模式（'history' 或 'realtime'）和配置文件中的设置（`economic_calendar.filtering`, `economic_calendar.currencies`, `economic_calendar.keywords_config` 等）来处理输入数据并生成相应的输出。

**重要**: 实时工作流现在将处理后的中间 CSV (`processed_live.csv`) 作为输入传递给 `filter_data_step.py`，而不是之前的原始 CSV (`upcoming.csv`)。

## 依赖与环境

*   运行前请确保已安装项目根目录 `requirements.txt` 中列出的所有 Python 依赖。
    ```bash
    pip install -r requirements.txt
    ```
*   对于实时工作流，如果需要网页抓取功能，请确保 Playwright 浏览器驱动已安装。
    ```bash
    playwright install
    ```

## 便捷运行方式

# (删除末尾不完整的句子)