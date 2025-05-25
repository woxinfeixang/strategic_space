# coding: utf-8
"""
反向穿越策略 (Reverse Crossover Strategy)

策略逻辑:
1. 继承 EventDrivenSpaceStrategy 来利用其定义的博弈空间。
2. 监控活跃的博弈空间。
3. 当价格有效收盘突破博弈空间的上边界或下边界时，视为反向穿越信号。
4. 在突破后的下一根K线或价格回撤至边界附近时，顺应突破方向入场。
5. 设置止损和止盈。

止盈止损设置方法 (根据PDF理解，需要细化):
- 止损: 设置在被突破边界的反方向一定距离 (例如，低于上边界支撑或高于下边界阻力)。
- 止盈: 可以是固定盈亏比 (例如 1:2, 1:3)，或者追踪到下一个关键阻力/支撑位，或者追踪止损。
"""

import pandas as pd
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from omegaconf import DictConfig

# 导入基础策略类和数据提供者
from .event_driven_space_strategy import EventDrivenSpaceStrategy
from strategies.core.data_providers import DataProvider # 确保导入以供类型提示
from strategies.live.sandbox import SandboxExecutionEngine # 新增导入
from strategies.risk_management.risk_manager import RiskManager # 新增导入
from .live.order import OrderSide, OrderType # <--- 修改为正确的相对导入
from strategies.utils.signal_aggregator import SignalAggregator # 导入信号聚合器

class ReverseCrossoverStrategy(EventDrivenSpaceStrategy):
    """
    反向穿越策略，继承自事件驱动空间策略。
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
        初始化反向穿越策略。
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
        self.strategy_name = "ReverseCrossoverStrategy"
        # self.logger is initialized in StrategyBase
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Initializing ReverseCrossoverStrategy...")

        # 策略特定参数 (可以从 config 中读取)
        # self.params 是在 StrategyBase 中通过 app_config 初始化好的
        # 尝试从特定的配置路径获取参数
        strategy_params = app_config.get('strategy_params', {})
        rcs_params = strategy_params.get('ReverseCrossoverStrategy', {})
        
        # 打印调试信息
        self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] app_config type: {type(app_config)}")
        self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] app_config.strategy_params exists: {hasattr(app_config, 'strategy_params')}")
        self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] strategy_params from app_config: {strategy_params}")
        self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] rcs_params from strategy_params: {rcs_params}")
        
        # 优先从strategy_params中获取，然后从self.params中获取
        entry_retrace_from_strat_params = None
        if hasattr(rcs_params, 'entry_on_retrace'):
            entry_retrace_from_strat_params = rcs_params.entry_on_retrace
            self.logger.debug(f"[{self.strategy_name}-{self.strategy_id}] Found entry_on_retrace in strategy_params.ReverseCrossoverStrategy: {entry_retrace_from_strat_params}")
            
        self.entry_on_retrace = entry_retrace_from_strat_params if entry_retrace_from_strat_params is not None else self.params.get('entry_on_retrace', False)
        self.stop_loss_factor = self.params.get('stop_loss_factor', 0.5) # For non-retrace SL
        self.take_profit_ratio = self.params.get('take_profit_ratio', 2.0) # General TP ratio

        # New parameters for retrace logic - Plan Item 1.1
        self.retrace_entry_buffer_pips = self.params.get('retrace_entry_buffer_pips', 1.0)
        self.retrace_max_wait_bars = self.params.get('retrace_max_wait_bars', 5)
        self.retrace_sl_use_entry_bar_extremum = self.params.get('retrace_sl_use_entry_bar_extremum', True)
        self.retrace_sl_extremum_buffer_pips = self.params.get('retrace_sl_extremum_buffer_pips', 2.0)
        
        # 初始化信号聚合器（如果父类未初始化）
        if not hasattr(super(), 'signal_aggregator') or super().signal_aggregator is None:
            self.signal_aggregator = SignalAggregator(self.logger, self.params.get('signal_aggregator_config', {}))
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 初始化信号聚合器")
        else:
            self.signal_aggregator = super().signal_aggregator
            self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] 使用父类信号聚合器")
            
        # 信号聚合器控制参数
        self.use_signal_aggregator = self.params.get('use_signal_aggregator', True)

        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Initialized with entry_on_retrace: {self.entry_on_retrace}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Retrace params: entry_buffer_pips={self.retrace_entry_buffer_pips}, max_wait_bars={self.retrace_max_wait_bars}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Retrace SL params: use_entry_bar_extremum={self.retrace_sl_use_entry_bar_extremum}, extremum_buffer_pips={self.retrace_sl_extremum_buffer_pips}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] General SL/TP params: stop_loss_factor (for non-retrace)={self.stop_loss_factor}, take_profit_ratio={self.take_profit_ratio}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] Signal Aggregator enabled: {self.use_signal_aggregator}")
        self.logger.info(f"[{self.strategy_name}-{self.strategy_id}] ReverseCrossoverStrategy Initialization complete.")

    def _execute_trading_logic(self, symbol: str, current_bar: dict, space_info: dict, all_symbol_spaces: list):
        """
        执行反向穿越的交易逻辑。
        """
        current_time = current_bar['time']
        close_price = current_bar['close']
        space_id = space_info.get('id', 'N/A')
        log_prefix = f"[{self.strategy_name}-{symbol}-{current_time}-SpaceID:{space_id}]"
        self.logger.debug(f"{log_prefix} Executing trading logic. Bar: O={current_bar['open']:.5f} H={current_bar['high']:.5f} L={current_bar['low']:.5f} C={close_price:.5f} @ {current_time}, Space Event: {space_info.get('event_name', 'N/A')}")
        
        # high_price = current_bar['high'] # 未在此简化逻辑中使用
        # low_price = current_bar['low']   # 未在此简化逻辑中使用
        
        # Plan Item 2.1: Unify boundary key names
        # upper_bound = space_info['upper_bound']
        # lower_bound = space_info['lower_bound']
        upper_bound = space_info.get('high') # Use .get() for safety, though 'high' should exist from P0
        lower_bound = space_info.get('low')  # Use .get() for safety, though 'low' should exist from P0

        if upper_bound is None or lower_bound is None:
            self.logger.warning(f"{log_prefix} Missing 'high' or 'low' bounds in space_info. Skipping logic. Space Info: {space_info}")
            return
            
        space_height = upper_bound - lower_bound
        if space_height <= 0: # Basic check for valid space height
            self.logger.warning(f"{log_prefix} Invalid space height {space_height:.5f} (Upper: {upper_bound:.5f}, Lower: {lower_bound:.5f}). Skipping logic.")
            return
        self.logger.debug(f"{log_prefix} Space bounds: Upper={upper_bound:.5f}, Lower={lower_bound:.5f}, Height={space_height:.5f}")

        event_name = space_info.get('event_name', space_info.get('event_title', 'N/A')) # Try 'event_title' as fallback

        position = self.positions.get(symbol, {'volume': 0.0})
        self.logger.debug(f"{log_prefix} Current position for {symbol}: Volume={position.get('volume', 0.0)}, EntryPrice={position.get('entry_price', 0.0)}")

        # Plan Item 2.2 & 2.3 & 2.4: Main logic adjustment for retrace
        if position['volume'] == 0: # 只有在没有持仓时才考虑入场
            self.logger.debug(f"{log_prefix} No active position. Checking for entry signals.")
            current_rc_status = space_info.get('rc_status')
            pip_size = self._get_pip_size(symbol) # Get pip_size for buffer calculations
            if pip_size is None: # Fallback if pip_size is not found, though it should be
                self.logger.warning(f"{log_prefix} Pip size not found for {symbol}, using default for retrace buffer. This may be incorrect.")
                pip_size = 0.0001 if "JPY" not in symbol.upper() else 0.01
            self.logger.debug(f"{log_prefix} Pip size: {pip_size}, Current rc_status: {current_rc_status}")

            # --- Plan Item 2.3: Handle existing PENDING_RETRACE states --- 
            if current_rc_status == 'PENDING_RETRACE_BUY':
                self.logger.info(f"{log_prefix} Handling PENDING_RETRACE_BUY.")
                space_info['rc_bars_waited'] = space_info.get('rc_bars_waited', 0) + 1
                target_retrace_level = space_info.get('rc_target_retrace_level', upper_bound) # Default to upper_bound if missing
                breakout_bar_time = space_info.get('rc_breakout_bar_time')
                self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY: bars_waited={space_info['rc_bars_waited']}, target_retrace_level={target_retrace_level:.5f}, breakout_bar_time={breakout_bar_time}")

                # 2.3.1.1. Timeout Check
                if space_info['rc_bars_waited'] > self.retrace_max_wait_bars:
                    self.logger.info(f"{log_prefix} PENDING_RETRACE_BUY timed out after {space_info['rc_bars_waited']} bars (max: {self.retrace_max_wait_bars}). Clearing status.")
                    space_info.pop('rc_status', None)
                    space_info.pop('rc_target_retrace_level', None)
                    space_info.pop('rc_breakout_bar_time', None)
                    space_info.pop('rc_bars_waited', None)
                    current_rc_status = None # Allow fresh breakout detection below
                else:
                    # 2.3.1.2. Retrace Entry Check
                    effective_retrace_buy_target = target_retrace_level + self.retrace_entry_buffer_pips * pip_size
                    self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY: Checking entry. Bar low {current_bar['low']:.5f} vs effective_target {effective_retrace_buy_target:.5f} (target {target_retrace_level:.5f} + buffer {self.retrace_entry_buffer_pips * pip_size:.5f}) (pip_size={pip_size})")
                    if current_bar['low'] <= effective_retrace_buy_target:
                        self.logger.info(f"{log_prefix} PENDING_RETRACE_BUY confirmed. Bar low {current_bar['low']:.5f} <= target {effective_retrace_buy_target:.5f}.")
                        # 2.3.1.3. Calculate SL/TP
                        sl_price = 0.0
                        if self.retrace_sl_use_entry_bar_extremum:
                            sl_price = current_bar['low'] - self.retrace_sl_extremum_buffer_pips * pip_size
                            self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY: SL using entry bar extremum: {sl_price:.5f} (bar_low {current_bar['low']:.5f} - buffer {self.retrace_sl_extremum_buffer_pips * pip_size:.5f}) (pip_size={pip_size})")
                        else:
                            sl_price = target_retrace_level - space_height * self.stop_loss_factor # Original breakout boundary based SL
                            self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY: SL using original boundary: {sl_price:.5f} (target_retrace {target_retrace_level:.5f} - space_height {space_height:.5f} * factor {self.stop_loss_factor})")
                        
                        # Ensure SL is meaningful (e.g., not above entry for a buy)
                        sl_price = min(sl_price, current_bar['close'] - pip_size) # Basic sanity check
                        self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY: Adjusted SL after sanity check: {sl_price:.5f}")

                        tp_price = current_bar['close'] + (current_bar['close'] - sl_price) * self.take_profit_ratio
                        self.logger.info(f"{log_prefix} PENDING_RETRACE_BUY: Placing BUY order. Entry ~{current_bar['close']:.5f}, SL={sl_price:.5f}, TP={tp_price:.5f}")
                        
                        # 提交信号到聚合器
                        self._submit_signal(symbol, "BUY", current_time, 0.9, {
                            "signal_type": "RETRACE_BUY", 
                            "space_id": space_id,
                            "target_level": target_retrace_level,
                            "entry_price": current_bar['close'],
                            "stop_loss": sl_price,
                            "take_profit": tp_price
                        })
                        
                        self._place_order(symbol, OrderSide.BUY, current_bar, sl_price, tp_price, f"RC_RetraceBuy_{event_name[:10]}")
                        space_info['rc_status'] = 'RETRACE_BUY_ORDERED' # Update status
                        self.logger.info(f"{log_prefix} Status updated to RETRACE_BUY_ORDERED.")
                        return # Exit after placing order
                    else: # No retrace yet, continue waiting
                       self.logger.debug(f"{log_prefix} PENDING_RETRACE_BUY - Bar low {current_bar['low']:.5f} > target {effective_retrace_buy_target:.5f}. Waiting. ({space_info['rc_bars_waited']}/{self.retrace_max_wait_bars}) bars.")
            
            elif current_rc_status == 'PENDING_RETRACE_SELL':
                self.logger.info(f"{log_prefix} Handling PENDING_RETRACE_SELL.")
                space_info['rc_bars_waited'] = space_info.get('rc_bars_waited', 0) + 1
                target_retrace_level = space_info.get('rc_target_retrace_level', lower_bound)
                breakout_bar_time = space_info.get('rc_breakout_bar_time')
                self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL: bars_waited={space_info['rc_bars_waited']}, target_retrace_level={target_retrace_level:.5f}, breakout_bar_time={breakout_bar_time}")

                if space_info['rc_bars_waited'] > self.retrace_max_wait_bars:
                    self.logger.info(f"{log_prefix} PENDING_RETRACE_SELL timed out after {space_info['rc_bars_waited']} bars (max: {self.retrace_max_wait_bars}). Clearing status.")
                    space_info.pop('rc_status', None)
                    space_info.pop('rc_target_retrace_level', None)
                    space_info.pop('rc_breakout_bar_time', None)
                    space_info.pop('rc_bars_waited', None)
                    current_rc_status = None
                else:
                    effective_retrace_sell_target = target_retrace_level - self.retrace_entry_buffer_pips * pip_size
                    self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL: Checking entry. Bar high {current_bar['high']:.5f} vs effective_target {effective_retrace_sell_target:.5f} (target {target_retrace_level:.5f} - buffer {self.retrace_entry_buffer_pips * pip_size:.5f}) (pip_size={pip_size})")
                    if current_bar['high'] >= effective_retrace_sell_target:
                        self.logger.info(f"{log_prefix} PENDING_RETRACE_SELL confirmed. Bar high {current_bar['high']:.5f} >= target {effective_retrace_sell_target:.5f}.")
                        sl_price = 0.0
                        if self.retrace_sl_use_entry_bar_extremum:
                            sl_price = current_bar['high'] + self.retrace_sl_extremum_buffer_pips * pip_size
                            self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL: SL using entry bar extremum: {sl_price:.5f} (bar_high {current_bar['high']:.5f} + buffer {self.retrace_sl_extremum_buffer_pips * pip_size:.5f}) (pip_size={pip_size})")
                        else:
                            sl_price = target_retrace_level + space_height * self.stop_loss_factor
                            self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL: SL using original boundary: {sl_price:.5f} (target_retrace {target_retrace_level:.5f} + space_height {space_height:.5f} * factor {self.stop_loss_factor})")
                        
                        sl_price = max(sl_price, current_bar['close'] + pip_size) # Basic sanity check
                        self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL: Adjusted SL after sanity check: {sl_price:.5f}")

                        tp_price = current_bar['close'] - (sl_price - current_bar['close']) * self.take_profit_ratio
                        self.logger.info(f"{log_prefix} PENDING_RETRACE_SELL: Placing SELL order. Entry ~{current_bar['close']:.5f}, SL={sl_price:.5f}, TP={tp_price:.5f}")
                        self._place_order(symbol, OrderSide.SELL, current_bar, sl_price, tp_price, f"RC_RetraceSell_{event_name[:10]}")
                        space_info['rc_status'] = 'RETRACE_SELL_ORDERED'
                        self.logger.info(f"{log_prefix} Status updated to RETRACE_SELL_ORDERED.")
                        return
                    else:
                        self.logger.debug(f"{log_prefix} PENDING_RETRACE_SELL - Bar high {current_bar['high']:.5f} < target {effective_retrace_sell_target:.5f}. Waiting. ({space_info['rc_bars_waited']}/{self.retrace_max_wait_bars}) bars.")
            
            # --- Plan Item 2.2: Detect new breakouts if not already handling a PENDING_RETRACE --- 
            # (Only if current_rc_status is None or not one of the PENDING states, which is implicitly handled by the 'if/elif' for PENDING states above)
            if current_rc_status not in ['PENDING_RETRACE_BUY', 'PENDING_RETRACE_SELL', 'RETRACE_BUY_ORDERED', 'RETRACE_SELL_ORDERED']:
                self.logger.debug(f"{log_prefix} No PENDING_RETRACE or ORDERED status. Checking for new breakouts.")
                # 向上突破 (Buy Signal)
                if close_price > upper_bound:
                    self.logger.info(f"{log_prefix} Breakout above upper_bound {upper_bound:.5f} detected at close price {close_price:.5f}.")
                    if self.entry_on_retrace:
                        self.logger.info(f"{log_prefix} entry_on_retrace is True. Setting PENDING_RETRACE_BUY.")
                        space_info['rc_status'] = 'PENDING_RETRACE_BUY'
                        space_info['rc_target_retrace_level'] = upper_bound
                        space_info['rc_breakout_bar_time'] = current_time
                        space_info['rc_bars_waited'] = 0
                        self.logger.info(f"{log_prefix} Status set to PENDING_RETRACE_BUY. Target: {upper_bound:.5f}, Breakout time: {current_time}")
                    else: # 即时入场
                        self.logger.info(f"{log_prefix} entry_on_retrace is False. Placing immediate BUY order.")
                        stop_loss_price = upper_bound - space_height * self.stop_loss_factor
                        # Ensure SL is meaningful
                        stop_loss_price = min(stop_loss_price, close_price - pip_size)
                        take_profit_price = close_price + (close_price - stop_loss_price) * self.take_profit_ratio
                        self.logger.info(f"{log_prefix} Immediate BUY: Entry ~{close_price:.5f}, SL={stop_loss_price:.5f}, TP={take_profit_price:.5f}")
                        self._place_order(symbol, OrderSide.BUY, current_bar, stop_loss_price, take_profit_price, f"RC_Buy_{event_name[:10]}")
                        space_info['rc_status'] = 'IMMEDIATE_BUY_ORDERED' # Update status
                        self.logger.info(f"{log_prefix} Status updated to IMMEDIATE_BUY_ORDERED.")
                    return # Exit after processing breakout

                # 向下突破 (Sell Signal)
                elif close_price < lower_bound:
                    self.logger.info(f"{log_prefix} Breakout below lower_bound {lower_bound:.5f} detected at close price {close_price:.5f}.")
                    if self.entry_on_retrace:
                        self.logger.info(f"{log_prefix} entry_on_retrace is True. Setting PENDING_RETRACE_SELL.")
                        space_info['rc_status'] = 'PENDING_RETRACE_SELL'
                        space_info['rc_target_retrace_level'] = lower_bound
                        space_info['rc_breakout_bar_time'] = current_time
                        space_info['rc_bars_waited'] = 0
                        self.logger.info(f"{log_prefix} Status set to PENDING_RETRACE_SELL. Target: {lower_bound:.5f}, Breakout time: {current_time}")
                    else: # 即时入场
                        self.logger.info(f"{log_prefix} entry_on_retrace is False. Placing immediate SELL order.")
                        stop_loss_price = lower_bound + space_height * self.stop_loss_factor
                        # Ensure SL is meaningful
                        stop_loss_price = max(stop_loss_price, close_price + pip_size)
                        take_profit_price = close_price - (stop_loss_price - close_price) * self.take_profit_ratio
                        self.logger.info(f"{log_prefix} Immediate SELL: Entry ~{close_price:.5f}, SL={stop_loss_price:.5f}, TP={take_profit_price:.5f}")
                        self._place_order(symbol, OrderSide.SELL, current_bar, stop_loss_price, take_profit_price, f"RC_Sell_{event_name[:10]}")
                        space_info['rc_status'] = 'IMMEDIATE_SELL_ORDERED' # Update status
                        self.logger.info(f"{log_prefix} Status updated to IMMEDIATE_SELL_ORDERED.")
                    return # Exit after processing breakout
                else:
                    self.logger.debug(f"{log_prefix} No new breakout. Price {close_price:.5f} is within bounds [{lower_bound:.5f}, {upper_bound:.5f}].")
            else:
                self.logger.debug(f"{log_prefix} Current rc_status is {current_rc_status}. No new breakout check needed this bar.")
        else:
            self.logger.debug(f"{log_prefix} Active position exists (Volume: {position['volume']}). Skipping entry logic.")
        self.logger.debug(f"{log_prefix} Finished trading logic execution for this bar.")

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
        if not hasattr(self, 'signal_aggregator') or not self.signal_aggregator:
            self.logger.warning(f"[{self.strategy_name}-{self.strategy_id}] 无法提交信号到信号聚合器，聚合器实例未找到")
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

    def _place_order(self, symbol: str, side: OrderSide, current_bar: dict, stop_loss: float, take_profit: float, comment: str):
        """
        下单逻辑。
        """
        try:
            # 创建 Order 对象
            # order = Order(
            #     symbol=symbol,
            #     type=OrderType.MARKET,  # 市价单
            #     side=side,
            #     volume=self._calculate_order_size(symbol, stop_loss),
            #     price=current_bar['close'],  # 当前K线收盘价
            #     stop_loss=stop_loss,
            #     take_profit=take_profit,
            #     comment=comment,
            #     # ... 其他必要字段 ...
            # )

            # 使用 StrategyBase 的 place_order_from_signal 方法
        signal_data = {
                'order_type': OrderType.MARKET, 
            'symbol': symbol,
                'side': side,
                'entry_price': current_bar['close'],
            'stop_loss': stop_loss,
            'take_profit': take_profit,
                'order_comment': comment
            }
            
            # 通过执行引擎下单
            self.place_order_from_signal(signal_data)
            self.logger.info(f"Order placed for {symbol}. Side: {side}, Price: {current_bar['close']}, SL: {stop_loss}, TP: {take_profit}, Comment: {comment}")
            
        except Exception as e:
            self.logger.error(f"下单失败: {e}", exc_info=True)


# --- 可选的测试入口 --- (如果需要，可以添加或更新测试代码)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.info("运行 ReverseCrossoverStrategy 测试代码 (占位符)...")

    # 此处可以添加类似其他策略的 mock 对象和测试场景
    # 由于该策略依赖于 EventDrivenSpaceStrategy 定义的空间，
    # 测试时需要 mock EventDrivenSpaceStrategy 的行为或提供 active_spaces。

    # 示例：假设我们有一个 mock 的 ReverseCrossoverStrategy 实例
    # mock_config = OmegaConf.create({
    #     'strategy_params': {
    #         'entry_on_retrace': False,
    #         'stop_loss_factor': 0.5,
    #         'take_profit_ratio': 2.0
    #     },
    #     # ... 其他必要的模拟配置项 ...
    # })
    # mock_dp = None # 模拟 DataProvider
    # mock_ee = None # 模拟 ExecutionEngine
    # mock_rm = None # 模拟 RiskManager
    # strategy_instance = ReverseCrossoverStrategy(
    #     strategy_id="MockRCS", 
    #     app_config=mock_config, 
    #     data_provider=mock_dp, 
    #     execution_engine=mock_ee, 
    #     risk_manager=mock_rm, 
    #     live_mode=False
    # )

    # 模拟 current_bar 和 space_info
    # mock_current_bar = {
    #     'time': pd.Timestamp.now(tz='UTC'),
    #     'open': 1.1000,
    #     'high': 1.1050,
    #     'low': 1.0990,
    #     'close': 1.1045 # 假设突破上边界
    # }
    # mock_space_info = {
    #     'upper_bound': 1.1040,
    #     'lower_bound': 1.1000,
    #     'event_name': 'TestEvent'
    # }

    # strategy_instance._execute_trading_logic(
    #     symbol='EURUSD',
    #     current_bar=mock_current_bar,
    #     space_info=mock_space_info,
    #     all_symbol_spaces=[mock_space_info]
    # )

    logger.info("ReverseCrossoverStrategy 测试代码 (占位符) 执行完毕。")
