# MT5 数据更新脚本 (market_price_data/scripts)

此目录包含用于运行 `market_price_data` 模块核心功能的 Python 脚本和批处理文件。

## 脚本在模块架构中的作用

这些脚本作为 `market_price_data` 模块核心功能的**执行入口**或**用户接口**。它们通常不包含核心的数据处理逻辑，而是负责：

1.  **解析用户输入:** 例如 `data_updater.py` 解析命令行参数，确定用户想要执行的操作（历史更新或实时监控）以及相关参数。
2.  **实例化核心引擎:** 根据用户请求，创建 `market_price_data` 模块中定义的 `HistoryUpdater` 或 `RealtimeUpdater` 类的实例。
3.  **调用核心方法:** 调用核心引擎实例的方法（如 `run_update_cycle()` 或 `start_updater()`）来启动实际的数据处理任务。
4.  **提供便捷方式:** `batch/` 目录下的批处理文件为 Windows 用户提供了更方便的脚本调用方式。

通过这种方式，脚本将用户交互与核心业务逻辑分离，使得模块的核心代码 (`history.py`, `realtime.py`) 更加内聚和可重用。这些脚本同样间接依赖于 `core.utils`（通过核心引擎类）和配置文件 (`config/updater.yaml`, `config/common.yaml`)。

## 主要脚本及其功能

1.  **`data_updater.py` (主要的命令行入口)**
    *   **目的**: 提供一个统一的命令行接口来执行历史或实时数据更新。
    *   **内部逻辑**: 根据接收到的子命令 (`history` 或 `realtime`)，实例化对应的核心引擎类 (`HistoryUpdater` 或 `RealtimeUpdater`)，并调用其主执行方法 (`run_update_cycle` 或 `start_updater`)。
    *   **用法**: 使用子命令 `history` 或 `realtime` 来指定操作。
        ```bash
        # 更新历史数据 (实例化 HistoryUpdater 并调用 run_update_cycle)
        python -m market_price_data.scripts.data_updater history

        # 启动实时数据监控 (实例化 RealtimeUpdater 并调用 start_updater, 仅用于测试)
        python -m market_price_data.scripts.data_updater realtime

        # 更新指定品种和周期的历史数据 (注意：当前版本可能未完全实现命令行覆盖)
        # python -m market_price_data.scripts.data_updater history -s EURUSD XAUUSD -t H1 D1

        # 监控指定品种和周期，并设置超时时间 (注意：当前版本可能未完全实现命令行覆盖)
        # python -m market_price_data.scripts.data_updater realtime -s EURUSD -t M5 M15 --timeout 3600

        # 覆盖日志级别 (注意：当前版本可能未完全实现命令行覆盖)
        # python -m market_price_data.scripts.data_updater history --log-level DEBUG
        ```
    *   **参数**: 支持 `-c/--config`, `-s/--symbols`, `-t/--timeframes`, `-l/--log-level`, `--timeout` (仅限实时)。
    *   **注意**: 命令行参数覆盖配置的功能可能未完全实现，当前主要依赖 `config/updater.yaml` 的设置。
    *   **实时模式**: 启动实时模式主要用于**单独测试和调试 `RealtimeUpdater`** 的功能。生产环境的实时数据服务**不推荐**使用此命令启动，而应由项目根目录的 `run_live_strategy.py` 脚本管理。

2.  **`run_updates.py`**
    *   **目的**: 一个简单的脚本，直接启动历史和实时更新流程，主要用于简单集成或测试。
    *   **内部逻辑**: 直接实例化 `HistoryUpdater` 和 `RealtimeUpdater` 类，然后分别调用 `run_update_cycle()` 和 `start_updater()`。
    *   **用法**: 可以直接执行。
        ```bash
        python market_price_data/scripts/run_updates.py
        ```
    *   **注意**: 不接受命令行参数，完全依赖配置文件。不推荐用此脚本启动生产环境的实时服务。

## 批处理文件 (`batch/`)

此子目录包含一些 `.bat` 文件，用于在 Windows 环境下方便地运行 Python 脚本。

-   **`update_history_data.bat`**: 用于手动运行历史数据更新，内部通常调用 `python -m market_price_data.scripts.data_updater history`。
-   **`run_history_update_scheduled.bat`**: 提供了一种设置 Windows 计划任务来定时运行历史数据更新的方法，配置其执行 `data_updater.py history`。

## 共享工具依赖 (`core.utils`)

这些脚本通过实例化和调用核心引擎类，间接依赖项目根目录下 `core/utils.py` 中的共享函数，用于配置加载、日志设置、MT5 操作等。

确保项目结构正确，以便脚本能够找到 `core` 模块。

## 目录结构 (更新后)

```
market_price_data/
├── ... (模块核心文件: __init__.py, history.py, realtime.py)
├── config/
│   └── updater.yaml
├── scripts/             # 脚本目录 (当前位置)
│   ├── data_updater.py  # 命令行工具入口
│   ├── run_updates.py   # 直接启动更新器的脚本
│   ├── batch/           # (Windows) 批处理文件目录
│   │   ├── update_history_data.bat        # 手动运行历史更新
│   │   └── run_history_update_scheduled.bat # 设置历史更新计划任务
│   └── README.md        # 说明文档 (本文件)
├── exporters/
│   └── ...
├── tools/
│   └── ...
└── README.md            # 模块主 README
```

## 使用建议

-   **更新历史数据:**
    -   **推荐使用命令行:** `python -m market_price_data.scripts.data_updater history`
    -   或者使用 `batch/update_history_data.bat` (Windows)。
    -   对于定时更新，配置 `batch/run_history_update_scheduled.bat` 并添加到 Windows 任务计划程序。
-   **启动实时监控:**
    -   **强烈建议通过项目根目录的 `run_live_strategy.py` 脚本来管理。**
    -   仅在需要单独测试时，才使用 `python -m market_price_data.scripts.data_updater realtime`。
-   **简单运行:** `python market_price_data/scripts/run_updates.py` 可用于快速运行一次历史更新并尝试启动实时更新（主要用于测试）。