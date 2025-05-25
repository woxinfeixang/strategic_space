# coding: utf-8
"""
衰竭策略 (Exhaustion Strategy)

策略逻辑:
1. 继承 EventDrivenSpaceStrategy 来利用其定义的博弈空间。
2. 监控活跃的博弈空间。
3. 识别价格在博弈空间边界附近形成的衰竭形态。
    - 多次尝试突破失败 (例如，长上/下影线)。
    - M30 K线在边界附近出现反转形态 (例如，吞没、pin bar)。
    - 价格二次推动未能创新高/低。
    - (可选) 结合技术指标背离 (如 RSI, MACD)。
4. 在确认衰竭形态后，在边界附近反向入场。
5. 设置止损和止盈。

止盈止损设置方法 (根据PDF理解，需要细化):
- 止损: 设置在衰竭形态的高点/低点之外一定距离。
- 止盈: 目标是博弈空间的另一侧边界，或固定盈亏比。
"""

import pandas as pd
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sys # 添加缺失的导入
# import talib # 如果使用 TA-Lib 指标

# 导入基础策略类和数据提供者
from .event_driven_space_strategy import EventDrivenSpaceStrategy
from .live.order import OrderSide, OrderType
# from .core.order import Order, OrderType, OrderSide
from strategies.core.data_providers import DataProvider
from strategies.live.sandbox import SandboxExecutionEngine # 新增导入
from strategies.risk_management.risk_manager import RiskManager # 新增导入
from omegaconf import DictConfig # 添加导入
from strategies.utils.signal_aggregator import SignalAggregator # 导入信号聚合器
from strategies.utils.key_time_detector import KeyTimeDetector # 导入关键时间检测器

class ExhaustionStrategy(EventDrivenSpaceStrategy):
    """
    衰竭策略，继承自事件驱动空间策略。
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
        self.strategy_name = "ExhaustionStrategy" # 确保每个策略有自己独特的名字
        # self.logger = logging.getLogger(self.strategy_name) # Logger is already initialized in StrategyBase
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Initializing...")

        # 策略特定参数 (从 app_config 中通过 self.params 获取)
        self.exhaustion_lookback = self.params.get('exhaustion_lookback', 20)
        self.exhaustion_threshold_factor = self.params.get('exhaustion_threshold_factor', 0.75)
        self.required_bars = self.exhaustion_lookback
        if self.required_bars <= 0:
            self.logger.warning(f"[{self.strategy_name}-{self.strategy_id}] exhaustion_lookback configured to {self.exhaustion_lookback}, required_bars will default to 3.")
            self.required_bars = 3
        self.stop_loss_pip_buffer = self.params.get('stop_loss_pip_buffer', 5) # 止损缓冲点数 (需要根据品种调整)
        self.take_profit_target = self.params.get('take_profit_target', 'opposite_boundary') # 止盈目标: 'opposite_boundary' 或 'ratio'
        self.take_profit_ratio = self.params.get('take_profit_ratio', 1.5) # 如果止盈目标是比例

        # (可选) RSI 参数用于背离检测
        self.rsi_period = self.params.get('rsi_period', 14)
        self.rsi_divergence_lookback = self.params.get('rsi_divergence_lookback', 5)
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Parameters: lookback={self.exhaustion_lookback}, threshold_factor={self.exhaustion_threshold_factor}, sl_buffer={self.stop_loss_pip_buffer}, tp_target='{self.take_profit_target}', tp_ratio={self.take_profit_ratio}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] RSI Params (optional): period={self.rsi_period}, divergence_lookback={self.rsi_divergence_lookback}")

        # 初始化信号聚合器（如果父类未初始化）
        if not hasattr(super(), 'signal_aggregator') or super().signal_aggregator is None:
            self.signal_aggregator = SignalAggregator(self.logger, self.params.get('signal_aggregator_config', {}))
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 初始化信号聚合器")
        else:
            self.signal_aggregator = super().signal_aggregator
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 使用父类信号聚合器")
            
        # 初始化关键时间检测器
        self.key_time_detector = KeyTimeDetector(self.logger)
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 初始化关键时间检测器")
            
        # 信号聚合器控制参数
        self.use_signal_aggregator = self.params.get('use_signal_aggregator', True)
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Signal Aggregator enabled: {self.use_signal_aggregator}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Initialization complete.")

    def _execute_trading_logic(self, symbol: str, current_bar: dict, space_info: dict, all_symbol_spaces: list):
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}][{symbol}] ENTER _execute_trading_logic. Space ID: {space_info.get('id', 'N/A')}, Event: {space_info.get('event_name', 'UnknownEvent')}, Bar Time: {current_bar.get('time')}")
        self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}][{symbol}] _execute_trading_logic: Current bar details: Open={current_bar.get('open')}, High={current_bar.get('high')}, Low={current_bar.get('low')}, Close={current_bar.get('close')}")
        """
        执行衰竭策略的交易逻辑。

        Args:
            symbol (str): 交易品种。
            current_bar (dict): 当前 K 线数据。
            space_info (dict): 当前正在处理的活跃空间信息。
            all_symbol_spaces (list): 该品种当前所有的活跃空间列表。
        """
        current_time = current_bar['time']
        close_price = current_bar['close']
        high_price = current_bar['high']
        low_price = current_bar['low']
        space_id = space_info.get('id', 'N/A')
        self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Executing trading logic for Space ID {space_id}. Bar: {current_bar}, Space: {space_info.get('event_name', 'N/A')}")
        
        # Plan Item 1.2.1 & 1.2.2: Unify boundary key names
        # upper_bound = space_info['upper_bound'] 
        # lower_bound = space_info['lower_bound']
        upper_bound = space_info.get('high')
        lower_bound = space_info.get('low')

        # Plan Item 1.2.3: Check for None boundaries
        if upper_bound is None or lower_bound is None:
            self.logger.warning(f"[{self.strategy_name}-{symbol}-{current_time}] Space ID {space_id} is missing 'high' or 'low' bounds. Skipping logic.")
            return

        event_name = space_info.get('event_name', space_info.get('event_title', 'N/A')) # Try event_title as fallback if event_name missing
        self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Space ID {space_id}: UpperBound={upper_bound:.5f}, LowerBound={lower_bound:.5f}, Event='{event_name}'")

        # 检查是否有持仓
        # Plan Item 1.1: Fix position acquisition
        # position = None # 假设无持仓 <- This was the bug
        position = self.execution_engine.get_position(symbol)
        self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Current position for {symbol}: {position}")

        # if position is None: # Original check, might need adjustment based on how get_position returns for no position
        # Adjusted check for no active position or zero volume
        if position is None or position.get('volume', 0.0) == 0.0:
            self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] No active position for {symbol}. Checking for exhaustion signals for Space ID {space_id}.")
            # 获取近期 K 线用于形态判断
            try:
                # 需要的回看期数 = 形态判断期数 + (可选)指标计算期数
                lookback_needed = max(self.exhaustion_lookback, self.rsi_period + self.rsi_divergence_lookback if 'talib' in sys.modules else self.exhaustion_lookback)
                start_query_time = current_time - pd.Timedelta(minutes=30 * (lookback_needed + 5)) # 加一点缓冲
                self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Fetching historical data for exhaustion check: start_time={start_query_time}, end_time={current_time}, lookback_needed={lookback_needed}")
                recent_bars_df = self.data_provider.get_historical_prices(
                    symbol=symbol,
                    start_time=start_query_time,
                    end_time=current_time,
                    timeframe='M30'
                )
                if recent_bars_df is None or len(recent_bars_df) < self.exhaustion_lookback:
                    self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Insufficient historical data for Space ID {space_id}. Have {len(recent_bars_df) if recent_bars_df is not None else 0}, need {self.exhaustion_lookback}.")
                    return
                # 确保包含当前 K 线
                if current_time not in recent_bars_df.index:
                     self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Current bar time {current_time} not in historical index. Appending current bar.")
                     current_bar_series = pd.Series(current_bar, name=current_time)
                     current_bar_df = pd.DataFrame([current_bar_series])
                     current_bar_df.index = [current_time]
                     for col in recent_bars_df.columns:
                         if col in current_bar_df.columns and recent_bars_df[col].dtype != current_bar_df[col].dtype:
                              try:
                                  current_bar_df[col] = current_bar_df[col].astype(recent_bars_df[col].dtype)
                              except Exception: pass
                     recent_bars_df = pd.concat([recent_bars_df, current_bar_df[recent_bars_df.columns]])
                recent_bars_df = recent_bars_df.sort_index().tail(lookback_needed) # 取所需的回看数据

            except Exception as e:
                self.logger.error(f"[{self.strategy_name}-{symbol}-{current_time}] Error getting historical data for exhaustion check on Space ID {space_id}: {e}", exc_info=True)
                return

            # --- 识别衰竭形态 ---
            self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Checking for exhaustion patterns for Space ID {space_id}.")
            sell_signal = self._check_bearish_exhaustion(recent_bars_df, upper_bound, symbol, current_time, space_id)
            buy_signal = self._check_bullish_exhaustion(recent_bars_df, lower_bound, symbol, current_time, space_id)

            # --- 入场逻辑 ---
            if sell_signal:
                self.logger.info(f"[{self.strategy_name}-{symbol}-{current_time}] Bearish exhaustion signal detected at {upper_bound:.5f} for Space ID {space_id} (Event: '{event_name}')")
                exhaustion_high = recent_bars_df['high'].tail(self.exhaustion_lookback).max()
                pip_size = super()._get_pip_size(symbol) # 明确调用父类方法
                if pip_size is None:
                    self.logger.warning(f"[{self.strategy_name}-{symbol}-{current_time}] Pip size not found for {symbol} on Space ID {space_id}. Cannot calculate SL/TP accurately.")
                    return
                stop_loss_price = exhaustion_high + self.stop_loss_pip_buffer * pip_size
                if self.take_profit_target == 'opposite_boundary':
                    take_profit_price = lower_bound
                else: # ratio
                    take_profit_price = close_price - (stop_loss_price - close_price) * self.take_profit_ratio
                self.logger.info(f"[{self.strategy_name}-{symbol}-{current_time}] Placing SELL order for Space ID {space_id}. Entry ~{close_price:.5f}, SL={stop_loss_price:.5f}, TP={take_profit_price:.5f}")
                # 下单
                self._place_order(symbol, OrderSide.SELL, current_bar, stop_loss_price, take_profit_price, f"Exh_Sell_{event_name[:10]}")

            elif buy_signal:
                self.logger.info(f"[{self.strategy_name}-{symbol}-{current_time}] Bullish exhaustion signal detected at {lower_bound:.5f} for Space ID {space_id} (Event: '{event_name}')")
                exhaustion_low = recent_bars_df['low'].tail(self.exhaustion_lookback).min()
                pip_size = super()._get_pip_size(symbol) # 明确调用父类方法
                if pip_size is None:
                    self.logger.warning(f"[{self.strategy_name}-{symbol}-{current_time}] Pip size not found for {symbol} on Space ID {space_id}. Cannot calculate SL/TP accurately.")
                    return
                stop_loss_price = exhaustion_low - self.stop_loss_pip_buffer * pip_size
                if self.take_profit_target == 'opposite_boundary':
                    take_profit_price = upper_bound
                else: # ratio
                    take_profit_price = close_price + (close_price - stop_loss_price) * self.take_profit_ratio
                self.logger.info(f"[{self.strategy_name}-{symbol}-{current_time}] Placing BUY order for Space ID {space_id}. Entry ~{close_price:.5f}, SL={stop_loss_price:.5f}, TP={take_profit_price:.5f}")
                # 下单
                self._place_order(symbol, OrderSide.BUY, current_bar, stop_loss_price, take_profit_price, f"Exh_Buy_{event_name[:10]}")
            else:
                self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] No exhaustion signal detected for Space ID {space_id}.")
        else:
            self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Position for {symbol} is not zero ({position.get('volume', 0.0)}). Skipping entry logic for Space ID {space_id}.")
        self.logger.debug(f"[{self.strategy_name}-{symbol}-{current_time}] Finished trading logic for Space ID {space_id}.")

    def _check_bearish_exhaustion(self, bars_df: pd.DataFrame, upper_bound: float, symbol: str, current_time: datetime, space_id: str) -> bool:
        """
        检查K线数据是否在指定上界附近形成顶部衰竭形态。
        (需要根据具体形态规则实现)
        """
        log_prefix = f"[{self.strategy_name}-{symbol}-{current_time}-SpaceID:{space_id}-BearishExhCheck]"
        self.logger.debug(f"{log_prefix} Checking near upper_bound {upper_bound:.5f}. Available bars: {len(bars_df)}")
        if len(bars_df) < self.exhaustion_lookback:
            self.logger.debug(f"{log_prefix} Insufficient data ({len(bars_df)} < {self.exhaustion_lookback}) for Space ID {space_id}")
            return False

        recent_bars = bars_df.tail(self.exhaustion_lookback)
        last_bar = recent_bars.iloc[-1]
        self.logger.debug(f"{log_prefix} Recent bars (last {self.exhaustion_lookback}) for Space ID {space_id}:\n{recent_bars.to_string(max_rows=5)}")
        self.logger.debug(f"{log_prefix} Last bar for Space ID {space_id}: H={last_bar['high']:.5f}, L={last_bar['low']:.5f}, O={last_bar['open']:.5f}, C={last_bar['close']:.5f}")

        # 1. K线接近或触及上界
        max_high_recent = recent_bars['high'].max()
        touched_upper = max_high_recent >= upper_bound
        self.logger.debug(f"{log_prefix} Max high in recent bars for Space ID {space_id}: {max_high_recent:.5f}. Touched upper bound? {touched_upper}")
        if not touched_upper:
            # self.logger.debug(f"{log_prefix} Not touched upper bound {upper_bound:.5f}. Max high: {max_high_recent:.5f}") # Redundant
            return False

        # 规则 a: 长上影线 Pin Bar
        body_size = abs(last_bar['close'] - last_bar['open'])
        upper_wick = last_bar['high'] - max(last_bar['open'], last_bar['close'])
        lower_wick = min(last_bar['open'], last_bar['close']) - last_bar['low']
        # Ensure body_size is not zero to avoid division by zero if used in ratio, and ensure wicks are non-negative
        body_size = max(body_size, 1e-9) # Avoid division by zero if body is flat
        upper_wick = max(0, upper_wick)
        lower_wick = max(0, lower_wick)

        is_pin_bar = upper_wick > body_size * 2 and upper_wick > lower_wick * 2 and last_bar['high'] >= upper_bound
        self.logger.debug(f"{log_prefix} Pin Bar Check for Space ID {space_id}: Body={body_size:.5f}, UpperWick={upper_wick:.5f}, LowerWick={lower_wick:.5f}, LastHigh>=Bound? {last_bar['high'] >= upper_bound}. IsPinBar? {is_pin_bar}")
        if is_pin_bar:
            self.logger.info(f"{log_prefix} Bearish Pin Bar detected at upper bound for Space ID {space_id}.")
            return True

        # 规则 b: 看跌吞没形态 (Bearish Engulfing)
        if len(recent_bars) >= 2:
            prev_bar = recent_bars.iloc[-2]
            # 当前K线为阴线，前一根K线为阳线
            is_curr_bearish = last_bar['close'] < last_bar['open']
            is_prev_bullish = prev_bar['close'] > prev_bar['open']
            # 当前K线实体完全吞没前一根K线实体
            engulfs_prev_body = last_bar['open'] > prev_bar['close'] and last_bar['close'] < prev_bar['open']
            # 发生在价格高位 (接近上边界)
            at_highs = last_bar['high'] >= upper_bound or prev_bar['high'] >= upper_bound
            is_bearish_engulfing = is_curr_bearish and is_prev_bullish and engulfs_prev_body and at_highs
            self.logger.debug(f"{log_prefix} Bearish Engulfing Check for Space ID {space_id}: CurrBearish? {is_curr_bearish}, PrevBullish? {is_prev_bullish}, Engulfs? {engulfs_prev_body}, AtHighs? {at_highs}. IsBearishEngulfing? {is_bearish_engulfing}")
            if is_bearish_engulfing:
                self.logger.info(f"{log_prefix} Bearish Engulfing pattern detected at upper bound for Space ID {space_id}.")
                return True
        else:
            self.logger.debug(f"{log_prefix} Not enough bars for Bearish Engulfing check (need 2, have {len(recent_bars)}) for Space ID {space_id}.")

        # 规则 c: 多次尝试突破失败 (例如，连续几根K线的最高价无法显著超越前期高点，且收盘回落)
        # 简化: 检查最近N根K线中，是否有M根K线的最高价接近上边界，但收盘价均低于上边界一个阈值
        if len(recent_bars) >= 3: # Example: check last 3 bars
            bars_near_upper = 0
            threshold_distance = (upper_bound - lower_bound) * 0.1 # e.g., 10% of space height as threshold
            for i in range(1, 4): # Last 3 bars
                bar_to_check = recent_bars.iloc[-i]
                if bar_to_check['high'] >= upper_bound - threshold_distance and bar_to_check['close'] < upper_bound - (threshold_distance * 0.5):
                    bars_near_upper += 1
            failed_breakouts = bars_near_upper >= 2 # Example: 2 out of 3 bars show failed attempts
            self.logger.debug(f"{log_prefix} Failed Breakouts Check for Space ID {space_id}: BarsNearUpper={bars_near_upper} (threshold_dist={threshold_distance:.5f}). FailedBreakouts? {failed_breakouts}")
            if failed_breakouts:
                self.logger.info(f"{log_prefix} Multiple failed breakout attempts detected at upper bound for Space ID {space_id}.")
                return True
        else:
            self.logger.debug(f"{log_prefix} Not enough bars for Failed Breakouts check (need 3, have {len(recent_bars)}) for Space ID {space_id}.")

        # (可选) 规则 d: RSI 背离 (需要 TA-Lib)
        # if 'talib' in sys.modules and len(recent_bars) >= self.rsi_period + self.rsi_divergence_lookback:
        #     rsi_values = talib.RSI(recent_bars['close'], timeperiod=self.rsi_period)
        #     # 简单顶背离: 价格创新高，RSI未创新高
        #     # (实现细节省略，需要比较最近的几个价格高点和对应的RSI值)
        #     self.logger.debug(f"{log_prefix} RSI divergence check (not fully implemented) for Space ID {space_id}.")

        self.logger.debug(f"{log_prefix} No bearish exhaustion pattern met for Space ID {space_id}.")
        return False

    def _check_bullish_exhaustion(self, bars_df: pd.DataFrame, lower_bound: float, symbol: str, current_time: datetime, space_id: str) -> bool:
        """
        检查K线数据是否在指定下界附近形成底部衰竭形态。
        (需要根据具体形态规则实现)
        """
        log_prefix = f"[{self.strategy_name}-{symbol}-{current_time}-SpaceID:{space_id}-BullishExhCheck]"
        self.logger.debug(f"{log_prefix} Checking near lower_bound {lower_bound:.5f}. Available bars: {len(bars_df)}")
        if len(bars_df) < self.exhaustion_lookback:
            self.logger.debug(f"{log_prefix} Insufficient data ({len(bars_df)} < {self.exhaustion_lookback}) for Space ID {space_id}")
            return False

        recent_bars = bars_df.tail(self.exhaustion_lookback)
        last_bar = recent_bars.iloc[-1]
        self.logger.debug(f"{log_prefix} Recent bars (last {self.exhaustion_lookback}) for Space ID {space_id}:\n{recent_bars.to_string(max_rows=5)}")
        self.logger.debug(f"{log_prefix} Last bar for Space ID {space_id}: H={last_bar['high']:.5f}, L={last_bar['low']:.5f}, O={last_bar['open']:.5f}, C={last_bar['close']:.5f}")

        # 1. K线接近或触及下界
        min_low_recent = recent_bars['low'].min()
        touched_lower = min_low_recent <= lower_bound
        self.logger.debug(f"{log_prefix} Min low in recent bars for Space ID {space_id}: {min_low_recent:.5f}. Touched lower bound? {touched_lower}")
        if not touched_lower:
            # self.logger.debug(f"{log_prefix} 未触及下界 {lower_bound:.5f}。最低价: {min_low_recent:.5f}") # Redundant
            return False

        # 规则 a: 长下影线 Pin Bar
        body_size = abs(last_bar['close'] - last_bar['open'])
        upper_wick = last_bar['high'] - max(last_bar['open'], last_bar['close'])
        lower_wick = min(last_bar['open'], last_bar['close']) - last_bar['low']
        body_size = max(body_size, 1e-9) # Avoid division by zero
        upper_wick = max(0, upper_wick)
        lower_wick = max(0, lower_wick)

        is_pin_bar = lower_wick > body_size * 2 and lower_wick > upper_wick * 2 and last_bar['low'] <= lower_bound
        self.logger.debug(f"{log_prefix} Pin Bar Check for Space ID {space_id}: Body={body_size:.5f}, UpperWick={upper_wick:.5f}, LowerWick={lower_wick:.5f}, LastLow<=Bound? {last_bar['low'] <= lower_bound}. IsPinBar? {is_pin_bar}")
        if is_pin_bar:
            self.logger.info(f"{log_prefix} Bullish Pin Bar detected at lower bound for Space ID {space_id}.")
            return True

        # 规则 b: 看涨吞没形态 (Bullish Engulfing)
        if len(recent_bars) >= 2:
            prev_bar = recent_bars.iloc[-2]
            # 当前K线为阳线，前一根K线为阴线
            is_curr_bullish = last_bar['close'] > last_bar['open']
            is_prev_bearish = prev_bar['close'] < prev_bar['open']
            # 当前K线实体完全吞没前一根K线实体
            engulfs_prev_body = last_bar['close'] > prev_bar['open'] and last_bar['open'] < prev_bar['close']
            # 发生在价格低位 (接近下边界)
            at_lows = last_bar['low'] <= lower_bound or prev_bar['low'] <= lower_bound
            is_bullish_engulfing = is_curr_bullish and is_prev_bearish and engulfs_prev_body and at_lows
            self.logger.debug(f"{log_prefix} Bullish Engulfing Check for Space ID {space_id}: CurrBullish? {is_curr_bullish}, PrevBearish? {is_prev_bearish}, Engulfs? {engulfs_prev_body}, AtLows? {at_lows}. IsBullishEngulfing? {is_bullish_engulfing}")
            if is_bullish_engulfing:
                self.logger.info(f"{log_prefix} Bullish Engulfing pattern detected at lower bound for Space ID {space_id}.")
                return True
        else:
            self.logger.debug(f"{log_prefix} Not enough bars for Bullish Engulfing check (need 2, have {len(recent_bars)}) for Space ID {space_id}.")

        # 规则 c: 多次尝试突破失败 (例如，连续几根K线的最低价无法显著创新低，且收盘回升)
        if len(recent_bars) >= 3:
            bars_near_lower = 0
            threshold_distance = (upper_bound - lower_bound) * 0.1 # e.g., 10% of space height
            for i in range(1, 4):
                bar_to_check = recent_bars.iloc[-i]
                if bar_to_check['low'] <= lower_bound + threshold_distance and bar_to_check['close'] > lower_bound + (threshold_distance * 0.5):
                    bars_near_lower += 1
            failed_breakouts = bars_near_lower >= 2
            self.logger.debug(f"{log_prefix} Failed Breakouts Check for Space ID {space_id}: BarsNearLower={bars_near_lower} (threshold_dist={threshold_distance:.5f}). FailedBreakouts? {failed_breakouts}")
            if failed_breakouts:
                self.logger.info(f"{log_prefix} Multiple failed breakout attempts detected at lower bound for Space ID {space_id}.")
                return True
        else:
            self.logger.debug(f"{log_prefix} Not enough bars for Failed Breakouts check (need 3, have {len(recent_bars)}) for Space ID {space_id}.")

        # (可选) 规则 d: RSI 背离
        # if 'talib' in sys.modules and len(recent_bars) >= self.rsi_period + self.rsi_divergence_lookback:
        #     # 简单底背离: 价格创新低，RSI未创新低
        #     self.logger.debug(f"{log_prefix} RSI divergence check (not fully implemented) for Space ID {space_id}.")

        self.logger.debug(f"{log_prefix} No bullish exhaustion pattern met for Space ID {space_id}.")
        return False

    # Plan Item 1.3: Remove _is_significant_wick and _is_engulfing_pattern
    # These methods are now effectively inlined and expanded within _check_bearish_exhaustion and _check_bullish_exhaustion

    def _place_order(self, symbol: str, side: OrderSide, current_bar: dict, stop_loss: float, take_profit: float, comment: str):
        """
        下单并处理相关逻辑。

        Args:
            symbol (str): 交易品种。
            side (OrderSide): 交易方向。
            current_bar (dict): 当前 K 线数据。
            stop_loss (float): 止损价格。
            take_profit (float): 止盈价格。
            comment (str): 订单注释。
        """
        try:
            current_time = current_bar.get('time')
            close_price = current_bar.get('close')
            
            # 1. 提交信号到聚合器
            action = "BUY" if side == OrderSide.BUY else "SELL"
            metadata = {
                "bar_time": current_time,
                "entry_price": close_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "comment": comment
            }
            self._submit_signal(symbol, action, current_time, confidence=0.8, metadata=metadata)
            
            # 2. 委托订单
            # 调用父类的下单方法
            super()._place_order(symbol=symbol, side=side, price=close_price, stop_loss=stop_loss, take_profit=take_profit, volume=None, comment=comment)
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}-{symbol}] Error placing order: {e}", exc_info=True)

    def _submit_signal(self, symbol: str, action: str, timestamp: pd.Timestamp, 
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
            self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] 信号聚合器已禁用，不提交信号")
            return
            
        # 检查信号聚合器是否已初始化
        if not hasattr(self, 'signal_aggregator') or self.signal_aggregator is None:
            self.logger.warning(f"[{self.strategy_name}-{self.strategy_id}] 无法提交信号，信号聚合器未初始化")
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
            self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] 信号已提交到聚合器: {symbol} {action}, 置信度={confidence:.2f}")
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}-{self.strategy_id}] 提交信号到聚合器时发生错误: {e}", exc_info=True)

    def _calculate_order_size(self, symbol: str, stop_loss_price: float) -> float:
        # 调用父类的计算方法或进行特定修改
        return super()._calculate_order_size(symbol, stop_loss_price)

# --- 可选的测试入口 ---
if __name__ == '__main__':
    import sys # 需要导入 sys
    # 设置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.info("运行 ExhaustionStrategy 测试代码...")

    # 1. 模拟配置
    mock_config = {
        'strategy_name': 'TestExhaustion',
        'strategy_params': {
            'event_importance_threshold': 2,
            'space_definition': {'forward_bars': 4, 'boundary_percentile': 90},
            'end_conditions': {'max_duration_hours': 24},
            'exhaustion_lookback': 3,
            'stop_loss_pip_buffer': 5,
            'take_profit_target': 'opposite_boundary'
        },
    }

    # 2. 模拟数据提供者 (需要能模拟衰竭形态)
    class MockDataProviderExhaustion(DataProvider):
        def get_historical_prices(self, symbol, start_time, end_time, timeframe):
            logger.debug(f"MockDataProviderExhaustion: 获取 {symbol} 从 {start_time} 到 {end_time} ({timeframe})")
            dates = pd.date_range(start=start_time, end=end_time, freq='30min', tz='UTC')
            if len(dates) < 2: dates = pd.date_range(start=start_time, periods=20, freq='30min', tz='UTC') # 保证有数据
            data = {
                'open': [1.1000 + i*0.0001 for i in range(len(dates))],
                'high': [1.1005 + i*0.00015 for i in range(len(dates))],
                'low': [1.0995 - i*0.00005 for i in range(len(dates))],
                'close': [1.1002 + i*0.00012 for i in range(len(dates))],
                'volume': [100 + i*10 for i in range(len(dates))]
            }
            df = pd.DataFrame(data, index=dates)

            # 模拟顶部衰竭 (Pin Bar)
            target_time_sell = pd.Timestamp('2023-01-01 11:30:00', tz='UTC')
            if symbol == 'EURUSD' and target_time_sell in df.index:
                 df.loc[target_time_sell, 'high'] = 1.1030 # 触及上界
                 df.loc[target_time_sell, 'open'] = 1.1015
                 df.loc[target_time_sell, 'close'] = 1.1010 # 收盘远离最高点
                 df.loc[target_time_sell, 'low'] = 1.1008

            # 模拟底部衰竭 (看涨吞没)
            target_time_buy_prev = pd.Timestamp('2023-01-01 13:00:00', tz='UTC')
            target_time_buy = pd.Timestamp('2023-01-01 13:30:00', tz='UTC')
            if symbol == 'EURUSD' and target_time_buy in df.index and target_time_buy_prev in df.index:
                 # 前一根阴线
                 df.loc[target_time_buy_prev, 'open'] = 1.0980
                 df.loc[target_time_buy_prev, 'high'] = 1.0982
                 df.loc[target_time_buy_prev, 'low'] = 1.0970 # 触及下界
                 df.loc[target_time_buy_prev, 'close'] = 1.0975
                 # 当前阳线吞没
                 df.loc[target_time_buy, 'open'] = 1.0974 # 低于前收盘
                 df.loc[target_time_buy, 'high'] = 1.0988
                 df.loc[target_time_buy, 'low'] = 1.0972
                 df.loc[target_time_buy, 'close'] = 1.0985 # 高于前开盘

            return df.loc[start_time:end_time]

        def get_calendar_events(self, start_time, end_time):
             return pd.DataFrame([
                  {'timestamp': pd.Timestamp('2023-01-01 10:00:00', tz='UTC'), 'name': 'Mock Event', 'currency': 'EUR', 'importance': 3, 'actual': '1.0'}
             ])

    # 3. 模拟执行引擎 (同上)
    class MockExecutionEngine:
        def place_order(self, order):
            logger.info(f"MockExecutionEngine: 收到订单: {order}")
            return {'status': 'FILLED', 'order_id': 'mock_456'}
        def get_position(self, symbol):
             return None

    # 4. 初始化和运行
    mock_provider = MockDataProviderExhaustion({})
    mock_engine = MockExecutionEngine()
    strategy = ExhaustionStrategy(mock_config, mock_provider, mock_engine)

    # 模拟事件触发
    event_time = pd.Timestamp('2023-01-01 10:00:00', tz='UTC')
    mock_event = {'timestamp': event_time, 'name': 'Mock Event', 'currency': 'EUR', 'importance': 3, 'actual': '1.0'}
    strategy.process_event(mock_event) # 这会定义空间边界

    # 模拟 K 线流 (需要覆盖衰竭发生的时间点)
    start_run_time = event_time + pd.Timedelta(minutes=30 * mock_config['strategy_params']['space_definition']['forward_bars'])
    end_run_time = start_run_time + pd.Timedelta(hours=5) # 模拟运行几小时
    current_time = start_run_time

    while current_time <= end_run_time:
        # 获取模拟的当前 K 线数据
        bar_df = mock_provider.get_historical_prices('EURUSD', current_time - pd.Timedelta(minutes=1), current_time, 'M30')
        if not bar_df.empty:
            current_bar_dict = bar_df.iloc[-1].to_dict()
            current_bar_dict['time'] = bar_df.index[-1]
            mock_bar_data = {'EURUSD': current_bar_dict}
            logger.info(f"\n--- Processing Bar Time: {current_bar_dict['time']} ---")
            # 打印空间信息用于调试
            if 'EURUSD' in strategy.active_spaces:
                 logger.debug(f"Active Space EURUSD: {strategy.active_spaces['EURUSD'][0]['lower_bound']:.5f} - {strategy.active_spaces['EURUSD'][0]['upper_bound']:.5f}")
            strategy.on_bar(mock_bar_data)
        else:
             logger.warning(f"无法获取 {current_time} 的模拟 K 线")
        current_time += pd.Timedelta(minutes=30)


    logger.info("测试完成。")
