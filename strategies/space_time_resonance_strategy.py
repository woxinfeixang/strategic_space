# coding: utf-8
"""
博弈空间时间共振策略 (Space-Time Resonance Strategy)

策略逻辑:
1. 继承 EventDrivenSpaceStrategy 来利用其定义的博弈空间。
2. 定义 "关键时间" (Key Time):
    - 可以是固定的交易时段 (如伦敦开盘后1小时)。
    - 可以是财经事件发生后的特定时间点 (如事件后2小时、4小时)。
    - 需要在配置中定义关键时间的规则。
3. 监控活跃的博弈空间。
4. 在 "关键时间" 到达时，根据当前价格相对于空间的位置执行不同逻辑 (参考PDF图T3-12):
    - 情况1 (价格在空间内): 等待价格突破空间方向后，顺势交易 (类似反向穿越)。
    - 情况2 (价格在空间外，未反穿): 如果价格回到空间内并出现反向信号，反向博弈。
    - 情况3 (价格在空间外，已反穿): 等待衰竭或进一步反穿确认后再考虑反向交易。
5. 考虑多空间共振: 如果当前存在多个活跃空间，并且它们指示相同方向 (例如，都在上方被突破，或都在下方形成衰竭)，则增强信号。
6. 设置止损和止盈，根据触发的具体情况 (突破、衰竭、博弈) 调整。

止盈止损设置方法 (根据PDF理解，需要细化):
- 止损/止盈根据具体触发的子逻辑（突破、衰竭、博弈反转）来设定，可能需要更灵活的设置。
"""

import pandas as pd
from typing import List, Dict, Any, Optional
import logging
from datetime import time # 用于定义时间段
from datetime import datetime, timedelta # Ensure necessary imports
from strategies.core.data_providers import DataProvider # MODIFIED
from strategies.live.sandbox import SandboxExecutionEngine # 新增导入
from strategies.risk_management.risk_manager import RiskManager # 新增导入
from omegaconf import DictConfig
import pytz # ADDED for timezone handling
from datetime import time as dt_time # ADDED for time object comparison

# 导入基础策略类和数据提供者
from .event_driven_space_strategy import EventDrivenSpaceStrategy
# from .core.data_providers import DataProvider # DataProvider 由父类提供
from .live.order import OrderSide, OrderType
# from .core.order import Order, OrderType, OrderSide
# 可能需要导入其他策略类以复用逻辑
from .reverse_crossover_strategy import ReverseCrossoverStrategy
from .exhaustion_strategy import ExhaustionStrategy
# 导入工具类
from strategies.utils.key_time_detector import KeyTimeDetector
from strategies.utils.signal_aggregator import SignalAggregator

class SpaceTimeResonanceStrategy(EventDrivenSpaceStrategy):
    """
    博弈空间时间共振策略。
    """
    _is_abstract = False # ADDED

    def __init__(self, 
                 strategy_id: str, 
                 app_config: DictConfig, 
                 data_provider: DataProvider,
                 execution_engine: SandboxExecutionEngine,
                 risk_manager: RiskManager,
                 live_mode: bool = False):
        """
        初始化策略。

        Args:
            strategy_id (str): 策略的唯一标识符。
            app_config (DictConfig): 合并后的应用程序配置。
            data_provider (DataProvider): 数据提供者实例。
            execution_engine (SandboxExecutionEngine): 执行引擎实例。
            risk_manager (RiskManager): 风险管理器实例。
            live_mode (bool): 是否为实盘模式。
        """
        super().__init__(strategy_id=strategy_id, 
                         app_config=app_config, 
                         data_provider=data_provider,
                         execution_engine=execution_engine,
                         risk_manager=risk_manager,
                         live_mode=live_mode)
        self.strategy_name = "SpaceTimeResonanceStrategy"
        self.logger = logging.getLogger(self.strategy_name)
        self.logger.info(f"[{self.strategy_name}] 初始化开始...")
        # Log parameters used for base class initialization for traceability
        self.logger.debug(f"[{self.strategy_name}] Base class initialized with: strategy_id='{strategy_id}', app_config_keys={list(app_config.keys()) if app_config else None}, data_provider_type='{type(data_provider).__name__}', execution_engine_type='{type(execution_engine).__name__}', risk_manager_type='{type(risk_manager).__name__}', live_mode={live_mode}")

        # 时空共振特定参数
        self.key_time_enabled = self.params.get('key_time_enabled', self.params.get('enabled', False))

        # 定义关键时间规则 (示例: 事件后 N 小时)
        self.key_time_hours_after_event = self.params.get('key_time_hours_after_event', [2, 4]) # 事件后2小时和4小时为关键时间
        # (可选) 定义固定关键时间段 (例如，伦敦/纽约开盘时段) - 需要时区处理
        self.fixed_key_times = self.params.get('fixed_key_times', []) # e.g., [{'start': '08:00', 'end': '09:00', 'tz': 'Europe/London'}]
        self.logger.debug(f"[{self.strategy_name}] Key time hours after event: {self.key_time_hours_after_event}")
        self.logger.debug(f"[{self.strategy_name}] Fixed key times: {self.fixed_key_times}")
        self.logger.debug(f"[{self.strategy_name}] Key time logic enabled: {self.key_time_enabled}")

        # 实例化子策略检查器 (传递所有必要依赖)
        # 访问其他策略的配置: app_config.strategy_params.OtherStrategyName
        rc_strategy_specific_params = self.config.get('strategy_params', {}).get('ReverseCrossoverStrategy', {})
        rc_strategy_id="ReverseCrossoverStrategy_checker_for_STRS"
        rc_params = self.config.get('strategy_params', {}).get('ReverseCrossoverStrategy', {})
        self._rc_checker = ReverseCrossoverStrategy(
            strategy_id=rc_strategy_id, 
            app_config=self.config, 
            data_provider=self.data_provider,      
            execution_engine=self.execution_engine,  
            risk_manager=self.risk_manager,          
            live_mode=self.live_mode
        )
        self.logger.info(f"[{self.strategy_name}] ReverseCrossoverStrategy checker (_rc_checker) initialized.")
        self.logger.debug(f"[{self.strategy_name}] _rc_checker params: strategy_id='{rc_strategy_id}', app_config_keys relevant to RC: {list(rc_params.keys()) if rc_params else 'None'}, data_provider_type='{type(self.data_provider).__name__}', execution_engine_type='{type(self.execution_engine).__name__}', risk_manager_type='{type(self.risk_manager).__name__}', live_mode={self.live_mode}")

        ex_strategy_specific_params = self.config.get('strategy_params', {}).get('ExhaustionStrategy', {})
        ex_strategy_id="ExhaustionStrategy_checker_for_STRS"
        ex_params = self.config.get('strategy_params', {}).get('ExhaustionStrategy', {})
        self._ex_checker = ExhaustionStrategy(
            strategy_id=ex_strategy_id, 
            app_config=self.config, 
            data_provider=self.data_provider,      
            execution_engine=self.execution_engine,  
            risk_manager=self.risk_manager,          
            live_mode=self.live_mode
        )
        self.logger.info(f"[{self.strategy_name}] ExhaustionStrategy checker (_ex_checker) initialized.")
        self.logger.debug(f"[{self.strategy_name}] _ex_checker params: strategy_id='{ex_strategy_id}', app_config_keys relevant to EX: {list(ex_params.keys()) if ex_params else 'None'}, data_provider_type='{type(self.data_provider).__name__}', execution_engine_type='{type(self.execution_engine).__name__}', risk_manager_type='{type(self.risk_manager).__name__}', live_mode={self.live_mode}")

        # 初始化关键时间检测器
        self.key_time_detector = KeyTimeDetector(self.logger)
        
        # 初始化信号聚合器（如果父类未初始化）
        if not hasattr(super(), 'signal_aggregator') or super().signal_aggregator is None:
            self.signal_aggregator = SignalAggregator(self.logger, self.params.get('signal_aggregator_config', {}))
            self.logger.info(f"[{self.strategy_name}] 初始化信号聚合器")
        else:
            self.signal_aggregator = super().signal_aggregator
            self.logger.info(f"[{self.strategy_name}] 使用父类信号聚合器")
            
        # 是否使用信号聚合器
        self.use_signal_aggregator = self.params.get('use_signal_aggregator', True)
        self.logger.info(f"[{self.strategy_name}] 信号聚合器启用状态: {self.use_signal_aggregator}")

        self.logger.info(f"[{self.strategy_name}] 初始化完成。")

        # 存储关键时间触发状态，避免重复处理 (现在由KeyTimeDetector管理)
        # self._key_time_triggered: Dict[str, Dict[Any, bool]] = {} # Changed Dict key type for trigger_key flexibility
        # Plan Item 4.1: Initialize _pending_s2_checks
        self._pending_s2_checks: Dict[str, Dict[str, Any]] = {} # {symbol: {space_id: {details...}}}
        self.s2_max_wait_bars = self.params.get('s2_max_wait_bars', 5) # Max bars to wait for S2 re-entry

    def get_required_timeframes(self) -> List[str]:
        """此策略需要 M30 (主要) 和 H1 (辅助) 时间框架。"""
        # 确保 primary_timeframe 仍然是第一个，或者明确指定
        primary_tf = super().get_required_timeframes()[0] # 获取基类确定的主时间框架
        required_tfs = {primary_tf, "H1"} # 使用集合去重
        self.logger.info(f"'{self.strategy_id}' requires timeframes: {list(required_tfs)}. Primary is '{primary_tf}'.")
        # 保持主时间框架在列表首位，如果它确实是M30或H1之一；否则按原样添加
        final_list = []
        if primary_tf in required_tfs:
            final_list.append(primary_tf)
            required_tfs.remove(primary_tf)
        final_list.extend(list(required_tfs))
        return final_list

    # Plan Item 3.1: Add get_timeframe_minutes helper method
    def get_timeframe_minutes(self, timeframe: str) -> int:
        """
        Converts a timeframe string (e.g., 'M30', 'H1', 'D1') to minutes.
        """
        # 使用KeyTimeDetector中的方法
        return self.key_time_detector.get_timeframe_minutes(timeframe)

    def _is_key_time(self, current_time: pd.Timestamp, space_info: dict) -> Optional[pd.Timestamp]:
        """
        检查当前时间是否是相对于某个空间的"关键时间"。
        使用KeyTimeDetector统一处理关键时间检测逻辑。

        Args:
            current_time (pd.Timestamp): 当前K线结束时间 (UTC)。
            space_info (dict): 关联的博弈空间信息。

        Returns:
            Optional[pd.Timestamp]: 如果是关键时间，返回该关键时间点 (UTC)；否则返回 None。
        """
        if not self.key_time_enabled:
        return None
        
        # 检查事件相对时间点和固定时间段
        return self.key_time_detector.is_key_time(
            current_time_utc=current_time, 
            space_info=space_info,
            key_time_hours_after_event=self.key_time_hours_after_event,
            fixed_key_times=self.fixed_key_times
        )

    def _execute_trading_logic(self, symbol: str, current_bar: dict, space_info: dict, all_symbol_spaces: list, price_data_full: pd.DataFrame):
        """
        执行博弈空间时间共振策略的交易逻辑。

        Args:
            symbol (str): 交易品种。
            current_bar (dict): 当前 K 线数据。 (包含 'time', 'open', 'high', 'low', 'close')
            space_info (dict): 当前正在处理的活跃空间信息。
            all_symbol_spaces (list): 该品种当前所有的活跃空间列表。
            price_data_full (pd.DataFrame): 该品种对应时间框架的完整历史+实时数据。
        self.logger.debug(f"[{self.strategy_name}-{symbol}] _execute_trading_logic ENTRY for space {space_info.get('id')}. Bar time: {current_bar['time']}. Close: {current_bar['close']}")
"""
        current_time = current_bar['time'] # Assuming current_bar has 'time'
        close_price = current_bar['close']
        
        # Plan Item 4.3: Process pending S2 checks for the current symbol
        s2_checks_for_symbol = self._pending_s2_checks.get(symbol, {})
        completed_s2_space_ids = []

        for space_id_pending, s2_details in list(s2_checks_for_symbol.items()): # Iterate over a copy
            # Find the space_info for this space_id from all_symbol_spaces (or it might be the current space_info)
            # This check is primarily if the space got invalidated by other means since S2 was logged.
            active_pending_space = next((s for s in all_symbol_spaces if s.get('id') == space_id_pending and s.get('status') == 'active'), None)
            if not active_pending_space:
                self.logger.debug(f"[{self.strategy_name}-{symbol}] S2 check: Space ID {space_id_pending} no longer active or found. Removing pending S2 check.")
                completed_s2_space_ids.append(space_id_pending)
                continue

            # Timeout check
            s2_recorded_time = s2_details['recorded_time_s2']
            primary_tf_minutes = self.get_timeframe_minutes(self.primary_timeframe)
            if current_time > s2_recorded_time + pd.Timedelta(minutes=self.s2_max_wait_bars * primary_tf_minutes):
                self.logger.info(f"[{self.strategy_name}-{symbol}] S2 check for space {space_id_pending} (event: {s2_details.get('event_name_s2', 'N/A')}) timed out after {self.s2_max_wait_bars} bars. Clearing.")
                completed_s2_space_ids.append(space_id_pending)
                continue

            s2_upper_bound = s2_details['upper_bound_s2']
            s2_lower_bound = s2_details['lower_bound_s2']
            s2_initial_breakout_direction = s2_details['breakout_direction_s2'] # 1 if price was above space, -1 if price was below
            
            price_re_entered_space = False
            # current_bar['low'] and current_bar['high'] should exist
            if s2_initial_breakout_direction == 1 and current_bar.get('low', float('inf')) < s2_upper_bound: # Was above, now current bar's low is below upper bound
                price_re_entered_space = True
            elif s2_initial_breakout_direction == -1 and current_bar.get('high', float('-inf')) > s2_lower_bound: # Was below, now current bar's high is above lower bound
                price_re_entered_space = True
            
            if price_re_entered_space:
                expected_reverse_signal_direction = -s2_initial_breakout_direction # If was above (1), expect sell (-1). If was below (-1), expect buy (1).
                self.logger.info(f"[{self.strategy_name}-{symbol}] S2 RE-ENTRY: Price for space {space_id_pending} (event: {s2_details.get('event_name_s2', 'N/A')}) re-entered active space bounds after S2 condition (was {s2_initial_breakout_direction}). Orig KeyTime: {s2_details['key_time_point_s2']}. CurrentClose: {close_price:.5f}. Now look for reverse signal (direction: {expected_reverse_signal_direction}).")
                completed_s2_space_ids.append(space_id_pending)
                # The actual signal check (e.g., via _rc_checker or _ex_checker) will happen in the normal flow 
                # for this space_info / current_bar if this space_id_pending is the current space_info.
                # Or, if this space_id_pending is a *different* space, its normal processing will handle it.

        # Clean up completed S2 checks for the current symbol
        if symbol in self._pending_s2_checks:
            for sid in completed_s2_space_ids:
                if sid in self._pending_s2_checks[symbol]:
                    del self._pending_s2_checks[symbol][sid]
            if not self._pending_s2_checks[symbol]: # If dict for symbol becomes empty
                del self._pending_s2_checks[symbol]
        
        # --- Main logic for the current space_info ---
        # Ensure current_bar has all necessary fields (open, high, low, close, time)
        # These should be guaranteed by the base class or data provider. For safety, can use .get()
        # upper_bound = space_info['upper_bound'] # Already available from input args
        # lower_bound = space_info['lower_bound'] # Already available from input args
        # Fallback for upper_bound and lower_bound if not directly in space_info, though they should be
        upper_bound = space_info.get('high', space_info.get('upper_bound'))
        lower_bound = space_info.get('low', space_info.get('lower_bound'))
        
        if upper_bound is None or lower_bound is None:
            self.logger.warning(f"[{self.strategy_name}-{symbol}] Missing upper or lower bound for space {space_info.get('id')}. Skipping trading logic.")
            return

        event_name = space_info.get('event_title', space_info.get('event_name', 'N/A')) # Use event_title if available

        # 检查是否到达关键时间
        key_time_point = self._is_key_time(current_time, space_info)
        if not key_time_point:
            # 非关键时间，此策略不执行操作 (但基类可能仍在检查空间结束)
            self.logger.debug(f"[{self.strategy_name}-{symbol}] _execute_trading_logic: Not a key time for space {space_info.get('id')}. Exiting specific STR logic.")
            return

        self.logger.info(f"[{self.strategy_name}-{symbol}-{current_time}] 到达关键时间 {key_time_point} for event '{event_name}'. SpaceID: {space_info.get('id')}. Upper: {upper_bound:.5f}, Lower: {lower_bound:.5f}. Close: {close_price:.5f}. 开始评估共振条件...")

        # 获取关键时间点的价格位置
        price_at_key_time = close_price # 使用当前收盘价作为关键时间点的价格近似

        # 判断价格相对于空间的位置
        is_inside = lower_bound <= price_at_key_time <= upper_bound
        is_above = price_at_key_time > upper_bound
        is_below = price_at_key_time < lower_bound

        # 判断是否发生过反穿 (基于基类记录的 breakout_info or invalidation_status)
        # Assuming 'invalidation_status' holds more detailed breakout info as per P0 plan
        invalidation_status = space_info.get('invalidation_status', {})
        # Check for confirmed breakout state (e.g. from strong breakout or retrace-confirm that implies a direction)
        # For simplicity, let's use a simplified check if price is merely outside the bounds now vs initial direction.
        # More robust check should use a confirmed breakout state if available from invalidation_status.
        # This 'breakout_info' might be from an older version or a different part of the system.
        # Let's rely on current price relative to bounds and what might be in invalidation_status.
        # For now, a simple check: has the space ever recorded a breakout?
        # A more reliable check would be if EventDrivenSpaceStrategy updates space_info['last_breakout_direction'] or similar.
        # Let's assume 'initial_direction' from space creation is the reference for "反穿"
        initial_pulse_direction = space_info.get('initial_direction') # 'up' or 'down'
        
        has_crossed_up = False
        has_crossed_down = False
        # A simple definition of "反穿" for S2/S3: if price is currently outside in the *opposite* direction of initial pulse.
        if initial_pulse_direction == 'up': # Initial pulse was up, space formed above event
            if is_below: has_crossed_down = True # Price now below the space, considered "反穿" down
        elif initial_pulse_direction == 'down': # Initial pulse was down, space formed below event
            if is_above: has_crossed_up = True # Price now above the space, considered "反穿" up
        # This interpretation of "反穿" might need refinement.
        # A simpler way for S2: price is outside, BUT NOT in the direction of a confirmed strong breakout.
        # Let's use the PDF's simpler view: is price outside, and if so, has it *ever* crossed this boundary before?
        # The 'breakout_info' or a similar field updated by the base class for any boundary cross would be ideal.
        # For now, will use a simple `is_above` / `is_below` and assume `has_crossed_X` can be determined.
        # The S2 logic: "未反穿" means price is outside, but it's the *first time* it's decisively outside in that direction since space formation at key time.
        # The S3 logic: "已反穿" means price is outside, and it has *already established* a break in that direction.

        # Simplified: Let's assume base strategy updates space_info['breakout_info']['direction'] for ANY crossing.
        # This is a placeholder as actual breakout_info structure from base class may vary / may not exist.
        # We'll use a simple flag for now for S2/S3 differentiation.
        # A more robust way for "未反穿": use invalidation_status if it tracks first breakout attempts.
        # For now, let's assume `has_crossed_up` implies a confirmed prior upward break, and `has_crossed_down` a downward one.
        # This part is tricky without knowing exactly how EventDrivenSpaceStrategy flags "反穿".
        # Let's make a working assumption:
        # - If price is above space:
        #   - If space_info.get('ever_broken_high', False) is True -> S3 (已反穿)
        #   - Else -> S2 (未反穿)
        # - If price is below space:
        #   - If space_info.get('ever_broken_low', False) is True -> S3 (已反穿)
        #   - Else -> S2 (未反穿)
        # This requires parent to set these flags. Since that's not guaranteed, let's use a simpler logic for now.
        # S2: price is outside, AND it is NOT in a state where a breakout in that direction has been confirmed by invalidation logic.
        # S3: price is outside, AND a breakout in that direction has been confirmed.
        # This is still too complex. For T3-12, "未反穿" vs "已反穿" seems to relate to the state AT THE KEY TIME.
        # If at Key Time, price is above space:
        #  - S2: This is the first significant move above since space formation.
        #  - S3: Price was already above, or broke above earlier and stayed there.
        # This needs more robust state from the space_info.
        # Given the existing breakout_info structure in _execute_trading_logic:
        # breakout_direction = space_info['breakout_info']['direction']
        # has_crossed_up = breakout_direction == 'UP'
        # has_crossed_down = breakout_direction == 'DOWN'
        # This implies base class sets this on ANY crossing.
        
        # --- 应用 PDF 图T3-12 的逻辑 ---
        position = self.execution_engine.get_position(symbol) # Get current position
        current_space_id = space_info.get('id')

        if position is None or position.get('volume', 0.0) == 0.0: # If no position for this symbol
            # 情况1: 关键时间，价格在空间内部 (S1)
            if is_inside:
                self.logger.info(f"[{self.strategy_name}-{symbol}] S1: 关键时间 ({key_time_point}), 价格在空间内 ({lower_bound:.5f}-{upper_bound:.5f}). 当前价格: {price_at_key_time:.5f}. 等待后续突破 (rc_checker). SpaceID: {current_space_id}")
                # Logic for S1 is typically to wait for a breakout, then use ReverseCrossoverStrategy (_rc_checker)
                # No direct action here, _rc_checker will handle subsequent breakout if it's called for this space.
                # The _rc_checker is typically called by the base class's _process_bar if a breakout occurs later.
                # Or if this strategy itself decides to invoke it based on S1 conditions (currently not implemented here for S1).
                self.logger.debug(f"[{self.strategy_name}-{symbol}] S1: _rc_checker (ReverseCrossoverStrategy) would typically handle breakouts from this state. No direct action by STR for S1 at key time.")
                pass 

            # 情况2: 关键时间，价格在空间外部，未反穿 (S2)
            # "未反穿" means price is outside, but it's not considered a confirmed breakout in that direction yet.
            # Example: price just poked outside.
            # Using a simplified S2 check: if it's outside, but not already in a pending S2 check for this *same* key_time event.
            # And no confirmed breakout in this direction (has_crossed_up/down refers to a more general state)
            # For S2, we're interested if THIS key time event sees price outside for the "first time" in a way.
            elif (is_above and not has_crossed_up) or (is_below and not has_crossed_down): # Simplified: using the has_crossed flags.
                 self.logger.info(f"[{self.strategy_name}-{symbol}] S2: 关键时间 ({key_time_point}), 价格在空间外 (Price: {price_at_key_time:.5f}, Above: {is_above}, Below: {is_below}) 且标记为'未反穿' (CrossedUp: {has_crossed_up}, CrossedDown: {has_crossed_down}). SpaceID: {current_space_id}. Monitoring for re-entry.")
                 # Plan Item 4.2: Record S2 situation
                 if symbol not in self._pending_s2_checks:
                     self._pending_s2_checks[symbol] = {}
                 
                 # Only record if not already pending for this specific space_id from a *previous* bar's S2 trigger.
                 # Or if this is a new S2 event (e.g. new key_time for the same space)
                 # A simple check: if current_space_id is not in pending, or if its key_time_point_s2 is different
                 current_pending_s2 = self._pending_s2_checks.get(symbol, {}).get(current_space_id)
                 if not current_pending_s2 or current_pending_s2.get('key_time_point_s2') != key_time_point :
                     self.logger.info(f"[{self.strategy_name}-{symbol}] S2: Recording pending S2 check for space {current_space_id} at key_time {key_time_point}. Price {price_at_key_time:.5f} is {'above' if is_above else 'below'} space.")
                     self._pending_s2_checks[symbol][current_space_id] = {
                         'recorded_time_s2': current_time, # Bar time when S2 was identified
                         'key_time_point_s2': key_time_point, # The key time point itself
                         'breakout_direction_s2': 1 if is_above else -1, # Direction price is relative to space
                         'upper_bound_s2': upper_bound,
                         'lower_bound_s2': lower_bound,
                         'event_name_s2': event_name
                     }
                     self.logger.info(f"[{self.strategy_name}-{symbol}] S2 condition recorded for space {current_space_id}. Direction: {self._pending_s2_checks[symbol][current_space_id]['breakout_direction_s2']}. Waiting for re-entry.")
                 else:
                      self.logger.debug(f"[{self.strategy_name}-{symbol}] S2 condition for space {current_space_id} (KeyTime: {key_time_point}) already pending or matches existing. No new record.")


            # 情况3: 关键时间，价格在空间外部，已反穿 (S3)
            # "已反穿" means price is outside and it's considered a confirmed breakout in that direction.
            elif (is_above and has_crossed_up) or (is_below and has_crossed_down): # Simplified
                 self.logger.info(f"[{self.strategy_name}-{symbol}] S3: 关键时间 ({key_time_point}), 价格在空间外 (Price: {price_at_key_time:.5f}, Above: {is_above}, Below: {is_below}) 且标记为'已反穿' (CrossedUp: {has_crossed_up}, CrossedDown: {has_crossed_down}). SpaceID: {current_space_id}. 等待衰竭.")
                 # 此时不轻易反向交易，需要等待衰竭信号
                 # 可以调用衰竭策略的检查逻辑
                 try:
                     # 获取近期数据用于衰竭判断
                     lookback_needed = self._ex_checker.exhaustion_lookback
                     # 筛选当前 K 线时间 *之前* 的数据
                     recent_bars_df = price_data_full[price_data_full.index < current_time].tail(lookback_needed)
                     self.logger.debug(f"[{self.strategy_name}-{symbol}] S3: Preparing to call _ex_checker for space {current_space_id}. Lookback: {lookback_needed}, Recent bars available: {len(recent_bars_df) if recent_bars_df is not None else 'None'}")
                     if recent_bars_df is not None and len(recent_bars_df) >= lookback_needed:
                          if is_above:
                              self.logger.debug(f"[{self.strategy_name}-{symbol}] S3: Calling _ex_checker._check_bearish_exhaustion for space {current_space_id}. Price above space.")
                              is_bearish_exhaustion = self._ex_checker._check_bearish_exhaustion(recent_bars_df, upper_bound)
                              self.logger.debug(f"[{self.strategy_name}-{symbol}] S3: _ex_checker._check_bearish_exhaustion for space {current_space_id} returned: {is_bearish_exhaustion}")
                              if is_bearish_exhaustion:
                                  self.logger.info(f"[{self.strategy_name}-{symbol}] S3: Bearish exhaustion detected by _ex_checker. Triggering SELL for space {current_space_id}.")
                              exhaustion_high = recent_bars_df['high'].tail(lookback_needed).max()
                              pip_size = self._get_pip_size(symbol)
                              sl = exhaustion_high + self._ex_checker.stop_loss_pip_buffer * pip_size
                              tp = lower_bound
                              signal_data = {
                                  'symbol': symbol,
                                  'side': OrderSide.SELL,
                                  'order_type': OrderType.MARKET,
                                  'volume': 0,  # 设置为0以触发手数计算
                                  'stop_loss': sl,
                                  'take_profit': tp,
                                  'metadata': {'trigger': 'STR_S3_ExhSell', 'event': event_name[:20], 'current_price_at_signal': current_bar['close']}
                              }
                              self.place_order_from_signal(signal_data)

                          elif is_below:
                              self.logger.debug(f"[{self.strategy_name}-{symbol}] S3: Calling _ex_checker._check_bullish_exhaustion for space {current_space_id}. Price below space.")
                              is_bullish_exhaustion = self._ex_checker._check_bullish_exhaustion(recent_bars_df, lower_bound)
                              self.logger.debug(f"[{self.strategy_name}-{symbol}] S3: _ex_checker._check_bullish_exhaustion for space {current_space_id} returned: {is_bullish_exhaustion}")
                              if is_bullish_exhaustion:
                                  self.logger.info(f"[{self.strategy_name}-{symbol}] S3: Bullish exhaustion detected by _ex_checker. Triggering BUY for space {current_space_id}.")
                              exhaustion_low = recent_bars_df['low'].tail(lookback_needed).min()
                              pip_size = self._get_pip_size(symbol)
                              sl = exhaustion_low - self._ex_checker.stop_loss_pip_buffer * pip_size
                              tp = upper_bound
                              signal_data = {
                                  'symbol': symbol,
                                  'side': OrderSide.BUY,
                                  'order_type': OrderType.MARKET,
                                  'volume': 0,  # 设置为0以触发手数计算
                                  'stop_loss': sl,
                                  'take_profit': tp,
                                  'metadata': {'trigger': 'STR_S3_ExhBuy', 'event': event_name[:20], 'current_price_at_signal': current_bar['close']}
                              }
                              self.place_order_from_signal(signal_data)
                     else:
                          self.logger.debug(f"[{self.strategy_name}-{symbol}] 情况3数据不足 ({len(recent_bars_df) if recent_bars_df is not None else 0} < {lookback_needed})，无法判断衰竭。")
                 except Exception as e:
                     self.logger.error(f"[{self.strategy_name}-{symbol}] 情况3检查衰竭时出错: {e}", exc_info=True)
            else: # Price is outside, but has_crossed status is ambiguous or doesn't fit S2/S3
                self.logger.debug(f"[{self.strategy_name}-{symbol}] KeyTime ({key_time_point}). Price {price_at_key_time:.5f} is_outside (A:{is_above},B:{is_below}), but CrossStatus (U:{has_crossed_up},D:{has_crossed_down}) doesn't match S2/S3. SpaceID: {current_space_id}")


        # --- 考虑多空间共振 (PDF 图T3-50 逻辑) ---
        if len(all_symbol_spaces) > 1:
            self.logger.debug(f"[{self.strategy_name}-{symbol}] 检测到多个活跃空间 ({len(all_symbol_spaces)}个)，检查共振...")
            confluence_direction = None
            confluence_count = 0
            reference_price = close_price # 使用当前收盘价

            for other_space in all_symbol_spaces:
                other_upper = other_space['upper_bound']
                other_lower = other_space['lower_bound']
                other_breakout = other_space['breakout_info']['direction']

                # 简单共振逻辑：检查价格是否同时突破多个空间的同向边界
                if reference_price > other_upper:
                    if confluence_direction is None: confluence_direction = 'UP'
                    if confluence_direction == 'UP': confluence_count += 1
                elif reference_price < other_lower:
                    if confluence_direction is None: confluence_direction = 'DOWN'
                    if confluence_direction == 'DOWN': confluence_count += 1
                else: # 价格在某个空间内部，不算强共振信号 (可调整)
                    pass

            if confluence_count >= 2: # 至少两个空间指示同一方向
                 self.logger.info(f"[{self.strategy_name}-{symbol}] 检测到 {confluence_direction} 方向的多空间共振 ({confluence_count}个空间)。")
                 # TODO: 在这里可以增强信号或触发交易
                 # 例如，如果当前关键时间逻辑也支持同向，则可以下单
                 # 需要结合上面的 S1/S2/S3 逻辑来决定是否交易
                 pass


    # 继承 _place_order 和 _calculate_order_size
    def _place_order(self, symbol: str, side: OrderSide, current_bar: dict, stop_loss: float, take_profit: float, comment: str):
        """
        辅助函数：构建信号数据并调用 StrategyBase 的 place_order_from_signal。
        """
        self.logger.info(f"[{self.strategy_name}-{symbol}-{current_bar['time']}] 准备下单: {side.value} @ MKT (SL={stop_loss:.5f}, TP={take_profit:.5f}), Comment: {comment}")
        
        signal_data = {
            'symbol': symbol,
            'side': side,
            'order_type': OrderType.MARKET,
            'volume': 0, # 设置为0，让 StrategyBase.place_order_from_signal 通过 RiskManager 计算手数
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'metadata': {
                'comment': comment,
                'strategy_name': self.strategy_name,
                'current_price_at_signal': current_bar['close']
            }
        }
        self.place_order_from_signal(signal_data)

    def _calculate_order_size(self, symbol: str, stop_loss_price: float) -> float:
        # 此方法已被 StrategyBase 中的逻辑取代或废弃，手数计算在 place_order_from_signal 中进行
        self.logger.warning(f"[{self.strategy_name}] _calculate_order_size 被调用，但手数计算已移至 place_order_from_signal。返回0。")
        return 0.0

    def process_new_data(self, current_time: datetime, market_data: Dict[str, Dict[str, pd.DataFrame]], latest_events: Optional[pd.DataFrame]):
        """
        处理新的市场数据和事件。
        """
        # self.logger.debug(f"{self.strategy_name}: Processing new data...") # Reduced verbosity, parent class logs this
        super().process_new_data(current_time, market_data, latest_events)
        self.logger.debug(f"{self.strategy_name}: Finished specific processing in process_new_data for {current_time}.")


    # Plan Item 2.1: REMOVE the overridden _map_event_to_symbol method to inherit from base.
    # def _map_event_to_symbol(self, event: Dict[str, Any]) -> Optional[str]:
    #     """
    #     将经济日历事件映射到交易品种
        
    #     Args:
    #         event (Dict[str, Any]): 经济事件数据
            
    #     Returns:
    #         Optional[str]: 对应的交易品种，如果无法映射则返回None
    #     """
    #     # 简单映射逻辑
    #     currency = event.get('Currency')
    #     if not currency:
    #         self.logger.debug(f"[{self.strategy_name}] _is_key_time: No key time identified for space {space_info.get('id')} at current_time {current_time}. Returning None.")
    #     return None
            
    #     # 基本货币映射
    #     if currency == 'USD':
    #         return 'EURUSD'  # 默认映射到EURUSD
    #     elif currency == 'EUR':
    #         return 'EURUSD'
    #     elif currency == 'GBP':
    #         return 'GBPUSD'
    #     elif currency == 'JPY':
    #         return 'USDJPY'
    #     elif currency == 'AUD':
    #         return 'AUDUSD'
    #     elif currency == 'CAD':
    #         return 'USDCAD'
    #     elif currency == 'NZD':
    #         return 'NZDUSD'
    #     elif currency == 'CHF':
    #         return 'USDCHF'
        
    #     # 如果找不到直接对应的品种，返回None
    #     return None

    def _submit_signal(self, symbol: str, action: str, timestamp: datetime, 
                      confidence: float = 1.0, metadata: Dict[str, Any] = None) -> None:
        """
        提交信号到聚合器
        
        Args:
            symbol: 交易品种
            action: 交易动作，"BUY"或"SELL"
            timestamp: 信号时间戳
            confidence: 信号置信度，0.0-1.0
            metadata: 附加信息字典
        """
        # 检查是否启用信号聚合器
        if not self.use_signal_aggregator:
            self.logger.debug(f"[{self.strategy_name}] 信号聚合器已禁用，不提交信号")
            return
            
        # 检查信号聚合器是否已初始化
        if not hasattr(self, 'signal_aggregator') or self.signal_aggregator is None:
            self.logger.warning(f"[{self.strategy_name}] 无法提交信号，信号聚合器未初始化")
            return
                
        # 提交信号
        try:
            self.signal_aggregator.submit_signal(
                strategy_name=self.strategy_name,
                symbol=symbol,
                action=action,
                timestamp=timestamp,
                confidence=confidence,
                metadata=metadata
            )
            self.logger.debug(f"[{self.strategy_name}] 信号已提交到聚合器: {symbol} {action}, 置信度={confidence:.2f}")
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 提交信号到聚合器时发生错误: {e}", exc_info=True)

# --- 可选的测试入口 ---
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.info("运行 SpaceTimeResonanceStrategy 测试代码...")

    # 1. 模拟配置
    mock_config = {
        'strategy_name': 'TestResonance',
        'strategy_params': {
            'event_importance_threshold': 2,
            'space_definition': {'forward_bars': 4, 'boundary_percentile': 90},
            'end_conditions': {'max_duration_hours': 48}, # 延长测试时间
            'resonance_params': {
                'key_time_hours_after_event': [2, 4] # 事件后2, 4小时为关键时间
            },
            # 继承其他策略参数用于 checker
            'exhaustion_lookback': 3,
            'stop_loss_pip_buffer': 5,
            'take_profit_target': 'opposite_boundary'
        },
    }

    # 2. 模拟数据提供者 (需要能覆盖关键时间点)
    class MockDataProviderResonance(DataProvider):
        def get_historical_prices(self, symbol, start_time, end_time, timeframe):
            logger.debug(f"MockDataProviderResonance: 获取 {symbol} 从 {start_time} 到 {end_time} ({timeframe})")
            # 确保生成足够长的时间序列
            sim_start = pd.Timestamp('2023-01-01 08:00:00', tz='UTC')
            sim_end = pd.Timestamp('2023-01-01 18:00:00', tz='UTC')
            dates = pd.date_range(start=sim_start, end=sim_end, freq='30min', tz='UTC')
            data = {
                'open': [1.1000 + i*0.0001 for i in range(len(dates))],
                'high': [1.1005 + i*0.00015 for i in range(len(dates))],
                'low': [1.0995 - i*0.00005 for i in range(len(dates))],
                'close': [1.1002 + i*0.00012 for i in range(len(dates))],
                'volume': [100 + i*10 for i in range(len(dates))]
            }
            df = pd.DataFrame(data, index=dates)

            # 模拟关键时间点 (事件后2小时 = 12:00) 价格在空间内
            # (假设空间是 1.1000 - 1.1010)
            key_time_1 = pd.Timestamp('2023-01-01 12:00:00', tz='UTC')
            if key_time_1 in df.index:
                 df.loc[key_time_1, 'close'] = 1.1005 # 在内部

            # 模拟关键时间点 (事件后4小时 = 14:00) 价格在空间外且已反穿，并形成衰竭
            key_time_2 = pd.Timestamp('2023-01-01 14:00:00', tz='UTC')
            if key_time_2 in df.index:
                 # 让价格先突破
                 df.loc[pd.Timestamp('2023-01-01 13:30:00', tz='UTC'), 'close'] = 1.1015
                 df.loc[pd.Timestamp('2023-01-01 13:30:00', tz='UTC'), 'high'] = 1.1018
                 # 在关键时间形成衰竭 (Pin Bar)
                 df.loc[key_time_2, 'open'] = 1.1016
                 df.loc[key_time_2, 'high'] = 1.1025 # 长上影
                 df.loc[key_time_2, 'low'] = 1.1014
                 df.loc[key_time_2, 'close'] = 1.1015 # 收盘较低

            return df.loc[start_time:end_time]

        def get_calendar_events(self, start_time, end_time):
             return pd.DataFrame([
                  {'timestamp': pd.Timestamp('2023-01-01 10:00:00', tz='UTC'), 'name': 'Mock Event', 'currency': 'EUR', 'importance': 3, 'actual': '1.0'}
             ])

    # 3. 模拟执行引擎
    class MockExecutionEngine:
        def place_order(self, order):
            logger.info(f"MockExecutionEngine: 收到订单: {order}")
            return {'status': 'FILLED', 'order_id': 'mock_789'}
        def get_position(self, symbol):
            logger.debug(f"MockExecutionEngine: 获取持仓信息: {symbol}")
        return None

    # 4. 初始化和运行
    mock_provider = MockDataProviderResonance({})
    mock_engine = MockExecutionEngine()
    mock_rm = RiskManager({})
    strategy = SpaceTimeResonanceStrategy(
        strategy_id="STRS_Test",
        app_config=mock_config,
        data_provider=mock_provider,
        execution_engine=mock_engine,
        risk_manager=mock_rm,
        live_mode=False
    )

    # 模拟事件触发
    event_time = pd.Timestamp('2023-01-01 10:00:00', tz='UTC')
    mock_event = {'timestamp': event_time, 'name': 'Mock Event', 'currency': 'EUR', 'importance': 3, 'actual': '1.0'}
    strategy.process_event(mock_event)

    # 模拟 K 线流
    start_run_time = event_time + pd.Timedelta(minutes=30 * mock_config['strategy_params']['space_definition']['forward_bars'])
    end_run_time = start_run_time + pd.Timedelta(hours=6) # 模拟运行几小时以覆盖关键时间
    current_time = start_run_time

    while current_time <= end_run_time:
        bar_df = mock_provider.get_historical_prices('EURUSD', current_time - pd.Timedelta(minutes=1), current_time, 'M30')
        if not bar_df.empty:
            current_bar_dict = bar_df.iloc[-1].to_dict()
            current_bar_dict['time'] = bar_df.index[-1]
            mock_bar_data = {'EURUSD': current_bar_dict}
            logger.info(f"\n--- Processing Bar Time: {current_bar_dict['time']} ---")
            if 'EURUSD' in strategy.active_spaces:
                 logger.debug(f"Active Space EURUSD: {strategy.active_spaces['EURUSD'][0]['lower_bound']:.5f} - {strategy.active_spaces['EURUSD'][0]['upper_bound']:.5f}")
            strategy.on_bar(mock_bar_data)
        else:
             logger.warning(f"无法获取 {current_time} 的模拟 K 线")
        current_time += pd.Timedelta(minutes=30)

    logger.info("测试完成。")
