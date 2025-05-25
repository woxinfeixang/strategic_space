# 回测模块 (Backtesting)

## 概述

本模块提供了一个事件驱动的回测框架，用于评估交易策略在历史数据上的表现。它模拟市场环境和交易执行，生成详细的绩效指标和报告，帮助开发者理解策略的潜在盈利能力和风险。

## 架构

回测系统主要由以下几个核心组件构成：

1.  **`BacktestEngine` (`engine.py`):**
    *   **角色:** 回测流程的总控制器和协调器。
    *   **职责:**
        *   加载配置。
        *   初始化其他所有组件。
        *   加载和预处理历史市场数据 (K 线) 和财经日历事件。
        *   构建并管理回测的时间序列。
        *   驱动回测循环，按时间顺序模拟市场进展。
        *   将数据分发给策略。
        *   调用结果生成和保存逻辑。

2.  **`DataProvider` (`strategies/core/data_providers.py`):**
    *   **角色:** 统一的数据供应接口。
    *   **职责:** 在回测模式下，负责从配置指定的历史数据源（通常是 `data/historical/` 和 `data/calendar/filtered/history/` 或数据库）加载 K 线和财经日历事件。确保数据按需提供给 `BacktestEngine`。

3.  **`SandboxExecutionEngine` (`strategies/live/sandbox.py`):**
    *   **角色:** 模拟经纪商/执行引擎。
    *   **职责:**
        *   接收来自策略的交易订单 (`place_order`, `cancel_order` 等)。
        *   **模拟订单撮合:** 根据当前市场价格（从回测数据中获取）模拟订单的成交。
        *   **管理模拟账户:** 跟踪持仓 (`positions`)、挂单 (`open_orders`)、账户余额 (`balance`)、净值 (`equity`) 等。
        *   **计算盈亏和成本:** 模拟计算交易的盈亏、佣金和滑点（如果配置）。
        *   **记录交易历史:** 保存所有已执行和关闭的交易记录 (`closed_trades`)。
        *   **记录资金曲线:** 按时间顺序记录账户净值的变化 (`equity_curve`)。

4.  **`RiskManager` (`strategies/core/risk_manager.py`):**
    *   **角色:** 风险管理策略执行者。
    *   **职责:** 在模拟环境中，根据策略信号和账户状态，决定是否允许交易、计算合适的交易手数等。它与 `SandboxExecutionEngine` 交互以获取账户信息。

5.  **`Strategy` (e.g., `strategies/*.py`):**
    *   **角色:** 被测试的交易策略逻辑。
    *   **职责:** 接收来自 `BacktestEngine` 的市场数据和事件，通过 `process_new_data` 方法分析数据，生成交易信号，并通过 `SandboxExecutionEngine` 和 `RiskManager` 发送模拟订单。

## 工作流程

一次典型的回测运行遵循以下步骤：

1.  **加载配置:** `BacktestEngine` 读取 `config/common.yaml` 中的 `backtest` 部分以及相关的策略参数配置 (`strategy_params`)。
2.  **初始化组件:** 引擎按顺序初始化 `DataProvider`, `SandboxExecutionEngine`, `RiskManager`, 以及配置中指定的 `Strategy` 实例。`SandboxExecutionEngine` 以 `backtest.initial_cash` 初始化模拟账户。
3.  **加载数据:** `BacktestEngine` 通过 `DataProvider` 加载指定时间范围 (`start_date`, `end_date`) 和交易品种 (`symbols`) 的历史 K 线数据，以及对应的财经日历事件。
4.  **构建事件流:** 引擎结合 K 线的时间戳和事件发生时间戳，创建一个统一的、按时间排序的回测时间点序列 (`backtest_timestamps`)。
5.  **回测循环:** 引擎遍历 `backtest_timestamps`：
    *   对于每个时间点 `t`：
        *   **准备数据:** 提取截至 `t` 时刻的所有 K 线数据 (`current_market_data`) 和在 `t` 时刻发生的事件 (`events_at_this_time`)。
        *   **调用策略:** 调用 `strategy.process_new_data(t, current_market_data, events_at_this_time)`。
        *   **模拟执行:** 如果策略发出交易信号，`RiskManager` 进行检查，然后 `SandboxExecutionEngine` 接收订单，模拟撮合，更新模拟账户状态（持仓、资金、交易记录）。
        *   **更新净值:** `BacktestEngine` 从 `SandboxExecutionEngine` 获取当前净值，记录到资金曲线 (`equity_curve`)。
6.  **生成结果:** 回测循环结束后，`BacktestEngine` 调用 `_generate_results` 方法：
    *   从 `SandboxExecutionEngine` 获取最终净值和资金曲线。
    *   使用 `quantstats` 库计算详细的绩效指标 (夏普率, 最大回撤, 胜率, 盈亏比, Sortino, Calmar 等)。
    *   计算期望收益 (Expectancy per Trade)。
    *   生成 QuantStats HTML 报告并保存到 `output/backtest_reports/` 目录下。
7.  **保存结果:** 调用 `_save_results_to_json` 方法，将本次回测的详细信息保存到 `backtesting/results/` 目录下的一个 JSON 文件中，文件名包含策略名和时间戳。保存内容包括：
    *   回测配置 (日期, 品种, 初始资金)
    *   策略参数
    *   计算出的所有绩效指标 (来自 QuantStats 和自定义计算)
    *   资金曲线数据 (`equity_curve_data`)
    *   可选的详细交易记录 (`trade_history`)，由 `backtest.save_trade_history` 配置控制。

## 运行回测

1.  **配置:**
    *   **主要配置:** 检查或修改 `config/common.yaml` 中的 `backtest` 部分，设置默认的回测时间范围 (`start_date`, `end_date`)、交易品种 (`symbols`)、初始资金 (`initial_cash`) 以及是否保存交易记录 (`save_trade_history`)。
    
    *   **脚本说明:**
        - `run_backtest.py`: 单策略回测入口脚本，支持命令行参数覆盖配置
        ```bash
        # 示例用法：
        python run_backtest.py --strategy SpaceTimeResonanceStrategy --symbols EURUSD,XAUUSD --timeframe H4
        ```
        - `run_all_backtests.py`: 批量回测脚本，特征：
          * 自动扫描 strategies/ 目录下的策略类
          * 支持并行回测（需配置 CPU 核心数）
          * 自动生成对比报告
          * 异常策略自动跳过
          * 支持自定义过滤条件（夏普率、最大回撤等）
          * 自动生成策略对比矩阵
        ```bash
        # 示例用法：
        python run_all_backtests.py --start 2020-01-01 --end 2023-12-31 --workers 4 --min-sharpe 1.2 --max-drawdown 20%
        ```
    *   **策略指定:** 你需要指定要回测的策略。这通常通过以下方式之一完成（具体取决于你的项目设置）：
        *   在 `config/common.yaml` 的 `backtest` 部分添加 `strategy_name: YourStrategyClassName`。
        *   创建一个专门的回测启动脚本 (e.g., `run_backtest.py`)，该脚本导入 `BacktestEngine`，并允许通过命令行参数或特定配置文件指定 `strategy_name`。
    *   **策略参数:** 确保 `config/strategy_params.yaml` (或其他策略参数文件) 中包含了要回测策略所需的参数。
2.  **数据准备:** 确保 `DataProvider` 配置的路径下存在所需交易品种和时间范围的历史 K 线数据和财经日历事件数据。
3.  **执行:** 运行回测的入口脚本 (例如，假设的 `run_backtest.py`)。脚本会实例化 `BacktestEngine` 并调用其 `run()` 方法。
    ```bash
    # 示例命令 (假设存在 run_backtest.py)
    python run_backtest.py --strategy-name EventDrivenSpaceStrategy --start-date 2022-01-01 --end-date 2023-12-31
    # 或者，如果配置在 common.yaml 中设置
    # python run_backtest.py # 使用 common.yaml 中的 backtest.strategy_name
    ```
    *(请根据你的实际项目结构调整运行方式)*

## 分析结果

回测完成后，你可以使用多种方式分析结果：

1.  **QuantStats HTML 报告:**
    *   **位置:** `output/backtest_reports/` 目录下，文件名类似 `<StrategyName>_<Timestamp>.html`。
    *   **内容:** 包含资金曲线图、月度/年度收益分析、各种绩效指标、交易统计等。非常直观。

2.  **JSON 结果文件:**
    *   **位置:** `backtesting/results/` 目录下，文件名类似 `<StrategyName>_<Timestamp>.json`。
    *   **内容:** 结构化的数据，包含所有配置、计算指标、资金曲线数据点和可选的交易历史。适合程序化处理和深度分析。

3.  **交互式筛选器 (`filter_app.py`):**
    *   **用途:** 提供一个 Web UI 界面，让你方便地根据关键指标（夏普、回撤、回报、交易次数）交互式地筛选 `backtesting/results/` 目录下的所有 JSON 结果。
    *   **运行:**
        ```bash
        python backtesting/filter_app.py
        ```
        然后在浏览器中打开提供的本地 URL (通常是 `http://127.0.0.1:7860` 或 `http://0.0.0.0:7860`)。
    *   **使用:** 在界面输入筛选条件（留空表示不限制），点击 "开始筛选"，下方表格会显示符合条件的结果摘要。

4.  **自动筛选报告 (`auto_filter.py`):**
    *   **用途:** 自动扫描 `backtesting/results/` 目录，根据脚本内预设的硬性门槛和排名优先级，筛选并排名策略，最后在终端打印出完整的分析报告，指出最优策略及其原因。
    *   **运行:**
        ```bash
        python backtesting/auto_filter.py
        ```
    *   **自定义:** 你可以编辑此脚本顶部的 `HARD_THRESHOLD` 和 `RANKING_PRIORITY` 变量来调整自动筛选的标准。

## 配置项

关键的回测配置项位于 `config/common.yaml` 的 `backtest` 部分：

*   `initial_cash`: 模拟账户的初始资金。
*   `start_date`: 回测开始日期 (YYYY-MM-DD)。
*   `end_date`: 回测结束日期 (YYYY-MM-DD)。
*   `strategy_name`: (可选，如果在脚本中指定则不需要) 要运行回测的策略类名。
*   `symbols`: 要包含在回测中的交易品种列表。
*   `save_trade_history`: (布尔值, `true` 或 `false`) 是否在 JSON 结果中保存详细的交易记录。
*   `stop_on_error`: (布尔值) 策略执行过程中遇到错误时是否中止回测。
