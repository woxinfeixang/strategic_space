# 反向穿越策略 (Reverse Crossover Strategy) 说明文档

**重要: 时区处理**

*   本策略接收的市场价格 K 线数据 (来自 `MarketDataProvider`)，其时间索引为 **UTC 时间**。
*   本策略接收的财经日历事件数据 (来自 `EconomicCalendarProvider`)，其时间列为 **北京时间 (`Asia/Shanghai`)**。
*   在策略的 `process_new_data` 方法内部，会**自动将接收到的事件时间转换为 UTC**，以便后续所有的时间比较、反向穿越判断和逻辑判断都在 **统一的 UTC 时间基准**下进行。

## 1. 策略依据

本策略基于《外汇交易面授总结》PDF中关于"价格反向穿越博弈空间边界"的论述（如图T3-19, T3-20）。核心逻辑是：

*   **市场异常行为**: 当价格从博弈空间外部反向穿越边界时，表明市场参与者对原有空间共识被打破
*   **机构行为特征**: 这类穿越往往伴随大单成交量和特定订单流模式
*   **统计优势**: 历史回测显示这类信号在M30周期具有显著统计优势

## 2. 实现逻辑

### 2.1 核心组件

```python
class ReverseCrossoverStrategy(EventDrivenSpaceStrategy):
    def __init__(self, config):
        super().__init__(config)
        self._setup_indicators()
        
    def _setup_indicators(self):
        self._volume_ma = VolumeMA(period=5)  # 成交量均线
        self._atr = ATR(period=14)  # 波动率指标
        self._angle_calculator = BreakoutAngle()  # 突破角度计算
```

### 2.2 信号检测流程

1.  **空间边界监控**:
    *   实时跟踪价格与空间边界的关系
    *   标记价格是从空间内部还是外部接近边界

2.  **反向穿越确认**:
    *   必须满足:
        *   前一根K线收盘在空间外
        *   当前价格从外向内穿越边界
        *   穿越幅度>5个点 (参数化: `crossover_min_pips`)
    *   计算突破角度(基于3根K线斜率)

3.  **成交量验证**:
    *   突破时成交量需>5分钟均量的120% (参数化: `volume_boost`)
    *   大单比例>15%

### 2.2.1 入场模式 (Entry Modes)

本策略支持两种入场模式，通过参数 `entry_on_retrace` (布尔型) 控制：

*   **即时入场 (`entry_on_retrace = False`)**: 当检测到有效的反向穿越信号并满足所有确认条件时，策略立即尝试按市价入场。
*   **回调入场 (`entry_on_retrace = True`)**: 当检测到有效的反向穿越信号后，策略不会立即入场，而是进入"等待回调"状态。
    *   **等待回调**: 策略会等待价格在突破后回调至原突破边界附近 (可配置一个小的缓冲区域，参数: `retrace_entry_buffer_pips`)。
    *   **回调入场**: 如果价格在指定的最大等待K线数内 (`retrace_max_wait_bars`) 成功回调到目标区域，策略将尝试入场。
    *   **回调超时**: 如果在最大等待K线数内价格未能回调，则该次入场机会作废。
    *   此模式旨在过滤掉突破后未经历任何回调直接延续的行情，寻求在回调点获得更好的入场价格。

### 2.3 交易执行

```python
# 示例性伪代码，实际逻辑在 _execute_trading_logic 方法中实现
# def _execute_trading_logic(self, symbol, current_bar, space_info, active_spaces_for_symbol):
#     # ... 获取当前持仓 ...
#     # ... 检查并处理回调等待状态 (如果 entry_on_retrace is True and space_info has 'rc_status') ...
#     #     - 检查回调超时
#     #     - 检查回调条件是否满足
#     #     - 如果满足回调入场，计算止损止盈并下单
# 
#     # ... 如果没有活跃的回调等待，则检查新的突破信号 ...
#     # if self._detect_reverse_crossover(current_bar, space_info): # 假设此方法检查了所有条件
#     #     if not self.entry_on_retrace:
#     #         # 即时入场逻辑
#     #         price = self._get_current_price(current_bar)
#     #         if self._is_upper_boundary_crossover(current_bar, space_info): # 假设
#     #             self._enter_short(price, space_info) # 传递 space_info 用于 SL/TP
#     #         else:
#     #             self._enter_long(price, space_info)
#     #     else:
#     #         # 设置等待回调状态 (rc_status, rc_target_retrace_level, rc_breakout_bar_time etc. in space_info)
#     #         self.logger.info(f"[{symbol}] Detected reverse crossover, waiting for retrace.")
```
实际的交易决策在 `_execute_trading_logic` 方法中进行。该方法会根据 `entry_on_retrace` 参数的值以及当前是否存在等待回调的状态，来决定是即时入场还是等待回调后入场。

### 2.4 止损止盈设置

*   **动态止损**:
    *   基础止损: 2×ATR
    *   角度调整: 突破角度每增加10度，止损缩小0.2×ATR
    *   最小止损: 1×ATR

*   **多层止盈**:
    1.  第一目标: 1×ATR (平仓50%)
    2.  第二目标: 空间对侧边界
    3.  最终目标: 2.5×ATR

## 3. 参数优化建议

| 参数名 | 默认值 | 优化范围 | 影响 |
|--------|--------|----------|------|
| entry_on_retrace | False | True/False | 控制是即时入场还是回调入场 |
| retrace_entry_buffer_pips | 1.0 | 0-5 | 回调入场时，允许价格突破边界的缓冲点数 |
| retrace_max_wait_bars | 5 | 3-10 | 回调入场时，等待回调的最大K线数量 |
| retrace_sl_use_entry_bar_extremum | True | True/False | 回调入场时，止损是否基于入场K线的极值点 |
| retrace_sl_extremum_buffer_pips | 2.0 | 0-5 | 回调入场且使用极值止损时，从极值点外扩的缓冲点数 |
| crossover_min_pips | 5 | 3-8 | 影响信号质量 |
| volume_boost | 1.2 | 1.1-1.5 | 过滤假突破 |
| angle_threshold | 30 | 25-40 | 决定突破强度 |
| atr_multiplier | 2.0 | 1.5-3.0 | 风险控制 |

## 4. 与其他策略的协同

1.  **与时间共振策略结合**:
    *   当反向穿越发生在关键时间窗口内时，仓位可增加30%
    *   需确认时间共振信号强度>0.7

2.  **与权重拐点策略对比**:
    *   反向穿越: 强调价格从外向内突破
    *   权重拐点: 关注边界附近的资金流向变化

## 5. 特殊场景处理

*   **连续事件冲击**:
    *   在连续重要事件公布期间，暂停策略运行
    *   通过`economic_calendar`模块检测事件密度
    
*   **流动性不足**:
    *   当买卖价差>3点时，不执行新交易
    *   通过`market_depth`分析实时流动性

反向穿越策略通过捕捉机构资金推动的非常规价格行为获取收益，其核心优势在于严格的空间边界定义和多重信号验证机制。
