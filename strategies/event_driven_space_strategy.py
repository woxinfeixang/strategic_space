# coding: utf-8
import logging
import os
import re
import pandas as pd
import pytz
import yaml
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

from omegaconf import DictConfig, OmegaConf

from strategies.core.strategy_base import StrategyBase
from strategies.config import DEFAULT_CONFIG # 导入默认配置
# The following imports are presumed safe as they were fine in engine.py individually
# and are expected by StrategyBase or its typical usage pattern.
from strategies.core.data_providers import DataProvider
from strategies.live.execution_engine import ExecutionEngineBase as ExecutionEngine # Renamed for consistency
from strategies.risk_management.risk_manager import RiskManager
# 导入信号聚合器
from strategies.utils.signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)

class EventDrivenSpaceStrategy(StrategyBase):
    """
    事件驱动的空间策略基类，统一处理事件映射、参数加载和核心事件处理逻辑。
    """
    _is_abstract = True # ADDED

    def __init__(self, 
                 strategy_id: str, 
                 app_config: DictConfig, 
                 data_provider: Any, # ADDED
                 execution_engine: Any, # ADDED
                 risk_manager: Any, # ADDED
                 live_mode: bool = False):
        # MODIFIED: Pass all required arguments to StrategyBase.__init__
        super().__init__(
            strategy_id=strategy_id, 
            app_config=app_config, 
            data_provider=data_provider,
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            live_mode=live_mode
        )
        
        self.strategy_name = "EventDrivenSpaceStrategy_MD_Compliant" # Changed name for clarity
        self.logger = logging.getLogger(self.strategy_name)
        
        self.primary_timeframe = self.params.get('primary_timeframe', 'M30')
        # active_spaces: Dict[symbol, List[space_info_dict]]
        # space_info_dict will store all details about a space, including its state for expiry conditions
        self.active_spaces: Dict[str, List[Dict]] = {}
        
        # Parameters for space invalidation (can be moved to config / self.params)
        # self.space_invalidate_strong_breakout_multiplier = self.params.get('space_invalidate_strong_breakout_multiplier', 2.0) # Commented out, to be reviewed
        # self.space_invalidate_boundary_touch_buffer_pips = self.params.get('space_invalidate_boundary_touch_buffer_pips', 5) # Commented out, to be reviewed
        # self.space_invalidate_boundary_oscillation_count = self.params.get('space_invalidate_boundary_oscillation_count', 3) # Commented out, potentially replaced by self.oscillation_M_times

        # Parameters for space invalidation from checklist 1.1
        self.strong_breakout_N_bars = self.config.get("event_driven_strategy.invalidation.strong_breakout_N_bars", 3)
        self.oscillation_M_times = self.config.get("event_driven_strategy.invalidation.oscillation_M_times", 5)
        self.retrace_confirmation_buffer_ratio = self.config.get("event_driven_strategy.invalidation.retrace_confirmation_buffer_ratio", 0.25)

        # Logging the loaded invalidation parameters
        self.logger.info(f"Invalidation params: strong_breakout_N_bars={self.strong_breakout_N_bars}, oscillation_M_times={self.oscillation_M_times}, retrace_confirmation_buffer_ratio={self.retrace_confirmation_buffer_ratio}")

        self.logger.info(f"Initialized: {self.strategy_name} with primary timeframe {self.primary_timeframe}. Event mapping and pip size need proper setup.")

        # Load event mapping rules from YAML file
        self.event_mapping_rules: List[Dict] = []
        try:
            # self.config 是传递给 StrategyBase 的完整 OmegaConf 对象，即 app_config
            # event_mapping.yaml 的内容应该被合并到 app_config.event_mapping 路径下
            event_mapping_node = OmegaConf.select(self.config, 'event_mapping') # self.config 就是 merged_config
            if event_mapping_node and OmegaConf.select(event_mapping_node, 'event_mappings'):
                rules_from_config = OmegaConf.to_container(event_mapping_node.event_mappings, resolve=True)
                if isinstance(rules_from_config, list):
                    self.event_mapping_rules = rules_from_config
                    self.logger.info(f"Successfully loaded {len(self.event_mapping_rules)} event mapping rules from merged configuration (event_mapping.event_mappings).")
                else:
                    self.logger.error(f"Content under 'event_mapping.event_mappings' in config is not a list, but {type(rules_from_config)}.")
            else:
                self.logger.error("CRITICAL: Event mapping rules not found in merged configuration under 'event_mapping.event_mappings'. Strategy cannot map events to symbols.")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while loading event mapping rules from merged configuration: {e}", exc_info=True)


        # Parameters from config
        self.space_duration_minutes = self.config.get("event_driven_strategy.space_definition.space_duration_minutes", 60)
        self.space_breakout_buffer_pips = self.config.get("event_driven_strategy.space_definition.space_breakout_buffer_pips", 1.0)
        self.max_active_spaces_per_event = self.config.get("event_driven_strategy.trade_management.max_active_spaces_per_event", 1)
        self.allow_multiple_trades_per_event = self.config.get("event_driven_strategy.trade_management.allow_multiple_trades_per_event", False)
        self.stop_loss_pips = self.config.get("event_driven_strategy.risk_management.stop_loss_pips", 20)
        self.take_profit_pips = self.config.get("event_driven_strategy.risk_management.take_profit_pips", 40)
        self.trailing_stop_pips = self.config.get("event_driven_strategy.risk_management.trailing_stop_pips", 0) # 0 means disabled
        self.trade_expiration_minutes = self.config.get("event_driven_strategy.trade_management.trade_expiration_minutes", 240)
        self.min_space_height_pips = self.config.get("event_driven_strategy.space_definition.min_space_height_pips", 5.0)
        self.news_lookback_minutes = self.config.get("event_driven_strategy.news_filter.news_lookback_minutes", 15)
        self.min_event_impact = self.config.get("event_driven_strategy.news_filter.min_event_impact", 2) # 0=low, 1=medium, 2=high
        self.allowed_event_currencies = self.config.get("event_driven_strategy.news_filter.allowed_event_currencies", ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"])
        self.trading_sessions = self.config.get("event_driven_strategy.trading_hours.sessions", {"london": ["07:00", "16:00"], "new_york": ["12:00", "21:00"]})
        self.trade_on_session_overlap_only = self.config.get("event_driven_strategy.trading_hours.trade_on_session_overlap_only", False)
        self.boundary_touch_buffer_value_percentage = self.config.get("event_driven_strategy.space_definition.boundary_touch_buffer_value_percentage", 0.05) # 5% buffer

        self.position_sizing_method = self.config.get("event_driven_strategy.risk_management.position_sizing.method", "fixed_lot") # fixed_lot, risk_percentage
        self.fixed_lot_size = self.config.get("event_driven_strategy.risk_management.position_sizing.fixed_lot_size", 0.01)
        self.risk_percentage_per_trade = self.config.get("event_driven_strategy.risk_management.position_sizing.risk_percentage_per_trade", 1.0) # 1% of account balance

        # 初始化信号聚合器
        self._initialize_signal_aggregator()

        logger.info(f"EventDrivenSpaceStrategy initialized with ID: {self.strategy_id}")
        logger.info(f"Space duration: {self.space_duration_minutes} mins, SL: {self.stop_loss_pips} pips, TP: {self.take_profit_pips} pips")
        logger.info(f"Min event impact: {self.min_event_impact}, Allowed currencies: {self.allowed_event_currencies}")
        if not self.event_mapping_rules:
            logger.warning(f"Strategy {self.strategy_id}: Event mapping rules are empty or failed to load. Event-to-symbol mapping will not function.")
        
        # 日志记录信号聚合器是否启用
        logger.info(f"Signal Aggregator enabled: {self.use_signal_aggregator}, Resonance threshold: {self.signal_aggregator_config.get('resonance_threshold', 2.0) if self.signal_aggregator_config else 'N/A'}")

    def _initialize_signal_aggregator(self):
        """
        初始化信号聚合器，加载配置参数
        """
        # 从配置中获取信号聚合器参数
        self.use_signal_aggregator = self.params.get('use_signal_aggregator', True)
        
        if self.use_signal_aggregator:
            # 加载信号聚合器配置
            self.signal_aggregator_config = {
                "strategy_weights": {
                    "EventDrivenSpaceStrategy": 1.0,
                    "ReverseCrossoverStrategy": 0.8,
                    "ExhaustionStrategy": 0.8,
                    "KeyTimeWeightTurningPointStrategy": 1.0,
                    "SpaceTimeResonanceStrategy": 1.0
                },
                "default_strategy_weight": 0.7,
                "resonance_time_window_minutes": 120,
                "resonance_threshold": 2.0
            }
            
            # 创建信号聚合器实例
            self.signal_aggregator = SignalAggregator(self.logger, self.signal_aggregator_config)
            self.logger.info("Signal Aggregator initialized successfully.")
        else:
            self.signal_aggregator = None
            self.logger.info("Signal Aggregator disabled in configuration.")

    def _parse_actual_value(self, actual_str: Optional[str]) -> float:
        # This function might be deprecated if 'Actual' is not used for bounds anymore.
        # Keeping it for now in case other parts of a larger system use it or if 'Actual' has other meanings.
        if actual_str is None:
            return 0.0
        try:
            # 移除可能的空白字符
            actual_str = str(actual_str).strip()
            if not actual_str:
                return 0.0

            if '%' in actual_str:
                return float(actual_str.replace('%', '')) / 100.0
            elif 'K' in actual_str.upper():
                return float(actual_str.upper().replace('K', '')) * 1000.0
            elif 'M' in actual_str.upper():
                return float(actual_str.upper().replace('M', '')) * 1000000.0
            return float(actual_str)
        except ValueError:
            self.logger.warning(f"Could not parse 'Actual' value: {actual_str}. Returning 0.0")
            return 0.0

    def process_new_data(self, current_time: pd.Timestamp, market_data: Dict[str, Dict[str, pd.DataFrame]], latest_events: Optional[pd.DataFrame]):
        """
        Handles new market data (bars) and new event data.
        This method is typically called by the backtesting/live trading framework.
        """
        current_processing_time = pd.Timestamp.now(tz='UTC') # Internal processing timestamp
        self.logger.debug(f"[{self.strategy_id}] process_new_data ENTRY. Framework time: {current_time}, Processing time: {current_processing_time}. Events: {'Yes' if latest_events is not None and not latest_events.empty else 'No'}")

        # Plan Item 2.4 (was 5.2.1): Ensure current_time is UTC (already present)
        if current_time.tzinfo is None:
            self.logger.debug(f"Framework current_time (input: {current_time}) is naive. Assuming UTC and localizing.")
            current_time = current_time.tz_localize('UTC')
        elif str(current_time.tzinfo).upper() != 'UTC' and current_time.tzinfo != pytz.UTC: # Added pytz.UTC check
            self.logger.debug(f"Framework current_time (input: {current_time}, tz: {current_time.tzinfo}) is not UTC. Converting to UTC.")
            current_time = current_time.tz_convert('UTC')
        else:
            self.logger.debug(f"Framework current_time (input: {current_time}) is already UTC.")

        # 1. 处理新事件，更新博弈空间
        if latest_events is not None and not latest_events.empty:
            # Pass market_data to _process_events for boundary calculation
            self.logger.debug(f"[{self.strategy_id}] Calling _process_events for {len(latest_events)} events.")
            self._process_events(latest_events, market_data, current_time) 

        # 2. 处理每个品种的K线数据，并检查空间失效条件
        self.logger.debug(f"[{self.strategy_id}] Iterating market_data for bar processing. Symbols: {list(market_data.keys())}")
        for symbol, symbol_market_data in market_data.items():
            if not symbol_market_data or self.primary_timeframe not in symbol_market_data:
                self.logger.debug(f"[{self.strategy_name}-{symbol}] No market data for primary timeframe {self.primary_timeframe} at {current_time}")
                continue
            
            primary_tf_data = symbol_market_data[self.primary_timeframe]
            if primary_tf_data.empty:
                self.logger.debug(f"[{self.strategy_name}-{symbol}] Primary timeframe {self.primary_timeframe} data is empty at {current_time}")
                continue

            # Plan Item 2.5 (was 5.2.2): Ensure primary_tf_data.index is UTC
            if primary_tf_data.index.tzinfo is None:
                self.logger.debug(f"Primary TF data index for symbol {symbol} is naive. Assuming UTC and localizing.")
                primary_tf_data.index = primary_tf_data.index.tz_localize('UTC')
            elif str(primary_tf_data.index.tzinfo).upper() != 'UTC':
                 self.logger.debug(f"Primary TF data index for symbol {symbol} is not UTC ({primary_tf_data.index.tzinfo}). Converting to UTC.")
                 primary_tf_data.index = primary_tf_data.index.tz_convert('UTC')
            # else: # No need for an else log here, can be verbose
                # self.logger.debug(f"Primary TF data index for symbol {symbol} is already UTC.")


            # Get the current bar based on current_time
            # Ensure current_bar_series is correctly identified for current_time
            if current_time in primary_tf_data.index:
                current_bar_series = primary_tf_data.loc[current_time]
            elif not primary_tf_data.empty and current_time > primary_tf_data.index[-1]:
                 # If current_time is beyond the last data point, use the last available bar.
                 # This might happen in live trading if current_time is slightly ahead of bar close,
                 # or if data feed has a slight lag for the very latest bar.
                current_bar_series = primary_tf_data.iloc[-1]
                # self.logger.debug(f"[{self.strategy_name}-{symbol}] Current time {current_time} is after last bar {primary_tf_data.index[-1]}. Using last bar.")
            elif not primary_tf_data.empty:
                # Fallback: find nearest past bar if current_time is not an exact match (e.g., inter-bar time)
                # This ensures we are processing based on most recent *closed* information relative to current_time
                try:
                    idx_loc = primary_tf_data.index.get_loc(current_time, method='ffill')
                    current_bar_series = primary_tf_data.iloc[idx_loc]
                except KeyError:
                    self.logger.warning(f"[{self.strategy_name}-{symbol}] Failed to find any bar for time {current_time} in primary_tf_data index. Skipping.")
                    continue
            else:
                self.logger.warning(f"[{self.strategy_name}-{symbol}] Unexpected state: primary_tf_data is not empty but no usable bar found. Skipping.")
                continue

            # Convert current_bar_series to DataFrame for consistency in methods expecting DataFrame
            current_bar_df = pd.DataFrame([current_bar_series])
            current_bar_df.index = [current_time if hasattr(current_bar_series, 'name') and pd.isna(current_bar_series.name) else current_bar_series.name]
            
            # Now process the bar - checks invalidation, does trading decisions
            self.logger.debug(f"[{self.strategy_id}] _process_bar for {symbol} at {current_time}. Bar info: {current_bar_df}")
            self._process_bar(symbol, current_bar_df, current_time, primary_tf_data)
            
        # 3. 检查跨策略信号共振
        if self.use_signal_aggregator and self.signal_aggregator:
            resonant_signals = self.signal_aggregator.check_resonance(current_time)
            if resonant_signals:
                self._handle_resonance_signals(resonant_signals, current_time)
            
            # 定期清理旧信号（每天一次）
            if hasattr(self, 'last_signal_cleanup') and (current_time - self.last_signal_cleanup).total_seconds() > 86400:
                self.signal_aggregator.clean_old_signals()
                self.last_signal_cleanup = current_time
            elif not hasattr(self, 'last_signal_cleanup'):
                self.last_signal_cleanup = current_time

    def _handle_resonance_signals(self, resonant_signals: Dict[str, Dict[str, Any]], current_time: pd.Timestamp):
        """
        处理共振信号，强化交易决策
        
        Args:
            resonant_signals: 共振信号字典，格式: {symbol: {'action': 'BUY'/'SELL', 'weight': float, 'strategies': list}}
            current_time: 当前处理时间
        """
        for symbol, signal_info in resonant_signals.items():
            action = signal_info['action']
            weight = signal_info['weight']
            strategies = signal_info['strategies']
            
            self.logger.info(f"[共振信号处理] {symbol} {action} 权重={weight:.2f} 策略={', '.join(strategies)}")
            
            # 根据共振信号执行交易逻辑
            # 1. 检查是否有该品种的活动空间
            if symbol in self.active_spaces and self.active_spaces[symbol]:
                # 找出与信号方向匹配的空间
                matching_spaces = []
                for space in self.active_spaces[symbol]:
                    space_direction = space.get('direction')
                    
                    # 如果空间方向与信号方向一致，添加到匹配列表
                    if (space_direction == 'bullish' and action == 'BUY') or (space_direction == 'bearish' and action == 'SELL'):
                        matching_spaces.append(space)
                
                if matching_spaces:
                    # 对每个匹配的空间执行增强决策
                    for space in matching_spaces:
                        space_id = space.get('space_id', 'unknown')
                        self.logger.info(f"[共振信号执行] 对 {symbol} 空间ID:{space_id} 执行增强 {action} 决策，共振权重={weight:.2f}")
                        
                        # 这里可以调用执行引擎实现具体交易，例如：
                        # 增加仓位、调整止损止盈、提高优先级等
                        # 由于具体执行逻辑可能与执行引擎实现相关，这里仅记录日志
                        
                        # 记录共振信号到空间信息中，便于后续处理
                        if 'resonance_signals' not in space:
                            space['resonance_signals'] = []
                            
                        space['resonance_signals'].append({
                            'action': action,
                            'weight': weight,
                            'strategies': strategies,
                            'timestamp': current_time
                        })
                else:
                    self.logger.info(f"[共振信号处理] {symbol} 没有与 {action} 方向匹配的活动空间，跳过执行")
            else:
                self.logger.info(f"[共振信号处理] {symbol} 没有活动空间，跳过执行")

    def _map_event_to_symbol(self, event_data: Dict[str, Any]) -> List[Dict[str, Union[str, float]]]: # Changed Event to Dict[str, Any] for broader compatibility
        """
        Maps an economic event to a list of potentially tradable symbols and suggested directions
        based on the configured event mapping rules.

        Args:
            event_data (Dict[str, Any]): The economic event data, expected to be a dictionary-like object
                                with keys like 'id', 'title', 'country_code', 'actual', 
                                'forecast', 'previous', 'impact'.

        Returns:
            List[Dict[str, Union[str, float]]]: A list of dictionaries, where each dictionary
            represents a tradable opportunity. Example:
            [{'symbol': 'EURUSD', 
              'suggested_direction': 'BUY', 
              'base_currency_outcome': 'good', # or 'bad'
              'rule_id': 'us_nfp_eurusd_rule' # ID of the rule from event_mapping.yaml
            }]
            Returns an empty list if no mapping rule matches or if data is insufficient.
        """
        matched_symbols_and_directions = []
        if not self.event_mapping_rules:
            logger.debug(f"[{self.strategy_id}] _map_event_to_symbol: No event mapping rules loaded.")
            return matched_symbols_and_directions

        if not isinstance(event_data, dict):
            logger.warning(f"[{self.strategy_id}] _map_event_to_symbol: event_data is not a dictionary. Type: {type(event_data)}. Event: {event_data}")
            return matched_symbols_and_directions

        event_title = str(event_data.get('title', '')).lower()
        event_country_code = str(event_data.get('country_code', '')).upper()
        # Use event_data.get('id') directly, or a generated one if not present.
        event_id_from_data = event_data.get('id')
        event_log_id = str(event_id_from_data) if event_id_from_data is not None else f"event_at_{event_data.get('datetime', 'unknown_time')}"

        self.logger.debug(f"[{self.strategy_id}] _map_event_to_symbol ENTRY for event_log_id: {event_log_id}, title: {event_title}, country: {event_country_code}")

        actual_val = event_data.get('actual') 
        forecast_val = event_data.get('forecast')
        previous_val = event_data.get('previous')

        logger.debug(f"[{self.strategy_id}] Mapping event (ID: {event_log_id}): Title='{event_title}', Country='{event_country_code}', A='{actual_val}', F='{forecast_val}', P='{previous_val}'")

        for rule in self.event_mapping_rules:
            rule_id = rule.get('id', 'unknown_rule')
            rule_country_codes = [cc.upper() for cc in rule.get('country_codes', [])]
            rule_title_keywords = [kw.lower() for kw in rule.get('title_keywords', [])]
            outcome_condition = rule.get('outcome_is_good_condition')
            symbols_reactions = rule.get('symbols_and_reactions', [])
            
            # impacted_currency = rule.get('impacted_currency', '') # Available if needed

            if event_country_code not in rule_country_codes:
                continue

            title_match = False
            if not rule_title_keywords: 
                title_match = True 
            else:
                for keyword in rule_title_keywords:
                    if keyword in event_title:
                        title_match = True
                        break
            
            if not title_match:
                continue
            
            logger.debug(f"[{self.strategy_id}] Rule '{rule_id}' matched event country/title for event '{event_log_id}'.")

            if not outcome_condition or not symbols_reactions:
                logger.warning(f"[{self.strategy_id}] Rule '{rule_id}' for event '{event_log_id}' is missing 'outcome_is_good_condition' ('{outcome_condition}') or 'symbols_and_reactions'. Skipping rule.")
                continue

            is_good_outcome = self._evaluate_outcome_condition(outcome_condition, actual_val, forecast_val, previous_val)
            outcome_label = "good" if is_good_outcome else "bad"
            logger.debug(f"[{self.strategy_id}] Rule '{rule_id}', Event '{event_log_id}': Condition '{outcome_condition}' -> '{outcome_label}' (A='{actual_val}', F='{forecast_val}', P='{previous_val}')")

            for reaction in symbols_reactions:
                symbol = reaction.get('symbol')
                direction_if_good = str(reaction.get('direction_if_good', '')).upper()
                direction_if_bad = str(reaction.get('direction_if_bad', '')).upper()

                if not symbol:
                    logger.warning(f"[{self.strategy_id}] Rule '{rule_id}', Event '{event_log_id}': Reaction missing symbol. Skipping.")
                    continue
                
                suggested_direction = None
                if is_good_outcome:
                    if not direction_if_good:
                        logger.debug(f"[{self.strategy_id}] Rule '{rule_id}', Symbol {symbol}: Missing 'direction_if_good' for good outcome.")
                        continue
                    suggested_direction = direction_if_good
                else: 
                    if not direction_if_bad:
                        logger.debug(f"[{self.strategy_id}] Rule '{rule_id}', Symbol {symbol}: Missing 'direction_if_bad' for bad outcome.")
                        continue
                    suggested_direction = direction_if_bad
                
                if suggested_direction not in ["BUY", "SELL", "HOLD", "NONE"]:
                     logger.warning(f"[{self.strategy_id}] Rule '{rule_id}', Symbol {symbol}: Invalid suggested direction '{suggested_direction}'. Must be BUY, SELL, HOLD, or NONE.")
                     continue 
                
                if suggested_direction in ["HOLD", "NONE"] or not suggested_direction: # Also catch empty string
                    logger.info(f"[{self.strategy_id}] Rule '{rule_id}', Event '{event_log_id}', Symbol {symbol}: Suggested direction is '{suggested_direction}'. No trade signal generated.")
                    continue

                result_entry = {
                    'symbol': symbol,
                    'suggested_direction': suggested_direction,
                    'base_currency_outcome': outcome_label,
                    'rule_id': rule_id
                }
                matched_symbols_and_directions.append(result_entry)
                self.logger.info(f"Event {event_log_id} ('{event_title}') mapped to {symbol} with direction {suggested_direction} (base currency outcome: {outcome_label}) by rule '{rule_id}'.")

        self.logger.debug(f"[{self.strategy_id}] _map_event_to_symbol EXIT for event_log_id: {event_log_id}. Found {len(matched_symbols_and_directions)} matches.")
        return matched_symbols_and_directions

    def _get_pip_size(self, symbol: str) -> Optional[float]:
        # Last digit for most FX pairs (e.g., EURUSD 1.2345, pip is 0.0001)
        # For JPY pairs, it's the second digit (e.g., USDJPY 123.45, pip is 0.01)
        # For XAUUSD, XAGUSD, usually 2 decimal places for pip (e.g., XAUUSD 1800.12, pip is 0.01)
        # For Indices, Stocks, and Oil, the concept of "pip" is different.
        # It's usually "tick size" or minimum price fluctuation.
        # The value of this fluctuation per contract/lot also varies greatly.
        # This function aims to return the traditional FX-style pip size for calculation of buffers.
        # For non-FX or non-standard symbols, it will return None and log a warning,
        # indicating that the user must provide specific handling or configuration.

        symbol_upper = symbol.upper()

        # Predefined common pip sizes for FX and metals
        # This list should be verified and extended by the user based on their broker/data.
        common_pip_sizes = {
            # Majors & Minors (5-digit pricing, 4th decimal is pip)
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
            "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
            # JPY Pairs (3-digit pricing, 2nd decimal is pip)
            "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01,
            "AUDJPY": 0.01, "CHFJPY": 0.01, "CADJPY": 0.01, "NZDJPY": 0.01,
            # Metals (Commonly priced to 2 decimal places for pip context)
            "XAUUSD": 0.01, # Gold
            "XAGUSD": 0.01, # Silver
        }

        if symbol_upper in common_pip_sizes:
            return common_pip_sizes[symbol_upper]

        # Fallback for JPY pairs not explicitly listed (e.g. if symbol is "EURJPY.BROKER")
        if "JPY" in symbol_upper:
            # This is a common convention for JPY pairs.
            # If your JPY pair has a different convention (e.g., more decimal places in its price),
            # you will need to add it specifically to common_pip_sizes or adjust this logic.
            self.logger.info(f"[{self.strategy_name}-{symbol}] Assuming JPY pair convention (0.01 pip size). Please verify for your specific broker and symbol.")
            return 0.01

        # For other symbols, especially indices, stocks, oil - cannot provide a generic FX-style pip.
        # User needs to define how buffer calculations should work for these.
        non_fx_like_patterns = ["SPX", "D30", "TSLA", "XBR", "XTI", "NASDAQ", "STOXX", ".OQ", ".N"] # Add more patterns if needed
        if any(pattern in symbol_upper for pattern in non_fx_like_patterns):
            self.logger.warning(
                f"[{self.strategy_name}-{symbol}] Symbol '{symbol}' appears to be an Index, Stock, or Commodity "
                f"for which a standard FX-style pip size is not applicable for buffer calculations in this context. "
                f"You need to define its minimum price fluctuation and how it translates to a buffer. Returning None."
            )
            return None

        # Default for unrecognised FX-like symbols (e.g. exotic pairs)
        # THIS IS A GUESS AND LIKELY TO BE WRONG. USER MUST VERIFY.
        self.logger.warning(
            f"[{self.strategy_name}-{symbol}] Pip size for symbol '{symbol}' is not predefined. "
            f"Falling back to a default of 0.0001. !!! USER MUST VERIFY THIS IS CORRECT FOR '{symbol}' !!! "
            f"Incorrect pip size will lead to incorrect buffer calculations and strategy behavior."
        )
        return 0.0001

    def _get_recent_m30_bars(self, symbol: str, current_bar_time: pd.Timestamp, num_bars: int) -> Optional[pd.DataFrame]:
        """获取指定品种在给定时间点之前的最近N条M30 K线数据"""
        # This method uses self.data_provider to fetch historical data.
        # Ensure data_provider is correctly initialized and accessible.
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _get_recent_m30_bars ENTRY. current_bar_time: {current_bar_time}, num_bars: {num_bars}")

        if self.data_provider is None:
            self.logger.error(f"[{self.strategy_id}-{symbol}] Data provider is not available. Cannot fetch M30 bars.")
            return None

        if num_bars <= 0:
            self.logger.warning(f"[{self.strategy_id}-{symbol}] num_bars requested for _get_recent_m30_bars must be positive, got {num_bars}.")
            return None

        lookback_timedelta = pd.Timedelta(minutes=(num_bars + 4) * 30) 
        start_time_utc = current_bar_time - lookback_timedelta

        try:
            hist_df = self.data_provider.get_historical_prices(
                symbol=symbol,
                start_time_utc=start_time_utc,
                end_time_utc=current_bar_time, 
                timeframe=self.primary_timeframe 
            )

            if hist_df is None or hist_df.empty:
                self.logger.warning(f"[{self.strategy_id}-{symbol}] No historical M30 data returned by data_provider for range {start_time_utc} to {current_bar_time}.")
                return None

            hist_df = hist_df.sort_index(ascending=True)

            if len(hist_df) < num_bars:
                self.logger.warning(f"[{self.strategy_id}-{symbol}] Insufficient M30 data: got {len(hist_df)}, needed {num_bars} for range {start_time_utc} to {current_bar_time}.")
                return hist_df # Return what we have

            return hist_df.tail(num_bars)

        except Exception as e:
            self.logger.error(f"[{self.strategy_id}-{symbol}] Error fetching M30 bars for {symbol} up to {current_bar_time}: {e}", exc_info=True)
            return None

    def _process_events(self, events_df: pd.DataFrame, market_data: Dict[str, Dict[str, pd.DataFrame]], current_processing_time: pd.Timestamp):
        self.logger.debug(f"[{self.strategy_id}] ENTERING _process_events. Number of events: {len(events_df)}, Current Time: {current_processing_time}") # P2.I.1.2 Log
        """
        Processes new economic events to identify tradable opportunities and create/update spaces.
        """
        self.logger.debug(f"[{self.strategy_id}] _process_events ENTRY. Processing {len(events_df)} events at {current_processing_time}.")

        # Filter events based on impact, currency, and keywords as per parameters
        if events_df.empty:
            self.logger.debug(f"[{self.strategy_id}] No new events to process at {current_processing_time}.")
            self.logger.debug(f"[{self.strategy_id}] EXITING _process_events due to empty events_df.") # P2.I.1.2 Log
            return

        for index, event in events_df.iterrows():
            event_dict = event.to_dict()
            event_log_id = str(event_dict.get('id', f"event_idx_{index}"))
            self.logger.debug(f"[{self.strategy_id}] Processing event: {event_log_id} - {event_dict.get('title')}")

            mapped_opportunities = self._map_event_to_symbol(event_dict)

            if not mapped_opportunities:
                self.logger.debug(f"[{self.strategy_id}] Event {event_log_id} did not map to any opportunity.")
                continue

            for opportunity in mapped_opportunities:
                symbol = opportunity.get('symbol')
                if not symbol:
                    self.logger.warning(f"[{self.strategy_id}] Mapped opportunity for event {event_log_id} is missing 'symbol'. Skipping.")
                    continue
                
                # Manage active spaces: only allow a certain number of spaces per event or overall
                active_spaces_for_symbol = self.active_spaces.get(symbol, [])
                
                # This logic is a bit simplified, needs to consider if existing spaces are from *this* event
                # or if the limit is per-symbol regardless of event.
                # For now, assuming a simple count per symbol based on active_spaces.
                # A more robust approach would tag spaces with their originating event_id.
                
                # Example check: if len(active_spaces_for_symbol) >= self.max_active_spaces_per_event:
                # self.logger.info(f"Max active spaces ({self.max_active_spaces_per_event}) reached for {symbol} from event {event_log_id}. Not creating new space.")
                # continue
                # For P0, let's assume we create a space if mapped. Limit management is for later.

                self.logger.info(f"Event {event_log_id} mapped to {symbol}. Proceeding to calculate space boundaries.")
                
                # Fetch M30 data for space calculation
                event_time_utc_series = event.get('datetime') 
                if pd.isna(event_time_utc_series):
                    self.logger.warning(f"Event {event_log_id} for {symbol} has no datetime. Using current_processing_time: {current_processing_time}")
                    event_time_utc = current_processing_time
                else:
                    # Ensure event_time_utc is a Timestamp and timezone-aware (UTC)
                    if not isinstance(event_time_utc_series, pd.Timestamp):
                        try:
                            event_time_utc = pd.Timestamp(event_time_utc_series)
                        except Exception as e_ts:
                            self.logger.error(f"Could not parse event datetime '{event_time_utc_series}' for event {event_log_id}. Error: {e_ts}. Using current processing time.")
                            event_time_utc = current_processing_time
                    else:
                        event_time_utc = event_time_utc_series

                    if event_time_utc.tzinfo is None:
                        event_time_utc = event_time_utc.tz_localize('UTC')
                    elif str(event_time_utc.tzinfo).upper() != 'UTC':
                        event_time_utc = event_time_utc.tz_convert('UTC')
                
                # Use the market_data passed into this function
                symbol_market_data = market_data.get(symbol, {})
                m30_data_for_space_calc = symbol_market_data.get(self.primary_timeframe)

                if m30_data_for_space_calc is None or m30_data_for_space_calc.empty:
                    self.logger.warning(f"No {self.primary_timeframe} data available for {symbol} at event time {event_time_utc} to calculate space for event {event_log_id}. Cannot create space.")
                    continue
                
                # Ensure m30_data_for_space_calc index is UTC (similar to process_new_data)
                if m30_data_for_space_calc.index.tzinfo is None:
                    m30_data_for_space_calc.index = m30_data_for_space_calc.index.tz_localize('UTC')
                elif str(m30_data_for_space_calc.index.tzinfo).upper() != 'UTC':
                    m30_data_for_space_calc.index = m30_data_for_space_calc.index.tz_convert('UTC')

                space_details = self._calculate_space_boundaries_from_initial_move(symbol, event_time_utc, m30_data_for_space_calc)

                if space_details:
                    # Add originating event details to space_details
                    space_details['event_id'] = event_log_id
                    space_details['event_title'] = event_dict.get('title', 'N/A')
                    space_details['event_time'] = event_time_utc.isoformat()
                    space_details['symbol'] = symbol # ensure symbol is in space_details
                    space_details['creation_time'] = current_processing_time.isoformat() # Add space creation time

                    # Initialize invalidation state for the new space
                    self._initialize_space_invalidation_state(space_details) # P0 - Step 4.1

                    if symbol not in self.active_spaces:
                        self.active_spaces[symbol] = []
                    
                    # Check if a similar space (e.g., from the same event or very close in time/price) already exists
                    # This is a placeholder for more advanced duplicate/overlap checking.
                    # For now, we add it if calculable.
                    self.active_spaces[symbol].append(space_details)
                    self.logger.info(f"New space created for {symbol} from event {event_log_id}: High={space_details['space_high']:.5f}, Low={space_details['space_low']:.5f}, Valid until={space_details['valid_until']}")
                else:
                    self.logger.warning(f"Could not calculate space boundaries for {symbol} from event {event_log_id}.")

        self.logger.debug(f"[{self.strategy_id}] _process_events EXIT.")

    def _calculate_space_boundaries_from_initial_move(self, symbol: str, event_time_utc: pd.Timestamp, m30_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _calculate_space_boundaries_from_initial_move ENTRY. Event time: {event_time_utc}")
        # Find the M30 bar that contains or immediately follows the event time
        # Ensure m30_data index is sorted if not already
        if not m30_data.index.is_monotonic_increasing:
            m30_data = m30_data.sort_index()

        if event_time_utc not in m30_data.index:
            # Try to find the nearest preceding bar if direct match fails (e.g. event time is off-market)
            try:
                loc = m30_data.index.get_loc(event_time_utc, method='ffill')
                event_time_on_bar = m30_data.index[loc]
                self.logger.debug(f"[{self.strategy_id}-{symbol}] Event time {event_time_utc} not directly in M30 index. Using ffill, mapped to bar at {event_time_on_bar}.")
                event_time_utc = event_time_on_bar # Adjust event_time_utc to an actual bar time
            except KeyError:
                self.logger.error(f"[{self.strategy_id}-{symbol}] _calculate_space_boundaries: Event time {event_time_utc} not in M30 data index and ffill failed. Data range: {m30_data.index.min()}-{m30_data.index.max()}")
                return None        
        
        start_idx = m30_data.index.get_loc(event_time_utc) # No method needed now as we ensured it or ffilled

        # Plan item 2.1.3 (refined check): If start_idx refers to a bar that is too late in a very short df
        if start_idx >= len(m30_data):
             self.logger.warning(f"[{self.strategy_id}-{symbol}] _calculate_space_boundaries: Event time {event_time_utc} maps to an index beyond available bars after ffill. len(m30_data)={len(m30_data)}, start_idx={start_idx}")
             return None

        initial_move_bar = m30_data.iloc[start_idx]
        if initial_move_bar.empty:
            self.logger.warning(f"No M30 bar found at or immediately after event time {event_time_utc} for {symbol}. Cannot determine initial move.")
            return None

        self.logger.debug(f"[{self.strategy_id}-{symbol}] Initial move bar for event at {event_time_utc} identified as bar at {initial_move_bar.name}")

        # Define space boundaries based on this bar's high and low
        space_high = initial_move_bar['high'].iloc[0]
        space_low = initial_move_bar['low'].iloc[0]
        space_height_pips = (space_high - space_low) / self._get_pip_size(symbol)

        self.logger.info(f"[{self.strategy_id}-{symbol}] Calculated initial space: High={space_high:.5f}, Low={space_low:.5f}, Height={space_height_pips:.2f} pips. Min height: {self.min_space_height_pips} pips.")

        if space_height_pips < self.min_space_height_pips:
            self.logger.info(f"Calculated space height {space_height_pips:.2f} pips for {symbol} is less than minimum {self.min_space_height_pips} pips. Space not created.")
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _calculate_space_boundaries_from_initial_move EXIT due to insufficient height.")
            return None

        # Calculate valid_until time
        event_bar_time_utc = initial_move_bar.name
        valid_until = event_bar_time_utc + timedelta(minutes=self.space_duration_minutes)

        space_details = {
            "space_high": space_high,
            "space_low": space_low,
            "space_height_pips": space_height_pips,
            "valid_until": valid_until.isoformat()
        }
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _calculate_space_boundaries_from_initial_move EXIT. Space details created.")
        return space_details

    def _check_and_handle_space_invalidation(self, space: Dict[str, Any], bar_data: pd.Series, current_processing_time: pd.Timestamp) -> bool:
        """
        Checks and handles space invalidation based on various conditions.
        Returns True if the space was invalidated, False otherwise.
        """
        symbol = space.get('symbol', 'UnknownSymbol')
        event_id = space.get('event_id', 'UnknownEvent')
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation ENTRY for space from event {event_id}. Current time: {current_processing_time}")

        # Condition 0: Space duration expired (already handled by filtering active_spaces generally)
        # This is more of a double check or if this function is called outside the main loop's filter
        if current_processing_time > space.get('valid_until', pd.Timestamp.max):
            space['is_valid'] = False
            space['invalidation_reason'] = 'duration_expired'
            space['invalidation_time'] = current_processing_time.isoformat()
            self.logger.info(f"Space for {symbol} (event {event_id}) invalidated: DURATION EXPIRED at {current_processing_time}. Valid until: {space['valid_until']}")
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation EXIT. Invalidated by duration.")
            return True

        pip_size = self._get_pip_size(symbol)
        if pip_size is None: return False

        # Check Invalidation Conditions from P0 Plan Step 1.1
        # Order of checks can be important.
        # For example, a strong breakout might occur before oscillation criteria are met.

        self.logger.debug(f"[{self.strategy_id}-{symbol}] Checking invalidation conditions for space (event {event_id}). Bar: H={bar_data['high']:.5f}, L={bar_data['low']:.5f}, C={bar_data['close']:.5f}")

        space_high = space['space_high']
        space_low = space['space_low']
        space_height = space_high - space_low

        if self._check_strong_breakout_invalidation(space, bar_data, space_height):
            space['is_valid'] = False
            space['invalidation_reason'] = 'strong_breakout'
            space['invalidation_time'] = current_processing_time.isoformat()
            self.logger.info(f"Space for {symbol} (event {event_id}) invalidated: STRONG BREAKOUT at {current_processing_time}")
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation EXIT. Invalidated by strong breakout.")
            return True

        if self._check_oscillation_invalidation(space, bar_data, space_high, space_low):
            space['is_valid'] = False
            space['invalidation_reason'] = 'oscillation'
            space['invalidation_time'] = current_processing_time.isoformat()
            self.logger.info(f"Space for {symbol} (event {event_id}) invalidated: OSCILLATION at {current_processing_time}")
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation EXIT. Invalidated by oscillation.")
            return True
        
        if self._check_breakout_retrace_confirmation_invalidation(space, bar_data, space_high, space_low, space_height):
            space['is_valid'] = False
            space['invalidation_reason'] = 'breakout_retrace_confirmation'
            space['invalidation_time'] = current_processing_time.isoformat()
            self.logger.info(f"Space for {symbol} (event {event_id}) invalidated: BREAKOUT RETRACE CONFIRMATION at {current_processing_time}")
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation EXIT. Invalidated by BRC.")
            return True

        self.logger.debug(f"[{self.strategy_id}-{symbol}] Space (event {event_id}) remains valid after checks.")
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_and_handle_space_invalidation EXIT. Space still valid.")
        return False

    def _check_strong_breakout_invalidation(self, space: Dict[str, Any], bar_data: pd.Series, space_height: float) -> bool:
        symbol = space.get('symbol', 'UnknownSymbol')
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_strong_breakout_invalidation ENTRY. Space ID: {space.get('event_id', 'N/A')}")
        pip_size = self._get_pip_size(space['symbol'])
        if pip_size is None: return False

        status = space['invalidation_status']
        space_high = space['space_high']
        space_low = space['space_low']

        # Ensure N_bars is at least 1 for meaningful check
        n_bars_for_confirmation = max(1, self.strong_breakout_N_bars) 

        if status.get('strong_breakout_pending', False):
            status['bars_since_strong_breakout'] = status.get('bars_since_strong_breakout', 0) + 1
            
            returned_to_space = False
            if status.get('strong_breakout_direction') == 1: # Was an upward breakout
                if bar_data['low'] < space_high:
                    returned_to_space = True
            elif status.get('strong_breakout_direction') == -1: # Was a downward breakout
                if bar_data['high'] > space_low:
                    returned_to_space = True
            
            if returned_to_space:
                self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] Strong breakout attempt ({status.get('strong_breakout_direction')}) failed; price returned to space. Resetting pending status.")
                status['strong_breakout_pending'] = False
                status['bars_since_strong_breakout'] = 0
                status['strong_breakout_direction'] = 0
                return False # Not invalidated, breakout aborted
            else:
                if status['bars_since_strong_breakout'] >= n_bars_for_confirmation:
                    reason = f"cond1_strong_breakout_{'up' if status.get('strong_breakout_direction') == 1 else 'down'}_confirmed"
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] Invalidated: Strong breakout confirmed. {status['bars_since_strong_breakout']} bars outside space after initial breakout {status.get('strong_breakout_direction')}.")
                    space['status'] = f'inactive_{reason}'
                    space['invalidation_reason'] = reason
                    return True # Invalidated
                else:
                    # self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] Pending strong breakout confirmation. Bars outside: {status['bars_since_strong_breakout']}/{n_bars_for_confirmation}")
                    return False # Still pending, not yet invalidated
        else:
            # Check for new strong breakout
            breakout_detected_direction = 0
            # Upward strong breakout
            if bar_data['close'] > space_high and (bar_data['close'] - space_high) > (2 * space_height):
                breakout_detected_direction = 1
                # self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] Potential strong upward breakout detected: close={bar_data['close']:.5f}, space_high={space_high:.5f}, 2*height={2*space_height:.5f}")
            # Downward strong breakout
            elif bar_data['close'] < space_low and (space_low - bar_data['close']) > (2 * space_height):
                breakout_detected_direction = -1
                # self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] Potential strong downward breakout detected: close={bar_data['close']:.5f}, space_low={space_low:.5f}, 2*height={2*space_height:.5f}")

            if breakout_detected_direction != 0:
                self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] New strong breakout pending: direction={breakout_detected_direction}. Starting count for {n_bars_for_confirmation} bars.")
                status['strong_breakout_pending'] = True
                status['strong_breakout_direction'] = breakout_detected_direction
                status['bars_since_strong_breakout'] = 1 # Current bar is the first bar of breakout
                # If n_bars_for_confirmation is 1, this breakout is immediately confirmed.
                if n_bars_for_confirmation == 1:
                    reason = f"cond1_strong_breakout_{'up' if status['strong_breakout_direction'] == 1 else 'down'}_confirmed_immediate"
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] Invalidated: Strong breakout confirmed immediately (N_bars=1). Direction: {status['strong_breakout_direction']}.")
                    space['status'] = f'inactive_{reason}'
                    space['invalidation_reason'] = reason
                    return True # Invalidated
                return False # Pending confirmation for N > 1
            
        return False # No new breakout, not pending

    def _check_oscillation_invalidation(self, space: Dict[str, Any], bar_data: pd.Series, space_high: float, space_low: float) -> bool:
        symbol = space.get('symbol', 'UnknownSymbol')
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_oscillation_invalidation ENTRY. Space ID: {space.get('event_id', 'N/A')}. Crossings: {space.get('osc_boundary_crossings', 0)}")
        # This logic needs to carefully define what a "crossing" is.
        # A simple version: if the close of the previous bar was on one side of a boundary (or inside)
        # and the current bar's close is on the other side (or outside in the opposite direction).
        bar_close = bar_data['close']

        # Update last known price relative to boundaries for next bar's check
        space['osc_last_price_high'] = space_high
        space['osc_last_price_low'] = space_low

        self.logger.debug(f"[{self.strategy_id}-{symbol}] Current crossings for space {space.get('event_id', 'N/A')}: {space['osc_boundary_crossings']}. Target: {self.oscillation_M_times}")

        if space['osc_boundary_crossings'] >= self.oscillation_M_times:
            self.logger.info(f"Oscillation invalidation for {space['symbol']} (event {space.get('event_id', 'N/A')}): Boundary crossings ({space['osc_boundary_crossings']}) reached limit ({self.oscillation_M_times}).")
            space['status'] = 'inactive_oscillation'
            space['invalidation_reason'] = 'oscillation'
            space['invalidation_time'] = pd.Timestamp.now(tz='UTC').isoformat()
            self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_oscillation_invalidation EXIT. Condition MET.")
            return True

        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_oscillation_invalidation EXIT. Condition NOT met.")
        return False
    
    def _check_breakout_retrace_confirmation_invalidation(self, space: Dict[str, Any], bar_data: pd.Series, space_high: float, space_low: float, space_height: float) -> bool:
        symbol = space.get('symbol', 'UnknownSymbol')
        state = space.get('brc_state', 'None')
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _check_breakout_retrace_confirmation_invalidation ENTRY. Space ID: {space.get('event_id', 'N/A')}. Current BRC State: {state}")

        pip_size = self._get_pip_size(space['symbol'])
        if pip_size is None: return False

        buffer = self.retrace_confirmation_buffer_ratio * space_height

        current_phase = space.get('brc_phase')
        breakout_direction = space.get('brc_direction', 0)

        # Phase: initial_breakout or None (looking for a new breakout)
        if current_phase is None:
            detected_new_breakout_direction = 0
            initial_breakout_price_candidate = None
            # Upward breakout: close is above space_high + buffer
            if bar_data['close'] > space_high + buffer:
                detected_new_breakout_direction = 1
                initial_breakout_price_candidate = bar_data['close'] 
                # self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Initial UP breakout detected. Price {bar_data['close']:.5f} > high {space_high:.5f} + buffer {buffer:.5f}")
            # Downward breakout: close is below space_low - buffer
            elif bar_data['close'] < space_low - buffer:
                detected_new_breakout_direction = -1
                initial_breakout_price_candidate = bar_data['close']
                # self.logger.debug(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Initial DOWN breakout detected. Price {bar_data['close']:.5f} < low {space_low:.5f} - buffer {buffer:.5f}")
            
            if detected_new_breakout_direction != 0:
                self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Phase changed to 'waiting_for_retrace'. Direction: {detected_new_breakout_direction}, Initial Breakout Price: {initial_breakout_price_candidate:.5f}")
                space['brc_phase'] = 'waiting_for_retrace'
                space['brc_direction'] = detected_new_breakout_direction
                space['brc_initial_price'] = initial_breakout_price_candidate
                space['brc_retrace_target_high'] = space_high + buffer
                space['brc_retrace_target_low'] = space_low - buffer
            return False # No invalidation in this step, phase just started or no breakout

        # Phase: waiting_for_retrace
        elif current_phase == 'waiting_for_retrace':
            retrace_achieved = False
            retrace_price_candidate = None

            if breakout_direction == 1: # Upward breakout, waiting for retrace to space_high + buffer
                if bar_data['low'] <= space_high + buffer: # Touches or enters the upper boundary buffer zone from above
                    retrace_achieved = True
                    retrace_price_candidate = bar_data['low']
                # Check for significant reversal: if price goes below space_low (opposite boundary)
                elif bar_data['close'] < space_low:
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Reversal during 'waiting_for_retrace' (UP). Price {bar_data['close']:.5f} < space_low {space_low:.5f}. Resetting phase.")
                    space['brc_phase'] = None
                    space['brc_direction'] = 0
                    space['brc_initial_price'] = None
                    return False
            elif breakout_direction == -1: # Downward breakout, waiting for retrace to space_low - buffer
                if bar_data['high'] >= space_low - buffer: # Touches or enters the lower boundary buffer zone from below
                    retrace_achieved = True
                    retrace_price_candidate = bar_data['high']
                # Check for significant reversal: if price goes above space_high (opposite boundary)
                elif bar_data['close'] > space_high:
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Reversal during 'waiting_for_retrace' (DOWN). Price {bar_data['close']:.5f} > space_high {space_high:.5f}. Resetting phase.")
                    space['brc_phase'] = None
                    space['brc_direction'] = 0
                    space['brc_initial_price'] = None
                    return False
            
            if retrace_achieved:
                self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Retrace achieved. Phase changed to 'waiting_for_confirmation'. Retrace Price: {retrace_price_candidate:.5f}")
                space['brc_phase'] = 'waiting_for_confirmation'
                space['brc_retrace_achieved_price'] = retrace_price_candidate
            return False # No invalidation yet

        # Phase: waiting_for_confirmation
        elif current_phase == 'waiting_for_confirmation':
            initial_breakout_price = space['brc_initial_price']
            if initial_breakout_price is None:
                self.logger.warning(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: In 'waiting_for_confirmation' but initial_breakout_price is None. Resetting phase.")
                space['brc_phase'] = None # Reset to avoid inconsistent state
                space['brc_direction'] = 0
                return False

            confirmation_achieved = False
            if breakout_direction == 1: # Upward breakout, confirmed if price moves above initial_breakout_price
                if bar_data['close'] > initial_breakout_price: # Using bar_close for confirmation
                    confirmation_achieved = True
                # Check for significant reversal: if price goes below space_low
                elif bar_data['close'] < space_low:
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Reversal during 'waiting_for_confirmation' (UP). Price {bar_data['close']:.5f} < space_low {space_low:.5f}. Resetting phase.")
                    space['brc_phase'] = None
                    space['brc_direction'] = 0
                    space['brc_initial_price'] = None
                    return False
            elif breakout_direction == -1: # Downward breakout, confirmed if price moves below initial_breakout_price
                if bar_data['close'] < initial_breakout_price: # Using bar_close for confirmation
                    confirmation_achieved = True
                # Check for significant reversal: if price goes above space_high
                elif bar_data['close'] > space_high:
                    self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] BRC Cond: Reversal during 'waiting_for_confirmation' (DOWN). Price {bar_data['close']:.5f} > space_high {space_high:.5f}. Resetting phase.")
                    space['brc_phase'] = None
                    space['brc_direction'] = 0
                    space['brc_initial_price'] = None
                    return False

            if confirmation_achieved:
                reason = f"cond3_breakout_retrace_confirm_{'up' if breakout_direction == 1 else 'down'}"
                self.logger.info(f"[{symbol}-{space.get('event_id', 'N/A')}] Invalidated: Breakout-Retrace-Confirmation. Direction: {breakout_direction}. Confirmed Price: {bar_data['close']:.5f} vs Initial Breakout: {initial_breakout_price:.5f}")
                space['status'] = f'inactive_{reason}'
                space['invalidation_reason'] = reason
                space['invalidation_time'] = pd.Timestamp.now(tz='UTC').isoformat()
                return True # Invalidated
            return False # No confirmation yet
        
        return False # Should not be reached if phase is one of the above

    def _process_bar(self, symbol: str, current_bar_df: pd.DataFrame, current_processing_time: pd.Timestamp, all_symbol_m30_data: pd.DataFrame):
        self.logger.debug(f"[{self.strategy_id}-{symbol}] ENTERING _process_bar. Current Time: {current_processing_time}, Bar Time: {current_bar_df['time'].iloc[0] if not current_bar_df.empty else 'N/A'}") # P2.I.1.2 Log
        """
        Processes a new bar for a given symbol:
        - Checks for space invalidation.
        - Calls trading logic for valid spaces.
        """
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _process_bar ENTRY for time {current_processing_time}. Bar timestamp: {current_bar_df['time'].iloc[0]}")
        current_bar_series = current_bar_df.iloc[0]

        # Retrieve active spaces for the current symbol
        active_spaces_for_symbol = self.active_spaces.get(symbol, [])
        
        # Iterate over a copy for safe modification if needed, though direct status update is common.
        # The actual removal/filtering of inactive spaces can be done here or periodically.
        for space in active_spaces_for_symbol[:]: # Iterate copy
            if space['status'] != 'active':
                continue

            space_id = space.get('id', 'unknown_space')
            space_formation_end_time = space.get('initial_pulse_end_time')

            if not isinstance(space_formation_end_time, pd.Timestamp):
                self.logger.error(f"[{symbol}-{space_id}] Space is missing a valid 'initial_pulse_end_time'. Marking as error and skipping.")
                space['status'] = 'inactive_error_missing_creation_time'
                space['invalidation_reason'] = 'error_missing_creation_time'
                space['invalidation_time'] = current_processing_time
                continue
            
            if current_bar_series.name <= space_formation_end_time:
                # self.logger.debug(f"[{symbol}-{space_id}] Skipping bar at {current_bar_series.name} as it is not strictly after space formation end time {space_formation_end_time}.")
                continue
            
            space['last_bar_time'] = current_bar_series.name
            space['last_close_price'] = current_bar_series['close']

            is_invalidated = self._check_and_handle_space_invalidation(space, current_bar_series, current_processing_time)

            if is_invalidated:
                self.logger.info(f"[{symbol}-{space_id}] Space became inactive. Reason: {space.get('invalidation_reason', 'unknown')}. Status: {space.get('status')}.")
                if space.get('trade_active') and space.get('entry_order_id'):
                    self.logger.info(f"[{symbol}-{space_id}] Space invalidated with an active trade (Order ID: {space['entry_order_id']}). Position should be closed.")
                    # Actual trade closing logic needs to be implemented here or via signal to ExecutionEngine
                    # e.g., self.execution_engine.close_trade_for_space(space_id, reason=space.get('invalidation_reason'))
            else:
                self.logger.debug(f"[{self.strategy_id}-{symbol}] Space {space_id} remains active. Processing trading logic.") # P2.I.1.2 Log
                self._execute_trading_logic(symbol, current_bar_df.copy(), space, self.active_spaces[symbol]) # Pass a copy of current_bar_df
        
        # Clean up invalidated spaces for the symbol
        # 计算已失效的空间数量
        num_invalidated = len([s for s in self.active_spaces.get(symbol, []) if s.get('status') != 'active'])
        if num_invalidated > 0:
            self.active_spaces[symbol] = [s for s in self.active_spaces[symbol] if s['status'] == 'active']
            if not self.active_spaces[symbol]:
                del self.active_spaces[symbol] # Remove symbol entry if no valid spaces left

        self.logger.debug(f"[{self.strategy_id}-{symbol}] _process_bar EXIT. Active spaces for symbol: {len(self.active_spaces.get(symbol, []))}") # P2.I.1.2 Log

    def _execute_trading_logic(self, symbol: str, current_bar: pd.DataFrame, space_info: dict, all_symbol_spaces: list):
        # Implement trading logic based on the current bar and space_info
        # This method should be implemented to handle trading logic based on the space's state
        # and the current bar data.
        # This is a placeholder and should be replaced with the actual implementation of trading logic.
        event_id = space_info.get('event_id', 'N/A')
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _execute_trading_logic ENTRY for space (event {event_id}). Bar time: {current_bar['time'].iloc[0]}")
        # self.logger.debug(f"Space details: {space_info}") # Can be very verbose
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _execute_trading_logic EXIT (placeholder). No action taken.")
        pass

    def _initialize_space_invalidation_state(self, space: dict):
        symbol = space.get('symbol', 'UnknownSymbol')
        event_id = space.get('event_id', 'N/A') # Assuming event_id is added to space dict
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _initialize_space_invalidation_state ENTRY for space (event {event_id})")
        # For Strong Breakout
        space['sb_pending_confirmation_direction'] = None # 'UP' or 'DOWN'
        space['sb_pending_confirmation_level'] = None   # Price level that was broken
        space['brc_confirmation_level'] = None          # Price level that needs to be broken for confirmation

        # General state
        space['is_valid'] = True
        space['invalidation_reason'] = None
        space['invalidation_time'] = None
        self.logger.debug(f"[{self.strategy_id}-{symbol}] Initialized invalidation state for space (event {event_id}): sb_dir={space['sb_pending_confirmation_direction']}, osc_cross={space['osc_boundary_crossings']}, brc_state={space['brc_state']}")
        self.logger.debug(f"[{self.strategy_id}-{symbol}] _initialize_space_invalidation_state EXIT.")

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
