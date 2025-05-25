# 实时财经日历数据下载器 (`download_investing_calendar.py`)

## 1. 模块概述

本目录下的核心脚本是 `download_investing_calendar.py`。它的主要功能是使用 Playwright 库自动化访问 Investing.com 网站，抓取**当天**的财经日历数据，并将其直接保存为 **CSV 文件**。

**重要提示:** 此脚本是**实时数据处理工作流** (`economic_calendar/tasks/run_realtime_workflow.py`) 的**第一个步骤**，负责获取和初步格式化当天的原始数据。它通常由主工作流脚本自动调用。

## 2. 功能与输出

*   **访问目标:** 访问 `config/processing.yaml` 中 `economic_calendar.download.target_url` 指定的 URL (默认为 `https://cn.investing.com/economic-calendar/`)。
*   **数据提取:** 提取页面表格中的事件数据，包括时间、货币、重要性、事件名称、实际值、预测值、前值。
*   **格式调整:**
    *   **日期 (Date):** 所有事件的日期列统一设置为**脚本运行的当天日期** (格式 YYYY-MM-DD)。
    *   **重要性 (Importance):** 保存为**数字**格式 (例如 1, 2, 3)，代表网页上的星级。
    *   其他字段基本保持原始文本。
*   **输出:** 将提取并调整格式后的数据保存为 CSV 文件。
    *   **路径:** 由配置 `economic_calendar.paths.raw_live_dir` 指定。
    *   **文件名:** 由配置 `economic_calendar.files.raw_live_csv` 指定 (默认 `upcoming.csv`)。
*   **不进行筛选:** 此脚本**不执行**任何基于重要性、货币、关键词等的筛选操作，只负责下载和基本格式化。

## 3. 在工作流中的作用

在 `run_realtime_workflow.py` 中，此脚本 (`download_investing_calendar.py`) 被首先调用。成功执行后，它生成的原始 CSV 文件 (`upcoming.csv` 或配置指定的文件) 会作为下一步筛选脚本 (`filter_data_step.py`) 的输入。

## 4. 配置依赖

此脚本的行为主要通过 `config/processing.yaml` 控制，关键配置项包括：

*   `economic_calendar.download.target_url`: 要抓取的 URL。
*   `economic_calendar.download.timeout_seconds`: 页面加载和元素查找的超时时间。
*   `economic_calendar.paths.raw_live_dir`: 输出 CSV 文件存放的目录。
*   `economic_calendar.files.raw_live_csv`: 输出 CSV 文件的名称 (默认 `upcoming.csv`)。
*   `logging.*`: 日志相关配置。

## 5. 手动执行

虽然通常由工作流调用，但也可以手动运行此脚本进行测试：

```bash
# (确保已激活虚拟环境 .venv)
# 确保已安装依赖: pip install -r requirements.txt
# 确保已安装 playwright 浏览器: playwright install

python economic_calendar/economic_calendar_realtime/download_investing_calendar.py
```

成功运行后，将在配置指定的 `raw_live_dir` 目录下生成相应的 CSV 文件。

## 6. 环境与依赖

*   所有 Python 依赖项均由**项目根目录**的 `requirements.txt` 文件统一管理。
*   **必须** 安装 Playwright 及其浏览器驱动才能运行此脚本：
    ```bash
    # (激活虚拟环境)
    pip install -r requirements.txt
    playwright install
    ```

## 7. 参考主文档

要了解完整的实时数据处理工作流和数据结构，请参考模块主说明文档：`economic_calendar/README_CN.md`。
