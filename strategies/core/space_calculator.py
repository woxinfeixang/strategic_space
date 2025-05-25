import pandas as pd
from typing import Dict, Any, List

# 假设配置从全局加载或传递进来
# from src.config_loader import load_config
# config = load_config()
# Example placeholder config access
config = {
    'strategy_params': {
        'event_driven': {
            'time_window': {
                'pre_event': '2h', # Use Timedelta compatible string
                'post_event': '4h'
            },
            'space_params': {
                'fib_levels': [0.236, 0.382, 0.5, 0.618],
                'volatility_threshold': 0.8
            }
        }
    }
}

def build_event_space(event: Dict[str, Any], price_data: pd.DataFrame) -> Dict[str, Any]:
    """
    根据财经事件和相关时间窗口内的价格数据，构建事件驱动的博弈空间。
    空间定义了关键的支撑位和阻力位，以及空间的有效时间。

    Args:
        event (Dict[str, Any]): 单个事件的字典，至少包含 'id', 'datetime'。
        price_data (pd.DataFrame): 与事件时间窗口相关的价格数据 (OHLC)。

    Returns:
        Dict[str, Any]: 包含事件空间信息的字典，例如:
            {
                'event_id': event['id'],
                'event_time': pd.Timestamp, # Event time
                'window_start': pd.Timestamp, # Start of pre-event window
                'window_end': pd.Timestamp, # End of pre-event window
                'high': float, # High price in window
                'low': float, # Low price in window
                'resistances': List[float], # Calculated resistance levels
                'supports': List[float], # Calculated support levels
                'valid_until': pd.Timestamp # When the space is considered valid
            }
    """
    try:
        event_time = pd.to_datetime(event['datetime'])
        pre_window_delta = pd.Timedelta(config['strategy_params']['event_driven']['time_window']['pre_event'])
        post_window_delta = pd.Timedelta(config['strategy_params']['event_driven']['time_window']['post_event'])

        # 确定用于计算高低点的时间窗口 (事件发生前的窗口)
        window_start = event_time - pre_window_delta
        window_end = event_time
        relevant_price_data = price_data[(price_data.index >= window_start) & (price_data.index < window_end)]

        if relevant_price_data.empty:
            # Handle case with no price data in the window
            # TODO: Log this situation
            print(f"Warning: No price data found for event {event.get('id')} between {window_start} and {window_end}")
            return {
                'event_id': event.get('id'),
                'event_time': event_time,
                'error': 'No price data in pre-event window'
            }

        high = relevant_price_data['high'].max()
        low = relevant_price_data['low'].min()
        price_range = high - low

        if price_range <= 0:
             # Handle case with zero or negative range (e.g., constant price)
             # TODO: Log this situation
             print(f"Warning: Price range is zero or negative for event {event.get('id')} between {window_start} and {window_end}")
             resistances = [high] * len(config['strategy_params']['space_params']['fib_levels'])
             supports = [low] * len(config['strategy_params']['space_params']['fib_levels'])
        else:
            levels = config['strategy_params']['space_params']['fib_levels']
            resistances = sorted([high - price_range * l for l in levels])
            supports = sorted([low + price_range * l for l in levels], reverse=True)

        # 空间的有效性持续到事件发生后的窗口结束
        valid_until = event_time + post_window_delta

        return {
            'event_id': event.get('id'),
            'event_time': event_time,
            'window_start': window_start,
            'window_end': window_end,
            'high': high,
            'low': low,
            'resistances': resistances,
            'supports': supports,
            'valid_until': valid_until
        }

    except Exception as e:
        # TODO: Log the error properly
        print(f"Error building event space for event {event.get('id')}: {e}")
        return {
            'event_id': event.get('id'),
            'error': str(e)
        }

# 你也可以将其封装在一个类中，如果需要更复杂的状态管理或配置加载
# class SpaceCalculator:
#     def __init__(self, config):
#         self.config = config
#
#     def build_event_space(self, event, price_data):
#         # ... implementation ...
#         pass 