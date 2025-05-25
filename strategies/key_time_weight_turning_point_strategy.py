# coding: utf-8
"""
关键时间之内权重拐点策略 (Key Time Weight Turning Point Strategy)

核心逻辑:
1. 继承 EventDrivenSpaceStrategy 来利用其定义的、由财经事件触发的动态博弈空间。
2. 在博弈空间形成后的特定"关键时间"点 (例如，事件发生后的 H1, H3, H5 收盘)，关注市场行为。
3. 在这些关键时间点，如果价格触及或接近博弈空间的边界 (被视为"权重拐点")，则产生交易信号。
4. (可选) 可以结合更小时间框架 (如 M5/M15) 的确认形态 (例如pin bar, 吞没) 来提高信号质量。
5. (可选) 引入穷尽信号判断，如果出现衰竭迹象，即使未到关键时间也可考虑入场或调整。

关键时间选择的考量:
- 事件发生后的第一个 H1 收盘价: 市场对事件的初步反应和流动性注入后的稳定点。
- 事件发生后的 H3/H5 收姿势: 市场可能已经完成初步消化，趋势或区间可能形成。

权重拐点:
- 主要依赖 EventDrivenSpaceStrategy 计算出的博弈空间上下边界。
- 未来可以扩展到重要的 Node 点或自然回调点 (Natural Retracement)。

风险管理:
- 止损: 基于边界之外一定距离，或形态的高/低点。
- 止盈: 博弈空间另一侧，或固定盈亏比。

"""

import pandas as pd
import numpy as np
import talib
from typing import List, Dict, Any, Optional
import logging
from datetime import time, datetime, timedelta # time 未使用，可以移除
from omegaconf import DictConfig
import pytz
import re # 添加缺失的导入

# 导入基础策略类和数据提供者
from .event_driven_space_strategy import EventDrivenSpaceStrategy
from strategies.core.data_providers import DataProvider # 确保这个路径是正确的，并且能被加载
from strategies.live.sandbox import SandboxExecutionEngine # 新增导入
from strategies.risk_management.risk_manager import RiskManager # 新增导入
from .live.order import OrderSide, OrderType # <--- 修改为正确的相对导入

# 导入工具类
from strategies.utils.key_time_detector import KeyTimeDetector
from strategies.utils.signal_aggregator import SignalAggregator

# 可能需要导入其他策略类以复用逻辑
from .exhaustion_strategy import ExhaustionStrategy # Modified line: Uncommented

class KeyTimeWeightTurningPointStrategy(EventDrivenSpaceStrategy):
    """
    关键时间之内权重拐点策略。
    """
    _is_abstract = False

    def __init__(self, 
                 strategy_id: str, 
                 app_config: DictConfig, 
                 data_provider: DataProvider,
                 execution_engine: SandboxExecutionEngine,
                 risk_manager: RiskManager,
                 live_mode: bool = False):
        super().__init__(strategy_id=strategy_id, 
                         app_config=app_config, 
                         data_provider=data_provider,
                         execution_engine=execution_engine,
                         risk_manager=risk_manager,
                         live_mode=live_mode)
        self.strategy_name = "KeyTimeWeightTurningPointStrategy"
        self.logger = logging.getLogger(self.strategy_name)
        # self.logger.info(f"{self.strategy_name} 初始化完成。") # Restored to commented state

        # 添加策略时区属性
        # self.strategy_timezone = pytz.UTC # Restored to commented state
        
        # 策略特定参数
        ktwtp_params = self.params.get('ktwtp_params', {})
        # 关键时间定义 (复用共振策略的定义或独立定义)
        self.key_time_hours_after_event = ktwtp_params.get('key_time_hours_after_event', [1, 3, 5]) # 示例：事件后1, 3, 5小时
        # 权重拐点定义 (目前仅使用空间边界)
        self.use_space_boundaries_as_turning_points = ktwtp_params.get('use_space_boundaries_as_turning_points', True)
        # TODO: 添加识别和使用 Node / Natural Retracement 的逻辑 # This TODO is being addressed
        self.profit_loss_ratio = ktwtp_params.get('risk_reward_ratio', 1.5) # 在 _execute_trading_logic 中使用

        # New parameters for Node and Natural Retracement turning points
        self.use_natural_retracement_tp = ktwtp_params.get('use_natural_retracement_tp', False)
        self.natural_retracement_levels = ktwtp_params.get('natural_retracement_levels', [0.382, 0.5, 0.618])
        self.use_node_tp = ktwtp_params.get('use_node_tp', False)
        self.node_proximity_buffer_pips = ktwtp_params.get('node_proximity_buffer_pips', 5)

        # VWAP Take Profit parameters (Plan Item 2)
        # take_profit_target is already fetched in _execute_trading_logic, ensure it can handle 'vwap'
        self.vwap_tp_atr_period = ktwtp_params.get('vwap_tp_atr_period', 14)
        self.vwap_tp_atr_multiplier = ktwtp_params.get('vwap_tp_atr_multiplier', 1.0)
        self.vwap_tp_period = ktwtp_params.get('vwap_tp_period', 14)

        # M5/M15 确认参数 (可选)
        self.confirm_with_m5_m15 = ktwtp_params.get('confirm_with_m5_m15', False)
        self.m5_m15_lookback = ktwtp_params.get('m5_m15_lookback', 6) # 回看多少根 M5/M15 K线

        # 为穷尽检查器创建一个实例 (传递所有必要依赖)
        # 需要确保穷尽策略的配置也包含在主 config 中，或提供默认值
        # exhaustion_config = self.config.get('exhaustion_checker_params', config) # 尝试获取特定参数，否则复用主配置
        # self._ex_checker = ExhaustionStrategy(exhaustion_config, data_provider, execution_engine, risk_manager) # 已注释
        exhaustion_params = self.params.get('exhaustion_checker_params', {}) 
        self._ex_checker = ExhaustionStrategy(
            strategy_id=f"{self.strategy_id}_ex_checker", 
            app_config=self.app_config, 
            data_provider=self.data_provider,
            execution_engine=self.execution_engine,
            risk_manager=self.risk_manager,
            live_mode=self.live_mode
            # params=exhaustion_params # Assuming ExhaustionStrategy handles its own params from app_config or has a params kwarg
        )

        # 初始化关键时间检测器
        self.key_time_detector = KeyTimeDetector(self.logger)
        
        # 初始化信号聚合器（如果父类未初始化）
        if not hasattr(super(), 'signal_aggregator') or super().signal_aggregator is None:
            self.signal_aggregator = SignalAggregator(self.logger, self.params.get('signal_aggregator_config', {}))
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 初始化信号聚合器")
        else:
            self.signal_aggregator = super().signal_aggregator
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 使用父类信号聚合器")
            
        # 信号聚合器控制参数
        self.use_signal_aggregator = self.params.get('use_signal_aggregator', True)
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 信号聚合器启用状态: {self.use_signal_aggregator}")
        
        # 存储关键时间触发状态 (现在由 KeyTimeDetector 管理)
        # self.triggered_times: Dict[str, datetime] = {}

    def _is_key_time(self, current_time: pd.Timestamp, space_info: dict) -> Optional[pd.Timestamp]:
        """
        判断当前时间是否是博弈空间形成后的"关键时间"之一。
        使用 KeyTimeDetector 统一处理关键时间检测逻辑。

        Args:
            current_time (pd.Timestamp): 当前 K 线的时间 (UTC)。
            space_info (dict): 当前活跃空间的信息，包含 'creation_time' 和 'event_data'。

        Returns:
            Optional[pd.Timestamp]: 如果是关键时间，返回该关键时间点 (UTC)；否则返回 None。
        """
                # 如果参数中的space_info包含event_time_utc，转换成KeyTimeDetector期望的格式
        if 'event_time_utc' in space_info and 'creation_time' not in space_info:
            # 确保creation_time存在且格式正确
        event_time_utc = space_info['event_time_utc']
        if not isinstance(event_time_utc, pd.Timestamp):
            try:
                event_time_utc = pd.Timestamp(event_time_utc, tz='UTC')
            except Exception as e:
                self.logger.error(f"[{self.strategy_name}] 无法解析 space_info 中的 event_time_utc '{event_time_utc}': {e}")
                return None
        
            # 创建新的space_info副本，添加KeyTimeDetector需要的字段
            space_info_for_detector = space_info.copy()
            space_info_for_detector['creation_time'] = event_time_utc
            if 'event_data' not in space_info_for_detector:
                space_info_for_detector['event_data'] = {
                    'symbol': space_info.get('symbol', 'unknown')
                }
                
            # 调用KeyTimeDetector的方法检测关键时间
            return self.key_time_detector.is_key_time(
                current_time_utc=current_time, 
                space_info=space_info_for_detector,
                key_time_hours_after_event=self.key_time_hours_after_event
            )
                else:
            # 直接使用KeyTimeDetector方法
            return self.key_time_detector.is_key_time(
                current_time_utc=current_time, 
                space_info=space_info,
                key_time_hours_after_event=self.key_time_hours_after_event
            )

    def _is_at_turning_point(self, symbol: str, current_bar: pd.Series, space_info: dict, all_symbol_spaces: list) -> Optional[str]:
        """
        判断价格是否在当前活跃空间的关键边界附近 (权重拐点)。
        """
        current_high = current_bar['high']
        current_low = current_bar['low']

        upper_bound = space_info['upper_bound']
        lower_bound = space_info['lower_bound']

        if self.use_space_boundaries_as_turning_points:
            # pip_size = 0.0001 if 'JPY' not in symbol else 0.01
            pip_size = self._get_pip_size(symbol)
            buffer_pips = self.params.get('ktwtp_params', {}).get('turning_point_buffer_pips', 10) 
            pips_buffer_value = buffer_pips * pip_size

            # 检查是否触及普通空间边界
            # (Original condition adjusted slightly for clarity based on tool output preview)
            if current_high >= upper_bound - pips_buffer_value and current_low <= upper_bound + pips_buffer_value:
                 self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及上边界拐点 (缓冲 {buffer_pips} pips): {upper_bound:.5f} ---")
                 return 'UPPER_BOUND'
            if current_low <= lower_bound + pips_buffer_value and current_high >= lower_bound - pips_buffer_value:
                 self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及下边界拐点 (缓冲 {buffer_pips} pips): {lower_bound:.5f} ---")
                 return 'LOWER_BOUND'
        
        # 实现 Natural Retracement 逻辑
        if self.use_natural_retracement_tp:
            pip_size_nr = self._get_pip_size(symbol) # Ensure pip_size is available if not defined above
            buffer_pips_nr = self.params.get('ktwtp_params', {}).get('turning_point_buffer_pips', 10)
            pips_buffer_value_nr = buffer_pips_nr * pip_size_nr
            space_height = upper_bound - lower_bound
            if space_height > 0: 
                for level in self.natural_retracement_levels:
                    support_level = lower_bound + (space_height * level)
                    if abs(current_low - support_level) <= pips_buffer_value_nr or \
                       (current_low < support_level and current_high > support_level):
                        self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及自然回调支撑位 {level*100:.1f}%: {support_level:.5f} (基于空间低点) ---")
                        return f'NATURAL_RETRACEMENT_SUPPORT_{int(level*100)}'

                    resistance_level = upper_bound - (space_height * level)
                    if abs(current_high - resistance_level) <= pips_buffer_value_nr or \
                       (current_low < resistance_level and current_high > resistance_level):
                        self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及自然回调阻力位 {level*100:.1f}%: {resistance_level:.5f} (基于空间高点) ---")
                        return f'NATURAL_RETRACEMENT_RESISTANCE_{int(level*100)}'

        # 实现 Node 拐点逻辑 (初步)
        if self.use_node_tp:
            pip_size_node = self._get_pip_size(symbol) # Ensure pip_size is available
            node_buffer_val = self.node_proximity_buffer_pips * pip_size_node
            if 'nodes' in space_info and space_info['nodes']:
                for node in space_info['nodes']:
                    node_level = node.get('level')
                    node_type = node.get('type', 'unknown').upper()
                    if node_level is not None:
                        if node_type == 'SUPPORT' and (abs(current_low - node_level) <= node_buffer_val or (current_low < node_level and current_high > node_level)):
                            self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及预定义 Node 支撑位: {node_level:.5f} ---")
                            return 'NODE_SUPPORT'
                        elif node_type == 'RESISTANCE' and (abs(current_high - node_level) <= node_buffer_val or (current_low < node_level and current_high > node_level)):
                            self.logger.info(f"[{self.strategy_name}-{symbol}] --- 价格触及预定义 Node 阻力位: {node_level:.5f} ---")
                            return 'NODE_RESISTANCE'
            else:
                self.logger.debug(f"[{self.strategy_name}-{symbol}] Node turning point check enabled, but no node data found in space_info.")

        return None

    def _confirm_with_m5_m15(self, symbol: str, current_m30_bar_time: pd.Timestamp, signal_type: str) -> bool:
        """
        (可选) 使用 M5/M15 K线形态确认 M30 级别在边界产生的信号。
        """
        log_prefix = f"[{self.strategy_name}-{symbol}]"
        self.logger.debug(f"{log_prefix} _confirm_with_m5_m15 called. M30 bar time: {current_m30_bar_time}, Signal: {signal_type}")

        if not self.confirm_with_m5_m15:
            self.logger.debug(f"{log_prefix} M5/M15 confirmation not enabled. Returning True.")
            return True 

        m5_end_time = current_m30_bar_time
        m5_start_time = current_m30_bar_time - timedelta(minutes=5 * (self.m5_m15_lookback -1))

        try:
            m5_bars_df = self.data_provider.get_historical_prices(symbol, m5_start_time, m5_end_time, 'M5')
            if m5_bars_df is None or len(m5_bars_df) < 2: 
                self.logger.debug(f"{log_prefix} M5数据不足 (found {len(m5_bars_df) if m5_bars_df is not None else 0} bars, need >=2)，无法进行小周期确认。Start: {m5_start_time}, End: {m5_end_time}")
                return False
            
            self.logger.debug(f"{log_prefix} Fetched {len(m5_bars_df)} M5 bars for confirmation.")
            last_m5_bar = m5_bars_df.iloc[-1]
            prev_m5_bar = m5_bars_df.iloc[-2]
            self.logger.debug(f"{log_prefix} Last M5 bar: O={last_m5_bar['open']:.5f} H={last_m5_bar['high']:.5f} L={last_m5_bar['low']:.5f} C={last_m5_bar['close']:.5f} @ {last_m5_bar.name}")
            self.logger.debug(f"{log_prefix} Prev M5 bar: O={prev_m5_bar['open']:.5f} H={prev_m5_bar['high']:.5f} L={prev_m5_bar['low']:.5f} C={prev_m5_bar['close']:.5f} @ {prev_m5_bar.name}")

            if signal_type == 'SELL': 
                # Bearish Engulfing
                if last_m5_bar['close'] < last_m5_bar['open'] and \
                   prev_m5_bar['close'] > prev_m5_bar['open'] and \
                   last_m5_bar['open'] >= prev_m5_bar['close'] and \
                   last_m5_bar['close'] < prev_m5_bar['open']:
                    self.logger.info(f"{log_prefix} M5 确认: 看跌吞没 @ {last_m5_bar.name}")
                    return True
                # Pin Bar (Shooting Star)
                body_size = abs(last_m5_bar['close'] - last_m5_bar['open'])
                upper_wick = last_m5_bar['high'] - max(last_m5_bar['open'], last_m5_bar['close'])
                if upper_wick > body_size * 1.5 and body_size < (last_m5_bar['high'] - last_m5_bar['low']) * 0.4:
                    self.logger.info(f"{log_prefix} M5 确认: 顶部Pin Bar @ {last_m5_bar.name}")
                    return True

            elif signal_type == 'BUY': 
                # Bullish Engulfing
                if last_m5_bar['close'] > last_m5_bar['open'] and \
                   prev_m5_bar['close'] < prev_m5_bar['open'] and \
                   last_m5_bar['open'] <= prev_m5_bar['close'] and \
                   last_m5_bar['close'] > prev_m5_bar['open']:
                    self.logger.info(f"{log_prefix} M5 确认: 看涨吞没 @ {last_m5_bar.name}")
                    return True
                # Pin Bar (Hammer)
                body_size = abs(last_m5_bar['close'] - last_m5_bar['open'])
                lower_wick = min(last_m5_bar['open'], last_m5_bar['close']) - last_m5_bar['low']
                if lower_wick > body_size * 1.5 and body_size < (last_m5_bar['high'] - last_m5_bar['low']) * 0.4: 
                    self.logger.info(f"{log_prefix} M5 确认: 底部Pin Bar @ {last_m5_bar.name}")
                    return True
            
            self.logger.debug(f"{log_prefix} M5 未出现明确反转形态进行确认。Signal: {signal_type}")
            return False

        except Exception as e:
            self.logger.error(f"{log_prefix} M5/M15 确认过程中出错: {e}", exc_info=True)
            return False

    def _execute_trading_logic(self, symbol: str, current_bar: pd.DataFrame, space_info: dict, all_symbol_spaces: list, current_time_utc: pd.Timestamp):
        """
        执行关键时间权重拐点策略的交易逻辑。
        """
        space_id = space_info.get('id', 'N/A')
        log_prefix = f"[{self.strategy_name}-{symbol}-{current_time_utc}-SpaceID:{space_id}]"
        self.logger.debug(f"{log_prefix} _execute_trading_logic called. Current_time_utc (engine time): {current_time_utc}")

        # current_time_utc 现在是方法参数
        # current_bar_time = current_bar['time'].iloc[0] # 这个仍然是从DataFrame的'time'列获取，代表当前K线自己的时间
        
        # 从DataFrame中安全地提取K线数据
        # 确保 current_bar 是单行 DataFrame
        if not isinstance(current_bar, pd.DataFrame) or current_bar.shape[0] != 1:
            self.logger.error(f"{log_prefix} _execute_trading_logic 期望 current_bar 是单行 DataFrame，但得到: {type(current_bar)}{' shape ' + str(current_bar.shape) if hasattr(current_bar, 'shape') else ''}")
            return

        current_bar_time = current_bar['time'].iloc[0] # K线自身的时间戳
        self.logger.debug(f"{log_prefix} Current bar time (from data): {current_bar_time}, O={current_bar['open'].iloc[0]:.5f}, H={current_bar['high'].iloc[0]:.5f}, L={current_bar['low'].iloc[0]:.5f}, C={current_bar['close'].iloc[0]:.5f}")

        event_name = space_info.get('event_name', 'N/A') # 用于 comment
        current_bar_close_price = current_bar['close'].iloc[0]
        current_bar_high = current_bar['high'].iloc[0]
        current_bar_low = current_bar['low'].iloc[0]

        # 使用传入的 current_time_utc (引擎的主循环时间) 来判断关键时间
        is_critical_time_flag = self._is_key_time(current_time_utc, space_info)
        self.logger.debug(f"{log_prefix} Is critical time? {is_critical_time_flag is not None}. (Critical time point if any: {is_critical_time_flag})")

        if is_critical_time_flag:
            # _is_at_turning_point 应该使用 current_bar (Series)
            # 但 current_bar 现在是 DataFrame，所以需要传递 Series
            current_bar_series_for_turning_point_check = current_bar.iloc[0] # 获取单行DataFrame对应的Series
            self.logger.debug(f"{log_prefix} Critical time confirmed. Checking for turning point.")
            turning_point_type = self._is_at_turning_point(symbol, current_bar_series_for_turning_point_check, space_info, all_symbol_spaces)
            self.logger.debug(f"{log_prefix} Turning point type: {turning_point_type}")

            if turning_point_type:
                position = self.positions.get(symbol, {'volume': 0.0})
                self.logger.debug(f"{log_prefix} Current position for {symbol}: Volume={position.get('volume', 0.0)}, EntryPrice={position.get('entry_price', 0.0)}")

                if position['volume'] == 0: # 只有在没有持仓时才考虑入场
                    self.logger.info(f"{log_prefix} Turning point '{turning_point_type}' detected at critical time. No active position. Evaluating entry.")
                    pip_size = self._get_pip_size(symbol)
                    if pip_size is None:
                        self.logger.warning(f"{log_prefix} Pip size not found for {symbol}, using default for SL/TP calc. This may be incorrect.")
                        pip_size = 0.0001 if "JPY" not in symbol.upper() else 0.01
                    
                    signal_confirmed_by_m5_m15 = True # Default to true if not using confirmation
                    trade_comment_suffix = ""

                    # 根据拐点类型决定交易方向
                    order_side = None
                    if 'UPPER_BOUND' in turning_point_type or 'RESISTANCE' in turning_point_type:
                        order_side = OrderSide.SELL
                        self.logger.info(f"{log_prefix} Potential SELL signal based on turning point '{turning_point_type}'.")
                        if self.confirm_with_m5_m15:
                            self.logger.debug(f"{log_prefix} Checking M5/M15 confirmation for SELL signal.")
                            signal_confirmed_by_m5_m15 = self._confirm_with_m5_m15(symbol, current_bar_time, 'SELL')
                            trade_comment_suffix = "_M5Conf" if signal_confirmed_by_m5_m15 else "_M5Rej"
                            self.logger.info(f"{log_prefix} M5/M15 confirmation for SELL: {signal_confirmed_by_m5_m15}")
                    elif 'LOWER_BOUND' in turning_point_type or 'SUPPORT' in turning_point_type:
                        order_side = OrderSide.BUY
                        self.logger.info(f"{log_prefix} Potential BUY signal based on turning point '{turning_point_type}'.")
                        if self.confirm_with_m5_m15:
                            self.logger.debug(f"{log_prefix} Checking M5/M15 confirmation for BUY signal.")
                            signal_confirmed_by_m5_m15 = self._confirm_with_m5_m15(symbol, current_bar_time, 'BUY')
                            trade_comment_suffix = "_M5Conf" if signal_confirmed_by_m5_m15 else "_M5Rej"
                            self.logger.info(f"{log_prefix} M5/M15 confirmation for BUY: {signal_confirmed_by_m5_m15}")

                    if order_side and signal_confirmed_by_m5_m15:
                        self.logger.info(f"{log_prefix} Signal confirmed. Proceeding to place {order_side.name} order.")
                        # 尝试使用穷尽策略的形态确认来增强信号 (如果配置了)
                        exhaustion_signal = None
                        if self._ex_checker and self.params.get('ktwtp_params', {}).get('use_exhaustion_confirmation', False):
                            self.logger.debug(f"{log_prefix} Using ExhaustionStrategy for confirmation.")
                            # _ex_checker._execute_trading_logic 需要 symbol, current_bar (DataFrame), space_info, all_symbol_spaces, current_time_utc
                            # 重要的是 _ex_checker 内部如何返回信号，这里假设它能修改 space_info 或有其他方式获取信号
                            # 这是一个简化的调用，实际可能需要更复杂的交互或 ex_checker 返回一个明确的信号对象
                            # For now, let's assume _ex_checker might set a flag or we call a specific check method if available.
                            # This part needs careful design of how ex_checker provides its signal to KTWTP.
                            # As a placeholder, let's assume ex_checker has a method like `check_exhaustion_signal`
                            # exhaustion_signal = self._ex_checker.check_exhaustion_signal(symbol, current_bar, space_info, order_side)
                            # For P2 logging, we'll just log the attempt to call it.
                            self.logger.info(f"{log_prefix} Calling internal ExhaustionStrategy checker for {order_side.name} confirmation.")
                            # This is a conceptual call, actual implementation of ex_checker interaction might differ.
                            # We are not actually executing ex_checker's trading logic here, but checking for its signal.
                            # Let's assume for now that if ex_checker is used, it's an additional filter.
                            # If ex_checker is meant to *replace* KTWTP's logic, the flow would be different.
                            # For P2, the focus is on logging the call if it were to happen.
                            # A more realistic integration would be: ex_checker.get_signal_if_any(...)
                            # For now, we'll assume if use_exhaustion_confirmation is true, we'd call it.
                            # This log indicates the *intent* or *potential path* for P2 testing.

                        # 计算止损和止盈
                        sl_pips = self.params.get('ktwtp_params', {}).get('stop_loss_pips', 20)
                        sl_price = 0.0
                        tp_price = 0.0

                        if order_side == OrderSide.BUY:
                            sl_price = current_bar_close_price - sl_pips * pip_size
                            # 确保SL在K线低点之下 (更安全的做法)
                            sl_price = min(sl_price, current_bar_low - pip_size) 
                            tp_price = current_bar_close_price + (current_bar_close_price - sl_price) * self.profit_loss_ratio
                            self.logger.info(f"{log_prefix} BUY order params: Entry ~{current_bar_close_price:.5f}, SL={sl_price:.5f} (based on {sl_pips} pips or bar low), TP={tp_price:.5f} (ratio {self.profit_loss_ratio})")
                        elif order_side == OrderSide.SELL:
                            sl_price = current_bar_close_price + sl_pips * pip_size
                            # 确保SL在K线高点之上
                            sl_price = max(sl_price, current_bar_high + pip_size)
                            tp_price = current_bar_close_price - (sl_price - current_bar_close_price) * self.profit_loss_ratio
                            self.logger.info(f"{log_prefix} SELL order params: Entry ~{current_bar_close_price:.5f}, SL={sl_price:.5f} (based on {sl_pips} pips or bar high), TP={tp_price:.5f} (ratio {self.profit_loss_ratio})")

                        comment = f"KTWTP_{order_side.name}_{turning_point_type[:5]}_{event_name[:10]}{trade_comment_suffix}"
                        self.logger.info(f"{log_prefix} Placing {order_side.name} order with comment: {comment}")
                        self._place_order(symbol, order_side, current_bar, sl_price, tp_price, comment)
                        # 可以在 space_info 中记录已交易，避免重复
                        space_info[f'ktwtp_trade_placed_at_{is_critical_time_flag.strftime("%Y%m%d%H%M")}'] = True
                        self.logger.info(f"{log_prefix} Order placed. Marked space_info for this critical time.")
                        return # 完成交易逻辑
                    elif not signal_confirmed_by_m5_m15:
                        self.logger.info(f"{log_prefix} Signal for {order_side.name if order_side else 'N/A'} NOT confirmed by M5/M15. No order placed.")
                    else:
                        self.logger.debug(f"{log_prefix} No valid order side determined or signal not confirmed. No order placed.")
                else:
                    self.logger.debug(f"{log_prefix} Active position exists (Volume: {position['volume']}). Skipping new entry at turning point.")
            else: # Not at a turning point
                self.logger.debug(f"{log_prefix} Critical time, but not at a recognized turning point. No action.")
        else: # Not a critical time
            self.logger.debug(f"{log_prefix} Not a critical time. No KTWTP-specific logic executed.")
        self.logger.debug(f"{log_prefix} Finished KTWTP trading logic execution.")

    def _calculate_vwap(self, symbol: str, period: int, current_time: pd.Timestamp) -> Optional[float]:
        """
        Calculates the Volume Weighted Average Price (VWAP) for a given period.
        Args:
            historical_data (pd.DataFrame): DataFrame with 'high', 'low', 'close', 'volume' columns.
            period (int): The time period for VWAP calculation (number of recent bars).

        Returns:
            Optional[float]: The VWAP value, or None if calculation fails or data is insufficient.
        """
        if historical_data is None or len(historical_data) < period:
            self.logger.warning(f"[{self.strategy_name}] VWAP calculation: Not enough historical data. Have {len(historical_data) if historical_data is not None else 0}, need {period}.")
            return None
        
        relevant_data = historical_data.tail(period)
        if relevant_data.empty or 'high' not in relevant_data or 'low' not in relevant_data or 'close' not in relevant_data or 'volume' not in relevant_data:
            self.logger.warning(f"[{self.strategy_name}] VWAP calculation: Relevant data is empty or missing required columns for period {period}.")
            return None
            
        try:
            typical_price = (relevant_data['high'] + relevant_data['low'] + relevant_data['close']) / 3
            tp_volume = typical_price * relevant_data['volume']
            
            sum_tp_volume = tp_volume.sum()
            sum_volume = relevant_data['volume'].sum()
            
            if sum_volume == 0:
                self.logger.warning(f"[{self.strategy_name}] VWAP calculation: Sum of volume is zero for period {period}, cannot calculate VWAP.")
                return None
                
            vwap = sum_tp_volume / sum_volume
            
            if np.isnan(vwap) or np.isinf(vwap):
                self.logger.warning(f"[{self.strategy_name}] VWAP calculation: Result is NaN or Inf for period {period}.")
                return None
            return vwap
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] Error calculating VWAP: {e}", exc_info=False)
            return None

    def _place_order(self, symbol: str, side: OrderSide, current_bar: pd.DataFrame, stop_loss_price: float, take_profit_price: float, comment: str):
        """
        放置订单并提交信号到聚合器
        
        Args:
            symbol: 交易品种
            side: 交易方向 (BUY/SELL)
            current_bar: 当前K线数据 (DataFrame)
            stop_loss_price: 止损价格
            take_profit_price: 止盈价格
            comment: 订单注释
        """
        # 提取关键数据
        current_bar_time = current_bar['time'].iloc[0]
        entry_price = current_bar['close'].iloc[0]  # 以收盘价作为入场价格
        
        # 1. 提交信号到聚合器
        action = "BUY" if side == OrderSide.BUY else "SELL"
        confidence = 1.0  # 默认置信度为 1.0
        
        # 构建元数据
        metadata = {
            "strategy_name": self.strategy_name,
            "signal_type": "key_time_turning_point",
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "comment": comment
        }
        
        # 调用父类的信号提交方法
        self._submit_signal(
            symbol=symbol,
            action=action,
            timestamp=current_bar_time,
            confidence=confidence,
            metadata=metadata
        )
        
        # 2. 下单
        self.logger.info(f"[{self.strategy_name}] 放置{action}订单: {symbol} @ ~{entry_price:.5f}, SL={stop_loss_price:.5f}, TP={take_profit_price:.5f}, 注释={comment}")
        
        try:
            # 计算仓位大小
            risk_amount = self._calculate_risk_amount(entry_price, stop_loss_price, symbol)
            
            # 创建订单对象
            order = {
                'symbol': symbol,
                'side': side,
                'price': entry_price,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'volume': risk_amount,
                'type': OrderType.MARKET,
                'magic': self.magic_number,
                'comment': comment
            }
            
            # 执行订单
            order_result = self.execution_engine.place_order(order)
            self.logger.info(f"[{self.strategy_name}] 订单执行结果: {order_result}")
            return order_result
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 下单失败: {e}", exc_info=True)
            return None
            
    def _calculate_risk_amount(self, entry_price: float, stop_loss_price: float, symbol: str) -> float:
        """计算基于风险的仓位大小"""
        try:
            # 使用风险管理器计算仓位
            signal_data = {
                'symbol': symbol,
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price,
                'strategy': self.strategy_name
            }
            position_size = self.risk_manager.calculate_position_size(signal_data)
            
            # 确保仓位大小在合理范围内
            min_lot = self.params.get('min_lot_size', 0.01)
            max_lot = self.params.get('max_lot_size', 10.0)
            
            if position_size < min_lot:
                self.logger.warning(f"[{self.strategy_name}] 计算的仓位 {position_size} 小于最小手数 {min_lot}，使用最小手数")
                position_size = min_lot
            elif position_size > max_lot:
                self.logger.warning(f"[{self.strategy_name}] 计算的仓位 {position_size} 大于最大手数 {max_lot}，使用最大手数")
                position_size = max_lot
                
            return position_size
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 计算仓位大小时出错: {e}", exc_info=True)
            return self.params.get('default_lot_size', 0.01)  # 返回默认手数

    def get_active_spaces_for_symbol(self, symbol: str, current_time_utc: pd.Timestamp) -> list:
        # KTWTP 维护自己的 active_spaces 列表或者依赖 EventDrivenSpaceStrategy 的实现
        # 如果它自己维护，确保在 __init__ 或 _process_events 中初始化 self.active_spaces (无下划线)
        # 如果它期望从父类获取，那么父类必须提供 self.active_spaces
        # 根据错误日志，KTWTP 尝试访问 self._active_spaces，而 EDSS 初始化的是 self.active_spaces
        # return self._active_spaces.get(symbol, []) # 这是原始代码，但 self._active_spaces 可能不存在
        # 正确的实现应该是调用父类的方法，或者直接访问 self.active_spaces (如果父类没有提供get方法)
        return super().get_active_spaces(symbol=symbol, current_time_utc=current_time_utc)

    def _process_events(self, events_df: pd.DataFrame, market_data: Dict[str, Dict[str, pd.DataFrame]], current_processing_time: pd.Timestamp):
        # Minimal KTWTP might call super() or have its own logic
        # For now, assume it does nothing beyond what the parent might do, or it's an override point.
        # If this method is intended to replace parent's logic entirely and does nothing, that's fine.
        # If it's meant to augment, it should call super()._process_events(...)
        _market_data = market_data # 标记为未使用
        _current_processing_time = current_processing_time # 标记为未使用
        
        # 确保正确调用父类方法，如果需要的话
        # super()._process_events(events_df, market_data, current_processing_time)
        
        # KTWTP 特定的事件处理逻辑（如果需要）
        # 例如，基于事件直接调整关键时间或现有空间
        # if events_df is not None and not events_df.empty:
        #     self.logger.debug(f"[{self.strategy_name}] _process_events received {len(events_df)} events.")
        pass

    def _process_bar(self, symbol: str, current_bar_df: pd.DataFrame, current_processing_time: pd.Timestamp, all_symbol_m30_data: pd.DataFrame):
        # Minimal KTWTP might call super() or manage its own spaces
        # current_bar is expected to be a single-row DataFrame by the parent's _process_bar
        # all_symbol_m30_data is the full M30 history for the symbol for lookbacks
        
        # 确保正确调用父类方法，它负责空间失效等逻辑
        super()._process_bar(symbol, current_bar_df, current_processing_time, all_symbol_m30_data)

        # KTWTP 特定的K线处理逻辑（如果需要，但主要逻辑在 _execute_trading_logic 中）
        # 例如，检查是否有基于当前K线的穷尽信号（如果 _ex_checker 启用）
        # if self._ex_checker:
        #     exhaustion_signal = self._ex_checker.check_exhaustion_signal(symbol, current_bar_df, current_processing_time)
        #     if exhaustion_signal:
        #         # Process exhaustion signal...
        #         pass
        pass

    # _map_event_to_symbol 方法已被移除，以使用 EventDrivenSpaceStrategy 基类的实现。
    # 基类实现将根据 event_mapping.yaml 文件动态映射财经事件到交易品种。
    # def _map_event_to_symbol(self, event_data: dict) -> Optional[str]:
    #     ...
    #     (原有代码已删除)


# --- 可选的测试入口 ---
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.info("运行 KeyTimeWeightTurningPointStrategy 测试代码...")

    # 模拟配置
    # KTWTP 策略的参数应该在其自己的键下，例如 'KeyTimeWeightTurningPointStrategy'
    # 或者，如果参数是在一个通用的 'strategy_params' 下按策略名组织的，那么 __init__ 中的 self.params 应该能正确获取。
    # 这里我们假设配置是直接传递给策略的，并且 self.params 指向这部分。
    mock_strategy_params_config = { # These are params for KTWTP itself
        'ktwtp_params': {
            'key_time_hours_after_event': [0.1, 0.2], # Use small hours for quick testing
            'use_space_boundaries_as_turning_points': True,
            'turning_point_buffer_pips': 5,
            'confirm_with_m5_m15': False, # Disable M5 confirm for simpler test
            'm5_m15_lookback': 3,
            'stop_loss_buffer_pips': 10,
            'take_profit_target': 'ratio', 
            'risk_reward_ratio': 1.5 # Changed from profit_loss_ratio for consistency
        },
        'event_mapping': { # This should be accessible via self.params.event_mapping
            'currency_to_symbol': {
                'EUR': 'EURUSD',
                'USD': 'EURUSD', # Example if USD events also affect EURUSD
            },
            'default_event_symbol': 'EURUSD'
        },
        'primary_timeframe': 'M30' # KTWTP specific, or could be common
    }
    # OmegaConf.create() is better for real config handling in tests
    mock_strategy_config_omegaconf = OmegaConf.create(mock_strategy_params_config)


    current_bar_time = pd.Timestamp.now(tz=pytz.UTC).replace(second=0, microsecond=0) - timedelta(minutes=120)
    
    # 模拟 DataProvider
    class MockDataProviderKTWTP(DataProvider):
        def get_historical_prices(self, symbol, start_time, end_time, timeframe):
            # logger.info(f"MockDataProviderKTWTP: 请求 {symbol} {timeframe} 数据从 {start_time} 到 {end_time}")
            # Create a range of times for the requested period
            freq_map = {'M30': '30min', 'M5': '5min', 'H1': 'H'}
            dt_idx = pd.date_range(start=start_time, end=end_time, freq=freq_map.get(timeframe, '30min'), tz='UTC')
            if dt_idx.empty and start_time <= end_time : # If range is too small, create at least a few bars
                 dt_idx = pd.date_range(start=start_time, periods=max(5, self.m5_m15_lookback if hasattr(self, 'm5_m15_lookback') else 5), freq=freq_map.get(timeframe, '30min'), tz='UTC')
            
            if dt_idx.empty: return pd.DataFrame()

            data_len = len(dt_idx)
            base_price = 1.0800
            data = {
                'open': np.array([base_price + (i * 0.0001) for i in range(data_len)]),
                'high': np.array([base_price + (i * 0.0001) + 0.0005 for i in range(data_len)]),
                'low':  np.array([base_price + (i * 0.0001) - 0.0005 for i in range(data_len)]),
                'close':np.array([base_price + (i * 0.0001) + np.random.uniform(-0.0002, 0.0002) for i in range(data_len)]),
                'volume': np.random.randint(100, 200, size=data_len)
            }
            df = pd.DataFrame(data, index=dt_idx)
            # Ensure specific bar for testing exists
            if timeframe == 'M30' and current_bar_time in df.index:
                 df.loc[current_bar_time, 'open'] = mock_current_bar_data_at_key_time['open']
                 df.loc[current_bar_time, 'high'] = mock_current_bar_data_at_key_time['high']
                 df.loc[current_bar_time, 'low'] = mock_current_bar_data_at_key_time['low']
                 df.loc[current_bar_time, 'close'] = mock_current_bar_data_at_key_time['close']
            
            return df

        def get_current_market_data(self, symbols: List[str], timeframe: str) -> Dict[str, pd.Series]:
            return {s: pd.Series(dtype=float) for s in symbols} # Empty series
        
        def get_active_spaces(self, symbol: str, current_time_utc: datetime) -> List[Dict]:
            return [] # Let the strategy manage its own spaces or mock them separately
        
        def get_all_events_for_period(self, start_date, end_date):
            return pd.DataFrame([
                {'Currency': 'EUR', 'Timestamp': pd.Timestamp('2023-01-01 09:50:00+0000', tz='UTC'), 'Event': 'Test Event', 'datetime': pd.Timestamp('2023-01-01 09:50:00+0000', tz='UTC') }
            ])


    # 模拟 ExecutionEngine
    class MockExecutionEngineKTWTP:
        def __init__(self, config, data_provider):
            self.logger = logging.getLogger("MockExecKTWTP")
        def place_order(self, order: Order): # Expects Order object
            self.logger.info(f"MockExecutionEngineKTWTP received order: {order.to_dict()}")
            # Simulate order filling
            order.status = OrderStatus.FILLED
            order.executed_volume = order.volume
            order.average_filled_price = order.limit_price if order.limit_price else (1.0800 if order.side == OrderSide.BUY else 1.0850) # Dummy fill price
            order.last_update_time = datetime.utcnow()
            order.order_id = f"sandbox_mock_{int(datetime.utcnow().timestamp()*1000)}"
            return order # Return the Order object
        def get_position(self, symbol: str): return None
        def get_account_balance(self): return {'USD': 100000.0}

    # 模拟 RiskManager
    class MockRiskManagerKTWTP:
        def __init__(self, config, broker, data_provider): self.logger = logging.getLogger("MockRiskKTWTP")
        def calculate_position_size(self, signal_data: Dict[str, Any]) -> Optional[float]:
            self.logger.info(f"MockRiskManagerKTWTP calculate_position_size for signal: {signal_data}")
            return 0.01 # Fixed size for testing
        def check_order(self, order_params: Dict[str, Any]) -> bool: return True

    
    mock_dp = MockDataProviderKTWTP(None) # Config not used in this mock DP
    mock_ee = MockExecutionEngineKTWTP(None, None)
    mock_rm = MockRiskManagerKTWTP(None, None, None)
    
    # Pass the strategy-specific part of the config
    strategy_instance = KeyTimeWeightTurningPointStrategy(
        strategy_id="KeyTimeWeightTurningPointStrategy",
        app_config=mock_strategy_config_omegaconf, # Pass the OmegaConf DictConfig object
        data_provider=mock_dp,
        execution_engine=mock_ee,
        risk_manager=mock_rm,
        live_mode=False
    )

    # --- Test Scenario ---
    test_symbol = "EURUSD"
    # 1. Simulate an event to create a space
    simulated_event_time = current_bar_time - timedelta(hours=1) # Event 1 hour ago
    mock_event_data = pd.DataFrame([{
        'Currency': 'EUR', 
        'datetime': simulated_event_time, # Ensure this is a Timestamp
        'name': 'Mock Event for KTWTP', 
        'importance': 3
    }])
    strategy_instance._process_events(mock_event_data, {}, pd.Timestamp.now(tz=pytz.UTC)) # Let strategy create its space

    # 2. Simulate current bar at a key time
    # Key times are 0.1h (6min) and 0.2h (12min) after event
    key_time_for_test = simulated_event_time + timedelta(minutes=6) 
    
    mock_current_bar_data_at_key_time = {
        'time': key_time_for_test, # This will be the current_time_utc for _execute_trading_logic
        'open': 1.0845, 'high': 1.0855, 'low': 1.0840, 'close': 1.0850 # Price near upper bound
    }
    mock_current_bar_series_at_key_time = pd.Series(mock_current_bar_data_at_key_time)
    
    # Manually set a dummy active space for testing _execute_trading_logic directly
    # In a real run, _process_bar -> get_active_spaces -> _execute_trading_logic
    dummy_space_for_test = {
        'id': 'test_space_ktwtp', 'symbol': test_symbol, 'event_name': 'Mock Event for KTWTP',
        'event_time_utc': simulated_event_time, 'status': 'active',
        'upper_bound': 1.0852, 'lower_bound': 1.0750 # Price is near this upper_bound
    }
    strategy_instance.active_spaces[test_symbol] = [dummy_space_for_test]


    logger.info(f"--- Test: Executing trading logic for {test_symbol} at key time {key_time_for_test} ---")
    strategy_instance._execute_trading_logic(
        symbol=test_symbol, 
        current_bar=mock_current_bar_series_at_key_time, 
        space_info=dummy_space_for_test, 
        all_symbol_spaces=[dummy_space_for_test],
        current_time_utc=key_time_for_test
    )

    logger.info("--- KTWTP Test Run Complete ---")
