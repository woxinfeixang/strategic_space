import logging
from datetime import datetime # Use datetime
import pandas as pd
from .strategy_base import StrategyBase
from .space_calculator import build_event_space
from typing import List, Dict, Optional, Any # Import Optional

class EventDrivenStrategyBase(StrategyBase):
    """
    事件驱动策略的基类。
    扩展了 StrategyBase，专注于处理基于财经事件的逻辑。
    """
    def __init__(self, config, data_provider, execution_engine):
        super().__init__(config, data_provider, execution_engine)
        # 特定于事件驱动策略的初始化
        self.active_event_spaces = {} # 存储当前活跃的事件空间
        self.logger = logging.getLogger(self.__class__.__name__) # Ensure logger exists
        # 从配置获取构建空间所需的回溯时间窗口
        self.pre_event_window = self.config.get('time_window', {}).get('pre_event', '60min') # Example default
        # 从配置获取构建空间所需的时间框架 (如果策略需要特定精度)
        self.build_space_timeframe = self.config.get('build_space_timeframe', 'M1') # Example default

    def process_new_data(self, current_time: datetime, # Use datetime
                         market_data: Dict[str, Dict[str, pd.DataFrame]],
                         event_data: Optional[pd.DataFrame]) -> None:
        """
        处理由 Orchestrator 传递的新市场数据和事件数据。

        Args:
            current_time (datetime): 当前时间 (UTC)。
            market_data (Dict[str, Dict[str, pd.DataFrame]]): 包含所有相关时间和品种的
                                                               最新合并价格数据的嵌套字典。
                                                               结构: market_data[timeframe][symbol] = DataFrame。
            event_data (Optional[pd.DataFrame]): 新产生的相关事件数据 DataFrame (已过滤)。
                                                 如果当前周期没有新事件，则为 None。
        """
        self.logger.debug(f"Processing new data at {current_time.isoformat()}")

        # 1. 处理新事件，构建博弈空间
        if event_data is not None and not event_data.empty:
            for _, event in event_data.iterrows():
                event_id = event.get('id', str(event.get('datetime'))) # Use datetime as fallback id
                if event_id not in self.active_event_spaces:
                    self.logger.debug(f"处理新事件: ID {event_id} at {event.get('datetime')}")
                    # 确定事件对应的交易品种
                    symbol = self._get_symbol_for_event(event) 
                    if not symbol:
                        self.logger.warning(f"无法确定事件 {event_id} 对应的交易品种，跳过。")
                        continue
                    
                    # 检查所需的时间框架数据是否存在
                    if self.build_space_timeframe not in market_data or symbol not in market_data[self.build_space_timeframe]:
                        self.logger.warning(f"缺少构建事件 {event_id} ({symbol} @ {self.build_space_timeframe}) 空间所需的市场数据，跳过。")
                        continue
                        
                    # 从 market_data 中提取构建空间所需的历史数据
                    try:
                         event_dt = pd.to_datetime(event['datetime']).tz_convert('UTC') # Ensure UTC
                         pre_event_start = event_dt - pd.Timedelta(self.pre_event_window)
                         
                         # 从完整数据中筛选时间范围
                         full_symbol_data = market_data[self.build_space_timeframe][symbol]
                         historical_price_data = full_symbol_data[
                             (full_symbol_data.index >= pre_event_start) & 
                             (full_symbol_data.index < event_dt) # Use < event_dt
                         ]
                    except Exception as data_extract_e:
                         self.logger.error(f"为事件 {event_id} 从 market_data 提取历史数据时出错: {data_extract_e}", exc_info=True)
                         historical_price_data = None # Set to None on error
                    
                    if historical_price_data is not None and not historical_price_data.empty:
                        space = build_event_space(event, historical_price_data)
                        if 'error' not in space:
                            # TODO: 确定空间的有效时间 (valid_until)
                            # 假设 space 计算器返回了 valid_until
                            space['valid_until'] = space.get('valid_until', current_time + pd.Timedelta('4h')) # Example default
                            self.active_event_spaces[event_id] = space
                            self.logger.info(f"为事件 {event_id} 构建并激活了空间: {space}")
                        else:
                            self.logger.warning(f"为事件 {event_id} 构建空间失败: {space['error']}")
                    else:
                         self.logger.warning(f"无法获取或提取用于为事件 {event_id} 构建空间的历史数据 (时间范围: {pre_event_start} to {event_dt})。")

        # 2. 清理过期的事件空间
        expired_ids = []
        for eid, space in self.active_event_spaces.items():
             # Ensure valid_until is a timezone-aware datetime object
             valid_until = space.get('valid_until')
             if isinstance(valid_until, str): valid_until = pd.to_datetime(valid_until).tz_localize('UTC') # Simple parse
             elif isinstance(valid_until, datetime) and valid_until.tzinfo is None: valid_until = valid_until.tz_localize('UTC')
             elif not isinstance(valid_until, datetime):
                 self.logger.warning(f"事件空间 {eid} 的 valid_until 无效: {valid_until}，将其视为已过期。")
                 valid_until = current_time - pd.Timedelta('1s') # Mark as expired
                 
             if current_time >= valid_until:
                 expired_ids.append(eid)
                 
        for eid in expired_ids:
            if eid in self.active_event_spaces:
                 del self.active_event_spaces[eid]
                 self.logger.info(f"移除了过期的事件空间 {eid}")

        # 3. 基于当前活跃空间和最新价格生成信号
        if self.active_event_spaces:
            # 将活跃空间和完整的 market_data 传递给具体策略
            # 注意: generate_signals 的签名也需要更新
            signals = self.generate_signals(list(self.active_event_spaces.values()), market_data)
            for signal in signals:
                 self.logger.debug(f"处理策略生成的信号: {signal}")
                 # 使用基类提供的下单方法
                 self.place_order_from_signal(signal)
        else:
            self.logger.debug("没有活跃的事件空间，跳过信号生成。")

    def generate_signals(self, active_spaces: List[Dict[str, Any]], market_data: Dict[str, Dict[str, pd.DataFrame]]) -> List[Dict[str, Any]]:
        """
        具体策略需要实现此方法。
        根据当前活跃的博弈空间和最新的市场价格数据生成交易信号。

        Args:
            active_spaces (List[Dict[str, Any]]): 当前所有活跃的事件空间列表。
            market_data (Dict[str, Dict[str, pd.DataFrame]]): 包含所有相关时间和品种的
                                                               最新合并价格数据的嵌套字典。
                                                               结构: market_data[timeframe][symbol] = DataFrame。

        Returns:
            List[Dict[str, Any]]: 交易信号列表 (字典格式，符合 place_order_from_signal 要求)。
        """
        raise NotImplementedError("Subclasses must implement generate_signals")

    def _get_symbol_for_event(self, event: Dict[str, Any]) -> Optional[str]: # Return Optional[str]
         """
         确定单个事件对应的主要交易品种。
         需要具体策略或配置提供映射逻辑。
         """
         # TODO: 实现更健壮的映射逻辑，例如从配置读取
         currency = event.get('currency')
         # 简单的示例映射
         mapping = {
             "USD": "EURUSD",
             "EUR": "EURUSD",
             "GBP": "GBPUSD",
             "JPY": "USDJPY",
             "CAD": "USDCAD",
             "AUD": "AUDUSD",
             "NZD": "NZDUSD",
             "CHF": "USDCHF"
             # ... 可扩展 ...
         }
         symbol = mapping.get(currency)
         if not symbol:
             self.logger.warning(f"无法将事件货币 '{currency}' 映射到交易品种。事件: {event.get('id')}")
         return symbol 