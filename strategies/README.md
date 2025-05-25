# 交易策略模块 (`strategies`)

本模块包含在战略空间框架内各种交易策略的核心逻辑和实现。

## 核心组件

以下是对核心组件及其内部具体工作机制的详细描述：

-   **`core/strategy_base.py` (`StrategyBase`)**: 
    *   **职责**: 作为所有策略类的抽象父类，强制子类实现核心的 `process_new_data` 方法，并提供通用的基础设施。
    *   **初始化 (`__init__`)**: 
        *   接收 `config` (一个 `DictConfig` 对象，包含 `strategy_params` 下该策略的特定配置)、`data_provider` 实例和 `execution_engine` 实例。
        *   初始化一个空的 `positions` 字典用于（未来实现的）持仓跟踪。
        *   使用 `logging.getLogger(self.__class__.__name__)` 获取一个以子类策略名称命名的 logger 实例。
        *   记录一条 INFO 级别的日志，表明策略已初始化。
    *   **核心接口 (`process_new_data`)**: 
        *   这是一个 `@abstractmethod`，意味着所有具体的策略子类**必须**重写此方法。
        *   由 `StrategyOrchestrator` 在每个处理周期调用。
        *   接收 `current_time` (datetime), `market_data` (嵌套字典 `Dict[TimeframeStr, Dict[SymbolStr, pd.DataFrame]]`), 以及 `event_data` (Optional `pd.DataFrame`) 作为输入。
        *   **设计目的**: 在此方法内实现策略的主要逻辑，分析传入的数据，并决定是否生成交易信号。
    *   **订单准备 (`prepare_order`)**: 
        *   **输入**: `signal_data` (字典)，至少需要包含 `symbol`, `side`, `order_type`。
        *   **注意**: `volume` 字段应由 RiskManager 计算，但 `prepare_order` 仍然需要它来创建 Order 对象。传递给 `place_order_from_signal` 的 `signal_data` 中的 `volume` 会被忽略。
        *   **内部逻辑**: 
            *   检查 `signal_data` 中是否存在 `client_order_id` 键。如果不存在或其值为 `None`，则使用 f-string 格式 `f"{self.get_name()}_{int(datetime.now().timestamp() * 1000)}"` 生成一个包含策略类名和当前毫秒级时间戳的唯一 ID。
            *   尝试使用 `signal_data` 中的值创建 `Order` 数据类的实例（假设 `Order`, `OrderSide`, `OrderType` 已正确导入或定义）。
            *   显式地将 `signal_data['side']` 和 `signal_data['order_type']` 转换为相应的枚举类型 (`OrderSide(signal_data['side'])`, `OrderType(signal_data['order_type'])`)。
            *   将 `signal_data['volume']` 转换为 `float` 类型。
            *   从 `signal_data` 中读取可选参数 `limit_price`, `stop_price`, `stop_loss`, `take_profit`。
            *   在创建的 `Order` 对象的 `metadata` 字典中，强制添加或更新键 `'strategy_name'`，其值为当前策略的类名 (`self.get_name()`)。
            *   如果 `signal_data` 中包含 `metadata` 字典，则将其内容更新（`update`）到 `Order` 对象的 `metadata` 中（会覆盖同名键）。
            *   记录一条 DEBUG 级别的日志，包含准备好的订单 ID 和策略名称。
        *   **错误处理**: 使用 `try...except` 块捕获 `KeyError` (缺少必要字段) 和 `ValueError` (值类型错误)，并记录 ERROR 级别的日志，返回 `None`。
        *   **输出**: 返回一个配置好的 `Order` 对象实例，如果准备失败则返回 `None`。
    *   **信号下单 (`place_order_from_signal`)**: 
        *   **输入**: `signal_data` (字典)。
        *   **内部逻辑**: 
            1. 调用 `self.prepare_order(signal_data)` 获取 `Order` 对象。
            2. 如果 `prepare_order` 返回有效的 `Order` 对象：
                a. 记录一条 INFO 级别的日志，说明正在尝试下单，并包含订单的字典表示 (`order_to_place.to_dict()`)。
                b. 调用 `self.execution_engine.place_order(order_to_place)` 将订单交给执行引擎处理。
                c. 检查执行引擎返回的结果 `executed_order`：
                    i. 如果 `executed_order` 非 `None` (表示引擎接受并处理了订单)：
                        *   记录一条 INFO 级别的日志，包含订单的 `client_order_id` 和状态 (`executed_order.status.value`)。
                        *   **关键判断**: 检查 `executed_order.status` 是否为 `OrderStatus.FILLED` 或 `OrderStatus.PARTIALLY_FILLED`。如果是，则调用 `self.update_positions(executed_order)` (当前 `update_positions` 仅打印日志，无实际逻辑)。
                        *   返回 `executed_order` 对象。
                    ii. 如果 `executed_order` 为 `None` (表示执行引擎未能处理，可能是连接问题等)：
                        *   记录一条 ERROR 级别的日志，说明执行引擎未能处理订单。
                        *   返回 `None`。
        *   **错误处理**: 外层有 `try...except Exception` 块，捕获执行引擎下单过程中可能出现的任何异常，记录 ERROR 日志（包含堆栈信息 `exc_info=True`），并返回 `None`。
        *   **输出**: 返回执行引擎处理后的 `Order` 对象（可能状态已更新），或者在任何失败情况下返回 `None`。
    *   **持仓更新 (`update_positions`)**: 
        *   **输入**: 已执行的 `Order` 对象。
        *   **当前实现**: 仅记录一条 DEBUG 日志，提示此功能未完全实现。**没有实际更新 `self.positions` 的逻辑。**
    *   **获取名称 (`get_name`)**: 
        *   一个 `@classmethod`，返回调用该方法的类自身的名称 (`cls.__name__`)。
    *   **合约规格获取 (`get_symbol_info`)**: 
        *   **新增方法**: 负责获取指定交易品种的合约规格（如合约大小、点值、最小手数、步长等）。
        *   **内部逻辑**: 
            1.  **优先尝试 MT5**: 如果 `MarketDataProvider` 已连接到 MT5 (`self.mt5_connected`)，则调用 `mt5.symbol_info(symbol)` 获取实时规格。
                *   需要将 MT5 返回的信息解析并转换为标准字典格式。
                *   **注意**: MT5 返回的 `tick_value` 可能需要根据账户货币进行转换（当前实现包含占位符和警告）。
            2.  **回退到配置文件**: 如果未连接 MT5 或获取失败，则尝试从 `__init__` 中加载的 `config/instrument_specs.yaml` 文件内容 (`self.instrument_specs`) 中查找对应 `symbol` 的规格。
                *   检查获取到的规格信息是否包含所有必需的键 (`contract_size`, `tick_size`, `tick_value`, `volume_min`, `volume_step`)。
        *   **输出**: 返回包含合约规格的字典，如果找不到或信息不完整则返回 `None`。

-   **`core/data_providers.py` (`MarketDataProvider`, 等)**: 
    *   **`MarketDataProvider`**: 
        *   **职责**: (假设) 负责从数据源（如 CSV 文件、数据库、实时 API）获取指定交易品种 (`symbol`) 和时间周期 (`timeframe`) 的 K 线数据 (OHLCV)。
        *   **核心方法 (`get_market_data`)**: 
            *   **输入**: `symbols` (List[str]), `timeframes` (List[str]), `start_time`, `end_time` (或 `lookback_periods`)。
            *   **内部逻辑**: (假设基于文件) 遍历 `symbols` 和 `timeframes` 的组合，查找对应的 CSV 文件路径（可能基于某种命名约定）。读取 CSV 文件内容到 `pandas.DataFrame`。根据请求的时间范围或回溯期筛选数据。
            *   **时区处理**: 读取CSV文件中的时间字符串（格式为'%Y-%m-%d %H:%M:%S'，代表UTC时间）后，**将其解析并本地化为带时区的 UTC 时间** (`df.index = df.index.tz_localize('UTC')`)。
            *   将结果存储在嵌套字典 `result[timeframe][symbol] = df` 中。
            *   **缓存**: (假设) 可能包含内存缓存机制，避免重复读取文件。
            *   **错误处理**: 文件未找到、数据格式错误、时间范围无效等情况的处理，可能返回空 DataFrame 或部分数据，并记录警告/错误日志。
        *   **输出**: 返回 `Dict[TimeframeStr, Dict[SymbolStr, pd.DataFrame]]` 结构的数据，**其中 DataFrame 的索引是 UTC 时间**。
    *   **`EconomicCalendarProvider`**: 
        *   **职责**: (假设) 获取财经日历事件数据。
        *   **核心方法 (`get_events`)**: 
            *   **输入**: 时间范围 `start_time`, `end_time`, 可能还有重要性 (`importance`)、国家/地区 (`countries`)、事件类型 (`event_types`) 等筛选条件。
            *   **内部逻辑**: (假设) 可能调用外部库 (如 `investpy`) 或 API，或者读取预存的数据文件。根据输入参数筛选事件。
            *   **时区处理**: 读取的事件时间戳，如果是naive类型，会**假定其代表北京时间并本地化为 `Asia/Shanghai`**；如果已经是时区感知类型但非北京时间，则会**转换为北京时间**。
        *   **输出**: `pd.DataFrame`，**其中时间列（如 `datetime`）是 `Asia/Shanghai` 时区**。
    *   **`DataProvider` (门面类)**: 
        *   **职责**: (假设) 整合 `MarketDataProvider` 和 `EconomicCalendarProvider`，提供统一的数据访问接口。
        *   **方法**: 可能包含 `get_consolidated_data` 方法，内部调用其他 Provider 获取数据并组合返回。

-   **`core/strategy_orchestrator.py` (`StrategyOrchestrator`)**: 
    *   **职责**: 系统的核心调度器，负责加载、初始化和按周期运行所有配置的策略。
    *   **初始化 (`__init__`)**: 
        *   接收 `config` (全局合并后的配置), `data_provider` 实例, `execution_engine` 实例。
        *   读取 `config.realtime.symbols` 和 `config.realtime.timeframes` 以确定需要关注的市场数据。
        *   读取 `config.strategies` (假设是一个列表或字典，包含要启用的策略名称及其参数路径)。
        *   动态导入并实例化在 `config.strategies` 中指定的每个策略类，将 `config.strategy_params[strategy_name]`、`data_provider` 和 `execution_engine` 传递给策略的构造函数。
        *   将实例化的策略对象存储在一个列表 `self.strategies` 中。
    *   **运行循环 (`run`)**: 
        *   启动一个主循环（可能是基于定时器 `schedule` 或简单的 `while True` 配合 `time.sleep`）。
        *   在每个循环周期（`_run_cycle`）:
            1. 获取当前时间 `current_time` (通常为 UTC)。
            2. 调用 `self.data_provider.market_provider.get_combined_prices(...)` 获取最新的市场数据 `market_data` (**返回的数据索引为 UTC 时间**)。
            3. 调用 `self.data_provider.economic_provider.get_filtered_events(...)` 获取最新的事件数据 `event_data` (**返回的数据时间列为北京时间 `Asia/Shanghai`**)。
            4. 遍历 `self.strategies` 列表中的每一个策略实例 `strategy`。
            5. 调用 `strategy.process_new_data(current_time, market_data, event_data)`，将最新数据传递给策略进行处理。
            6. 处理可能的异常，确保单个策略的失败不影响整个编排器的运行。

-   **`live/execution_engine.py` (`ExecutionEngineBase`, `MT5ExecutionEngine`)**: 
    *   **`ExecutionEngineBase`**: 
        *   **职责**: 定义执行引擎的抽象接口，所有具体的引擎（如 MT5、模拟引擎）都必须继承它。
        *   **核心抽象方法**: 
            *   `place_order(order: Order)`: 接收标准化的 `Order` 对象，负责将其提交给交易平台。
            *   `cancel_order(order_id: str)`: 根据订单 ID 取消一个未成交的订单。
            *   `get_order_status(order_id: str)`: 查询特定订单的状态。
            *   `get_position(symbol: str)`: 获取指定交易品种的当前持仓信息。
            *   `connect()`: 连接到交易平台。
            *   `disconnect()`: 断开连接。
    *   **`MT5ExecutionEngine`**: 
        *   **职责**: 实现 `ExecutionEngineBase` 接口，具体对接 MetaTrader 5 平台。
        *   **初始化 (`__init__`)**: 接收 MT5 的连接参数（账号、密码、服务器）等，通常来自全局配置。
        *   **连接 (`connect`)**: 调用 `MetaTrader5` 库的 `initialize` 和 `login` 函数建立连接。
        *   **下单 (`place_order`)**: 
            1. **关键步骤**: 从输入的 `Order` 对象的 `client_order_id` 字段获取由策略生成的唯一 ID。
            2. **计算 Magic Number**: 对 `order.client_order_id` 字符串进行 **哈希处理** (具体哈希算法可能需要查看代码，假设是 `hash()` 或 `md5` 等后取模或截断) 得到一个整数，作为 MT5 订单的 `magic` number。**这是将内部订单与 MT5 订单关联的关键机制。**
            3. 构建 MT5 `trade_request` 字典，将 `Order` 对象的字段（symbol, volume, type, price, sl, tp）映射到 MT5 请求的相应字段（如 `symbol`, `volume`, `type`, `price`, `sl`, `tp`）。需要注意 MT5 的订单类型枚举 (如 `ORDER_TYPE_BUY`, `ORDER_TYPE_SELL`, `ORDER_TYPE_BUY_LIMIT` 等) 和 `OrderType` 枚举的转换。
            4. 调用 `MetaTrader5.order_send(trade_request)` 发送订单请求。
            5. 处理 `order_send` 返回的 `result` 对象。检查 `result.retcode` 是否表示成功 (`TRADE_RETCODE_DONE`)。如果成功，更新 `Order` 对象的状态为 `PENDING` 或 `NEW` (取决于 MT5 的具体行为)，并可能将 MT5 返回的 `order` (订单号) 存入 `Order.order_id`。如果不成功，记录错误日志，设置 `Order` 状态为 `REJECTED`。
            6. 返回更新后的 `Order` 对象或在失败时返回 `None`。
        *   **其他方法**: 实现 `cancel_order`, `get_order_status`, `get_position` 等方法，分别调用 `MetaTrader5.order_cancel`, `MetaTrader5.history_orders_get` / `MetaTrader5.positions_get` 等相关 MT5 API 函数。

## 数据流 (详细步骤)

1.  `StrategyOrchestrator` 在其 `_run_cycle` 方法中确定需要的数据范围（基于 `self.symbols`, `self.timeframes`）。
2.  调用 `self.data_provider.market_provider.get_combined_prices(...)` (或类似方法)。`MarketDataProvider` 内部读取相应的 CSV 文件，**将时间索引本地化为 UTC**，并构造成嵌套字典 `market_data: Dict[str, Dict[str, pd.DataFrame]]` 返回。
3.  (如果需要事件数据) 调用 `self.data_provider.economic_provider.get_filtered_events(...)`。`EconomicCalendarProvider` 获取符合条件的事件，**将时间处理为北京时间 (`Asia/Shanghai`)**，返回 `event_data: pd.DataFrame`。
4.  `StrategyOrchestrator` 循环遍历 `self.strategies` 列表。
5.  对列表中的每个 `strategy` 实例，调用 `strategy.process_new_data(current_time, market_data, event_data)`。
6.  在 `strategy.process_new_data` 内部：
    *   策略逻辑访问 `market_data[所需时间周期][所需交易品种]` 获取对应的 DataFrame 进行分析 (**注意：索引是 UTC 时间**)。
    *   如果 `event_data` 非 `None`，策略逻辑访问 `event_data` 进行分析 (**注意：时间列是北京时间 `Asia/Shanghai`**)。
    *   **关键步骤**: 在进行任何依赖时间的操作（如比较市场数据和事件时间、基于时间窗口的计算等）之前，策略**必须**将 `event_data` 中的北京时间**转换为 UTC 时间**，以确保所有时间都在同一基准下进行处理。
    *   基于分析结果（在统一的 UTC 时区下），策略判断是否触发交易信号。

## 订单下单与跟踪 (详细步骤)

1.  **策略内部**: 当 `process_new_data` (或其调用的内部方法) 决定下单时，创建一个 `signal_data` 字典，例如：
    ```python
    signal = {
        'symbol': 'EURUSD',
        'side': 'BUY', # 或者 OrderSide.BUY.value
        'order_type': 'MARKET', # 或者 OrderType.MARKET.value
        'volume': 0.01,
        'stop_loss': 1.08000,
        'take_profit': 1.10000,
        'metadata': {'comment': 'Entry based on event X'}
        # client_order_id 可以省略，让 prepare_order 生成
    }
    ```
2.  **调用下单入口**: `executed_order = self.place_order_from_signal(signal)`
3.  **进入 `place_order_from_signal`**:
    *   调用 `calculated_volume = self.risk_manager.calculate_position_size(signal)`。
    *   检查 `calculated_volume` 是否有效。如果无效（如 `None` 或 <= 0），记录警告/错误并返回 `None`。
    *   如果有效，将 `signal['volume'] = calculated_volume` 更新信号数据。
    *   调用 `order_to_place = self.prepare_order(signal)`
4.  **进入 `prepare_order`**:
    *   `client_order_id` 不存在，生成 `client_id = f"MyStrategyName_{int(datetime.now().timestamp() * 1000)}"`。
    *   创建 `Order` 对象，使用**风险管理器计算出的 `volume`**: `order = Order(..., volume=calculated_volume, ...)`。
    *   更新元数据：`order.metadata['strategy_name'] = 'MyStrategyName'`, `order.metadata.update({'comment': 'Entry based on event X'})`。
    *   返回 `order` 对象。
5.  **回到 `place_order_from_signal`**: `order_to_place` 有效。
    *   记录尝试下单日志。
    *   调用 `executed_order_result = self.execution_engine.place_order(order_to_place)` (假设 `execution_engine` 是 `MT5ExecutionEngine` 实例)。
6.  **进入 `MT5ExecutionEngine.place_order`**:
    *   获取 `client_id = order_to_place.client_order_id`。
    *   计算 `magic_number = calculate_hash(client_id)` (具体哈希方法见代码)。
    *   构建 `request = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': 'EURUSD', 'volume': 0.01, 'type': mt5.ORDER_TYPE_BUY, 'magic': magic_number, 'sl': 1.08000, 'tp': 1.10000, ...}`。
    *   调用 `mt5_result = mt5.order_send(request)`。
    *   检查 `mt5_result.retcode`。假设成功 (`TRADE_RETCODE_DONE`)。
    *   更新 `order_to_place.status = OrderStatus.NEW` (或 PENDING)。
    *   `order_to_place.order_id = mt5_result.order` (MT5 订单号)。
    *   返回更新后的 `order_to_place`。
7.  **回到 `place_order_from_signal`**: `executed_order_result` 非 `None`。
    *   记录订单状态日志，如 "订单 MyStrategyName_1678886400000 状态: NEW"。
    *   检查状态：`executed_order_result.status` 是 `NEW`，不满足 `FILLED` 或 `PARTIALLY_FILLED`，**不调用** `update_positions`。
    *   返回 `executed_order_result`。
8.  **策略内部**: 收到 `executed_order` 对象，可以根据需要检查其状态。

## 配置要求 (详细说明)

策略运行依赖于合并后的全局配置对象。以下是关键配置项及其影响：

-   **`realtime.symbols` (List[str])**: `StrategyOrchestrator` 初始化时读取，决定了 `MarketDataProvider` 需要为哪些交易品种准备数据。如果策略需要的数据不在这个列表里，`process_new_data` 中的 `market_data` 将不包含对应键。
-   **`realtime.timeframes` (List[str])**: 同上，决定了 `MarketDataProvider` 需要准备哪些时间周期的数据。
-   **`event_mapping.currency_to_symbol` (Dict[str, str])**: (特定于 `EventDrivenSpaceStrategy` 或类似策略) 用于将财经日历事件中的货币代码（如 "USD"）映射到具体的交易品种（如 "EURUSD"），以便策略知道哪个品种可能受到事件影响。
-   **`strategy_params.{StrategyName}` (Dict)**: 这是传递给名为 `{StrategyName}` 的策略类构造函数的 `config` 参数。策略内部通过 `self.config.get('param_name', default_value)` 来访问其特定参数。
    *   例如：`strategy_params.EventDrivenSpaceStrategy.primary_timeframe` (str): 被 `EventDrivenSpaceStrategy` 用来决定主要分析哪个时间周期的数据（如 "H1"）。
-   **`config.risk_manager` (Dict)**: 用于配置风险管理器。
    *   `type` (str): 指定要使用的风险管理器类型，如 "FixedFractional"。
    *   `params` (Dict): 传递给所选风险管理器构造函数的参数。
        *   例如 `FixedFractional` 需要 `risk_per_trade_percent`, `min_lot_size`, `lot_step`。

## 已实现的策略 (详细逻辑待补充)

-   **`EventDrivenSpaceStrategy`**: 
    *   继承自 `StrategyBase`。
    *   **核心功能**: 作为事件驱动型空间交易策略的基类。它负责响应财经日历中的重要事件，动态地创建和管理"博弈空间"（通常基于事件发生后一段时间内的价格高低点）。策略会监控价格与这些动态空间边界的交互，并在边界附近寻找潜在的交易机会。核心逻辑包括空间的创建、激活、根据特定条件（如时间衰减、价格突破、新事件出现）进行失效处理。
    *   **P0阶段主要修复与增强**: 显著改进了空间失效逻辑的鲁棒性和准确性，确保空间边界计算的正确性，统一了事件数据和市场数据的时间处理（全部转换为UTC基准进行内部计算），并完善了日志记录。
    *   需要 `primary_timeframe` 和 `event_mapping` (在 `config.strategy_params.EventDrivenSpaceStrategy` 中配置) 等参数，用于确定主要分析的时间框架和如何将事件关联到具体交易品种。
    *   其 `process_new_data` 方法是策略驱动的核心，负责处理新的市场K线和事件数据，更新空间状态，并调用 `_execute_trading_logic`。
    *   `_execute_trading_logic` 是一个虚方法，期望子策略重写以实现具体的交易信号产生逻辑。

-   **`ReverseCrossoverStrategy`**:
    *   继承自 `EventDrivenSpaceStrategy`。
    *   **核心逻辑**: 当价格从博弈空间外部反向穿越回空间内部，并且满足一定的过滤条件（如穿越幅度、成交量配合）时，产生交易信号。
    *   **P1.1阶段主要修复与增强**: 增加了更为灵活的回调入场模式 (`entry_on_retrace=True`)，允许策略在初始突破后等待价格回调至边界附近再入场，以期获得更好的入场点。相关的参数如回调缓冲、等待K线数等也已加入。

-   **`ExhaustionStrategy`**:
    *   继承自 `EventDrivenSpaceStrategy`。
    *   **核心逻辑**: 在价格接近博弈空间边界时，通过分析一系列价格行为特征（如长影线、小实体K线）和技术指标（如RSI背离、MACD柱状图收缩）来识别当前趋势动能衰竭的信号，从而在边界附近捕捉反转机会。
    *   **P1.2.A阶段主要修复**: 解决了多个核心缺陷，包括：修正了获取当前持仓的逻辑（之前为硬编码），统一了内部代码对空间边界键名的引用（使用父类定义的 `high`/`low`），移除了子策略中不必要的对父类已有方法的覆盖（如 `process_new_data`, `_get_pip_size`），使得代码更简洁并依赖父类实现。

-   **`KeyTimeWeightTurningPointStrategy`**:
    *   继承自 `EventDrivenSpaceStrategy`。
    *   **核心逻辑**: 专注于重要财经事件发布后的关键时间窗口。在此窗口内，当价格运行至博弈空间边界附近时，结合对成交量分布（如VWAP变化）和订单流（如大单净流向）的"权重"分析，判断是否形成机构资金重新分配的"拐点"，并据此交易。
    *   **P1.3阶段主要修复**: 解决了多个核心缺陷，包括：确保从父类正确获取 `pip_size`，修正了其子策略检查器 (`_str_checker`) 的初始化逻辑，规范了对活跃空间列表 (`self.active_spaces`) 的访问方式，并初步实现了判断是否为"主要拐点" (`_is_main_turning_point`) 的逻辑框架。

-   **`SpaceTimeResonanceStrategy`**: 
    *   继承自 `EventDrivenSpaceStrategy`。
    *   **核心逻辑**: 试图捕捉价格行为与时间周期的"共振"点。当价格触及博弈空间边界的同时，通过时间周期分析（如利用FFT识别的主导周期达到关键转折点）也指示潜在反转时，产生交易信号。
    *   **P1.4阶段主要修复**: 解决了多个核心缺陷，包括：增强了对父类 `_map_event_to_symbol` 方法的兼容性（即使没有事件也能正常运行），澄清了关于S2阶段事件处理的TODO（相关逻辑已由父类 `_find_active_spaces_for_event` 覆盖），统一了内部 `_is_key_time` 的判断逻辑以适配父类对事件窗口的处理，修正了从配置文件读取参数的键名，并简化了其 `process_new_data` 方法，使其直接调用父类实现。
    *   其 `process_new_data` 方法内部会将接收到的北京时间事件数据转换为 UTC，然后执行后续逻辑。
    *   具体实现细节：(需要查看 `SpaceTimeResonanceStrategy` 代码来补充，例如它如何定义"耗尽模式"，如何精确地在边界附近下单)。

## 实现新策略 (详细步骤)

1.  在 `strategies` 目录下创建 `my_new_strategy.py`。
2.  写入代码：
    ```python
    import logging
    import pandas as pd
    from .core.strategy_base import StrategyBase
    from .live.order import OrderSide, OrderType # 假设的导入
    from typing import Dict, Optional
    from datetime import datetime

    class MyNewStrategy(StrategyBase):
        def __init__(self, config, data_provider, execution_engine):
            super().__init__(config, data_provider, execution_engine)
            # 读取策略特定参数
            self.my_param = self.config.get('my_param', 10)
            self.logger.info(f"MyNewStrategy initialized with my_param={self.my_param}")

        def process_new_data(self, current_time: datetime,
                             market_data: Dict[str, Dict[str, pd.DataFrame]],
                             event_data: Optional[pd.DataFrame]) -> None:
            self.logger.debug(f"Processing data at {current_time}")
            
            # 访问特定数据
            try:
                eurusd_h1_df = market_data.get('H1', {}).get('EURUSD')
                if eurusd_h1_df is None or eurusd_h1_df.empty:
                    self.logger.warning("EURUSD H1 data not available.")
                    return
                
                last_close = eurusd_h1_df['close'].iloc[-1]
                self.logger.debug(f"Last EURUSD H1 close: {last_close}")

                # --- 在这里实现您的核心交易逻辑 ---
                # 例如：简单的均线交叉 (在 UTC 时间下进行)
                # ma_short = eurusd_h1_df['close'].rolling(window=self.my_param).mean().iloc[-1]
                # ma_long = eurusd_h1_df['close'].rolling(window=self.my_param * 2).mean().iloc[-1]
                # if ma_short > ma_long:
                #    signal_side = OrderSide.BUY.value
                # else:
                #    signal_side = OrderSide.SELL.value

                # --- 如果需要结合事件数据，确保事件时间已转为 UTC --- 
                # if event_data is not None:
                #     events_utc = event_data.copy()
                #     events_utc['datetime_utc'] = events_utc['datetime'].dt.tz_convert('UTC')
                #     # ... 使用 events_utc['datetime_utc'] 进行比较 ...

                # --- 假设满足了某个条件，决定下单 ---
                if last_close > 1.09000: # 示例条件
                    signal_data = {
                        'symbol': 'EURUSD',
                        'side': OrderSide.BUY.value,
                        'order_type': OrderType.MARKET.value,
                        'volume': 0.02,
                        'metadata': {'reason': 'Price above threshold'}
                    }
                    self.logger.info("Generating BUY signal for EURUSD")
                    executed_order = self.place_order_from_signal(signal_data)
                    if executed_order:
                        self.logger.info(f"Order placed, status: {executed_order.status.value}")
                    else:
                        self.logger.error("Failed to place order.")

            except KeyError as e:
                self.logger.error(f"Data access error: {e}")
            except Exception as e:
                self.logger.error(f"Error in process_new_data: {e}", exc_info=True)

    ```
3.  **配置**: 在主配置文件 (例如 `config.yaml` 或 `main.py` 中构建配置的地方) 的 `strategy_params` 下添加：
    ```yaml
    strategy_params:
      MyNewStrategy:
        my_param: 20 # 覆盖默认值 10
      # ... 其他策略参数 ...
    ```
4.  **注册**: 在创建 `StrategyOrchestrator` 的地方，确保 `MyNewStrategy` 被包含在要加载的策略列表中。这通常通过读取配置的 `strategies` 部分来完成，需要确保 `MyNewStrategy` 的名称出现在该列表中，例如：
    ```yaml
    strategies:
      - name: MyNewStrategy # 确保策略名称在这里
      - name: EventDrivenSpaceStrategy
      # ...
    ```
    或者，如果手动实例化：
    ```python
    from strategies.my_new_strategy import MyNewStrategy
    # ...
    strategy_instances = [
        MyNewStrategy(config.strategy_params.MyNewStrategy, data_provider, execution_engine),
        # ... 其他策略实例 ...
    ]
    orchestrator = StrategyOrchestrator(config, data_provider, execution_engine, strategy_instances)
    ```

## 目录结构

```
strategies/
├── core/                     # 核心框架组件
│   ├── data_providers.py       # 为策略提供市场和日历数据
│   ├── event_driven.py         # 事件驱动策略的基类
│   ├── space_calculator.py     # 计算"事件空间"的逻辑
│   ├── strategy_base.py        # 所有策略的抽象基类
│   ├── strategy_orchestrator.py # 加载、配置和运行策略
│   └── __init__.py             # 包初始化文件
├── live/                     # 实盘交易执行组件
│   ├── execution_engine.py     # 执行引擎的抽象基类
│   ├── mt5_engine.py           # 使用 MetaTrader 5 的执行引擎
│   ├── order.py                # 标准化订单数据类和枚举
│   ├── sandbox.py              # 用于测试的沙盒/模拟执行引擎
│   └── __init__.py             # 包初始化文件
├── backtest/                 # 策略特定回测配置/脚本 (目前为空)
├── config/
│   └── strategies.yaml           # 模块特定配置文件
├── requirements.txt          # 模块的直接第三方依赖 (说明性)
├── event_driven_space_strategy.py # 事件驱动空间策略的实现
├── README.md                 # 本文档
└── 创建博弈空间.md          # 事件驱动空间概念的详细规则定义
```

## 依赖 (`requirements.txt`)

模块根目录下的 `requirements.txt` 文件列出了 `strategies` 模块**直接依赖**的第三方 Python 库（如 `pandas`）。这有助于理解模块的外部需求。

**注意:** 项目完整的依赖列表由项目根目录的 `requirements.txt` 文件管理。模块级的 `requirements.txt` 主要起说明作用。

## 核心概念

*   **事件驱动空间策略 (Event-Driven Space Strategy):** 实现的主要策略侧重于基于在 M30 时间周期上观察到的重要财经日历事件来创建"交易空间"（博弈空间）。空间的边界由事件后的初始价格脉冲定义，其持续时间由后续价格行为相对于这些边界的活动决定。
*   **模块化 (Modularity):** 该框架分离了关注点：
    *   **策略逻辑:** 在继承自 `StrategyBase` 或 `EventDrivenStrategyBase` 的类中定义 (例如 `EventDrivenSpaceStrategy`)。
    *   **核心框架 (`core/`):** 提供通用基础设施，如数据访问 (`DataProvider`)、策略调度 (`StrategyOrchestrator`)、基类和特定的计算器 (`space_calculator`)。
    *   **执行 (`live/`):** 通过 `ExecutionEngineBase` 的实现（`MT5ExecutionEngine`、`SandboxExecutionEngine`）使用标准化的 `Order` 格式处理与经纪商的交互。
    *   **回测配置 (`backtest/`):** 用于存放特定策略的回测启动脚本或配置（目前为空）。项目级的回测引擎位于根目录的 `backtesting/`。
    *   **配置 (`config/strategies.yaml`):** 定义模块特定的配置，并依赖共享的 `common.yaml`。
    *   **依赖声明 (`requirements.txt`):** 说明模块的第三方库依赖。

## 关键组件描述

*   **`strategies/event_driven_space_strategy.py`**: 包含 `EventDrivenSpaceStrategy` 类。此类监听特定的经济事件，根据初始价格变动定义"空间"，监控空间边界的价格行为，并（旨在）根据空间交互（例如突破、测试）执行交易。它在很大程度上依赖于 `创建博弈空间.md` 中定义的规则。
*   **`strategies/创建博弈空间.md`**: 一个详细说明"事件驱动空间"规则的 Markdown 文档。它涵盖了触发事件、时间周期（M30）、空间边界定义（事件后的初始高/低点）以及空间终止条件（强劲突破、边界震荡、突破-回撤-确认）。
*   **`strategies/core/`**:
    *   `strategy_base.py`: 定义 `StrategyBase` 抽象基类，要求子类实现 `generate_signals`。
    *   `event_driven.py`: 定义 `EventDrivenStrategyBase` 用于基于事件的策略，管理活跃空间并处理新数据点。
    *   `strategy_orchestrator.py`: `StrategyOrchestrator` 根据配置动态加载并运行启用的策略。
    *   `data_providers.py`: 包括 `EconomicCalendarProvider`（获取筛选后的日历事件）、`MarketDataProvider`（读取历史/实时价格 CSV）以及统一的 `DataProvider` 门面类。
    *   `space_calculator.py`: `build_event_space` 函数根据与事件相关的价格行为计算支撑/阻力位。
*   **`strategies/live/`**:
    *   `execution_engine.py`: 定义 `ExecutionEngineBase` 抽象基类，用于标准化的经纪商交互。
    *   `order.py`: 提供 `Order` 数据类以及相关的 `OrderType`、`OrderSide`、`OrderStatus` 枚举，用于一致的订单表示。
    *   `mt5_engine.py`: 实现 `MT5ExecutionEngine`，用于通过 MetaTrader 5 终端进行实盘交易。
    *   `sandbox.py`: 实现 `SandboxExecutionEngine`，用于在没有实时经纪商连接的情况下进行模拟交易，便于测试。
*   **`strategies/backtest/`**:
    *   (目录目前为空) 计划用于存放调用外部回测引擎 (`/backtesting/`) 来测试本模块策略的特定脚本或配置文件。
*   **`strategies/config/strategies.yaml`**: 定义策略编排器、启用的策略、策略参数和沙盒配置。
*   **`strategies/requirements.txt`**: 列出模块直接依赖的第三方库 (如 pandas)。

## 工作原理 (高层概述)

1.  使用**配置加载器**(如 OmegaConf) 加载共享配置 (`config/common.yaml`) 和策略模块配置 (`strategies/config/strategies.yaml`) 并**合并**。
2.  使用合并后的配置、`DataProvider` 和 `ExecutionEngine`（根据配置选择 `MT5ExecutionEngine` 或 `SandboxExecutionEngine`）初始化 `StrategyOrchestrator`。
3.  调度器从 `strategies` 包中动态加载策略类（如 `EventDrivenSpaceStrategy`）。
4.  调度器定期运行（例如，每分钟或基于事件）。
5.  在每个周期中，策略（如 `EventDrivenSpaceStrategy` 通过其 `process_event` 和 `on_bar` 方法，可能由调度器的 `run_cycle` 调用 `process_new_data` 等方法触发）从 `DataProvider` 请求必要的数据（事件、价格）。
6.  `EventDrivenSpaceStrategy` 识别相关的经济事件，并使用 `space_calculator.build_event_space` 定义活跃的"空间"。
7.  它监控新的价格柱 (`on_bar`)，以根据 `创建博弈空间.md` 中的规则检查活跃空间是否应终止。
8.  策略的交易逻辑（`_execute_trading_logic`，目前是占位符）将基于价格与活跃空间的交互生成 `Order` 对象。
9.  这些 `Order` 对象通过 `place_order` 传递给配置的 `ExecutionEngine`（`MT5ExecutionEngine` 或 `SandboxExecutionEngine`）执行。
10. 执行引擎与经纪商交互（或模拟交互）并返回更新后的订单状态。
11. 策略根据已执行的订单更新其内部状态 (`update_positions`)。

## 新增组件

-   **`core/risk_manager.py` (`RiskManagerBase`, `FixedFractionalRiskManager`, `get_risk_manager`)**:
    *   **职责**: 负责计算订单的仓位大小（手数），将风险管理逻辑与策略逻辑分离。
    *   **`RiskManagerBase` (抽象基类)**: 
        *   定义了所有风险管理器的通用接口，主要是 `calculate_position_size` 方法。
        *   初始化时接收 `config`, `execution_engine`, `data_provider` 以便访问账户信息、合约规格和市场价格。
    *   **`FixedFractionalRiskManager` (具体实现)**:
        *   **模型**: 基于固定比例风险模型，即每次交易的风险（以账户货币计）不超过当前账户净值的预设百分比（如 1%）。
        *   **核心方法 (`calculate_position_size`)**: 
            *   **输入**: `signal_data` (字典, 必须包含 `symbol` 和 `stop_loss`)。
            *   **内部逻辑**: 
                1.  调用 `_get_account_equity()` 获取当前账户净值 (余额 + 浮动盈亏)。
                2.  根据配置 (`risk_manager.params.risk_per_trade_percent`) 计算本次交易允许的最大风险金额。
                3.  调用 `_get_risk_amount_per_unit()` 计算每标准手交易的风险金额。
                    *   此方法内部会调用 `_get_contract_specs()` 获取合约规格 (优先 MT5, 回退配置)。
                    *   需要计算止损距离。
                    *   根据止损距离、点大小、点价值计算每手风险。
                4.  用最大允许风险金额除以每手风险金额，得到理论手数。
                5.  根据合约规格中的最小手数 (`volume_min`) 和手数步长 (`volume_step`) 调整理论手数，得到最终可执行的手数。
            *   **输出**: 计算出的手数 (float)，如果无法计算或风险过大/过小则返回 `None`。
        *   **账户净值获取 (`_get_account_equity`)**: (已优化) 尝试从 `execution_engine` 获取余额和所有持仓的浮动盈亏来计算净值。
        *   **合约规格获取 (`_get_contract_specs`)**: (已优化) 调用 `self.data_provider.market_provider.get_symbol_info(symbol)` 获取规格。
    *   **`get_risk_manager` (工厂函数)**:
        *   根据配置 (`config.risk_manager.type`) 创建并返回相应的 `RiskManager` 实例。 