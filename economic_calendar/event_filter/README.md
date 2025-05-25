# 事件筛选模块 (`economic_calendar/event_filter/`)

## 1. 模块概述

本模块提供了对经济日历事件进行筛选的核心逻辑。它支持基于多种条件的筛选，包括事件重要性、关键词、货币类型、时间范围等，并可以将筛选结果输出。

模块提供两种主要的筛选方式：

*   **内存筛选:** 直接处理 Python 列表或 Pandas DataFrame 中的事件数据。
*   **数据库筛选:** 直接从 SQLite 数据库文件中查询并筛选事件数据。

## 2. 核心功能与接口

### 内存筛选 (`logic.py: apply_memory_filters`)

这是最主要的筛选入口，功能最全面。

```python
from economic_calendar.event_filter.logic import apply_memory_filters

# 假设 events_list 是包含事件字典的列表，或 Pandas DataFrame
filtered_events_list = apply_memory_filters(
    events=events_list,                 # 输入事件列表或 DataFrame
    min_importance_threshold=2,         # 最小重要性 (1-3星)
    target_currencies=["USD", "EUR"],   # 目标货币列表 (可选)
    use_keywords_filter=True,           # 是否启用关键词筛选 (需要配置 keywords.py)
    # 细粒度关键词列表 (通常从 config/keywords.py 加载，可选)
    keywords_critical=["利率决议"], 
    keywords_speakers=["鲍威尔"], 
    keywords_high_impact=["非农"], 
    keywords_2star_specific={"USD": ["初请"]},
    start_time="08:00",                 # 筛选时间范围开始 (HH:MM, 可选)
    end_time="22:00",                   # 筛选时间范围结束 (HH:MM, 可选)
    add_market_open=True                # 是否添加美/欧市场开盘事件 (可选)
)
# 返回筛选并排序后的事件列表 (List[Dict[str, Any]])
```

### 数据库筛选 (`db.py: filter_events_from_db`)

用于直接从数据库文件进行筛选。

```python
from economic_calendar.event_filter.db import filter_events_from_db
import pandas as pd

filtered_df = filter_events_from_db(
    db_path="data/db/economic_events.db", # 数据库文件路径
    table_name="events_history",          # 要查询的表名
    min_importance=2,                     # 最小重要性
    currencies=["USD", "EUR"],            # 目标货币列表 (可选)
    start_date="2023-01-01",              # 开始日期 (YYYY-MM-DD, 可选)
    end_date="2023-12-31"                 # 结束日期 (YYYY-MM-DD, 可选)
)
# 返回包含筛选结果的 Pandas DataFrame
```

## 3. 文件说明

*   `logic.py`: 包含主要的**内存筛选**逻辑 (`apply_memory_filters`) 和相关的辅助筛选函数（按重要性、货币、关键词、时间等）。还包含 `process_events` 函数，用于封装加载-筛选-导出的流程。
*   `db.py`: 提供**数据库筛选**功能 (`filter_events_from_db`)。
*   `keywords.py` (**位于 `economic_calendar/config/` 目录下**): 定义用于内存筛选的关键词列表、重要发言人、特殊事件规则等。**这是内存筛选的关键依赖。**
*   `utils.py`: 提供各种辅助工具函数，如添加市场开盘事件、日期时间处理、市场状态判断等。
*   `constants.py`: 定义常量，可能包括时区、假日等（具体内容需查看文件）。
*   `enhancements.py`: (作用待确认，可能包含额外的处理或增强功能)。

## 4. 配置依赖

筛选功能的行为，特别是内存筛选，受到以下配置的影响：

*   **`economic_calendar/config/keywords.py`**: 定义了所有关键词筛选规则。
*   **`economic_calendar/config/processing.yaml`**: (通过调用方传入 `apply_memory_filters` 或 `process_events`)
    *   `economic_calendar.filtering.*`: 控制筛选的基本参数，如 `min_importance`、`add_market_open`、`use_keywords_filter` 等。
    *   `economic_calendar.currencies`: 指定默认的目标货币列表。

## 5. 在工作流中的使用

标准的用法是在自动化工作流脚本（如 `economic_calendar/tasks/run_realtime_workflow.py` 和 `run_history_workflow.py`）中被调用。这些脚本通常会：

1.  加载配置文件 (`common.yaml`, `processing.yaml`)。
2.  准备输入数据：
    *   **实时流程**: 下载 HTML -> 解析 HTML 生成中间 CSV (`processed_live.csv`)。
    *   **历史流程**: 解析历史 HTML 生成中间 CSV (`economic_calendar_history.csv`)。
3.  调用 `economic_calendar/tasks/filter_data_step.py`，该脚本内部会使用本模块的 `logic.py` 中的功能（可能是 `process_events` 或直接调用 `apply_memory_filters`）来执行筛选。
    *   **输入**: 上一步生成的**中间 CSV 文件** (无论是 `processed_live.csv` 还是 `economic_calendar_history.csv`)。
4.  工作流脚本负责传递必要的配置参数（如最小重要性、目标货币等）给筛选步骤。

**重要**: 本筛选模块的核心逻辑 (`apply_memory_filters`) 保持不变，但实时数据处理流程中**输入给它的数据来源**已经从直接的原始下载数据 (`upcoming.csv`) 变为了经过 HTML 解析和初步清理的中间数据 (`processed_live.csv`)，以确保与历史数据处理方式一致。

## 6. (不推荐) 独立使用示例

如果需要独立测试或在其他代码中直接使用筛选功能：

```python
import pandas as pd
from economic_calendar.event_filter.logic import apply_memory_filters
# 假设已加载关键词配置 (或传递 None 使用默认内部导入)
# from economic_calendar.config.keywords import CRITICAL_EVENTS, ... 

# 示例：筛选 CSV 文件
input_csv = "data/calendar/processed/history/economic_calendar_history.csv"
output_csv = "filtered_output.csv"

events_df = pd.read_csv(input_csv)

filtered_events = apply_memory_filters(
    events=events_df, 
    min_importance_threshold=2, 
    target_currencies=["USD", "EUR"], 
    use_keywords_filter=True
    # 可以传递从 keywords.py 导入的列表
    # keywords_critical=CRITICAL_EVENTS, ... 
)

if filtered_events:
    result_df = pd.DataFrame(filtered_events)
    result_df.to_csv(output_csv, index=False, encoding='utf-8')
    print(f"筛选结果已保存到 {output_csv}")
else:
    print("没有事件满足筛选条件。")

```

**注意:** 独立使用时，需要确保正确加载和传递 `config/keywords.py` 中的规则给 `apply_memory_filters` 函数的相应参数，否则关键词筛选将无法正常工作。 