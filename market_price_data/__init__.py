"""
MT5市场数据更新模块

此模块提供了从MetaTrader 5获取历史和实时市场数据的工具，
支持多币种、多时间周期的数据更新和实时监控。

主要组件:
- HistoryUpdater: 历史K线数据下载和更新
- RealtimeUpdater: 实时K线数据监控和保存

使用示例:
    from market_price_data import HistoryUpdater, RealtimeUpdater
    
    # 历史数据更新
    history_updater = HistoryUpdater()
    # history_updater.initialize_mt5() # Initialization is handled within run_update_cycle
    history_updater.run_update_cycle()
    
    # 实时数据监控
    realtime_updater = RealtimeUpdater()
    realtime_updater.start_updater()
    # ... 应用运行中 ...
    # Need to handle stopping, e.g., via KeyboardInterrupt or other signal
    # realtime_updater.stop_updater()
"""

# 版本信息
__version__ = '1.0.1' # Increment version due to change
__author__ = 'Strategic Space'

# 导出主要类以便直接导入
from .history import HistoryUpdater
from .realtime import RealtimeUpdater

# 导出实用函数 (从core模块导入) - 确保core在路径中
try:
    from core.utils import (
        initialize_mt5,
        shutdown_mt5,
        setup_logging,
        load_app_config,
        parse_timeframes,
        MT5_AVAILABLE
    )
except ImportError:
    # If core is not available, perhaps log a warning or set flags
    # For now, let the ImportError propagate if core is essential
    # Or define fallback values/functions if appropriate
    initialize_mt5 = None
    shutdown_mt5 = None
    setup_logging = None
    load_app_config = None
    parse_timeframes = None
    MT5_AVAILABLE = False
    import logging
    logging.warning("Could not import from core.utils. Some functionality might be limited.")

# 便于从模块导入的命名空间整理
__all__ = [
    'HistoryUpdater',
    'RealtimeUpdater',
    # Conditionally export core utils if they were imported
] + ([ 
    'initialize_mt5',
    'shutdown_mt5',
    'setup_logging',
    'load_app_config',
    'parse_timeframes',
    'MT5_AVAILABLE',
] if initialize_mt5 is not None else [])

# --- 移除脚本函数相关的导出 ---
#     'run_history_update',
#     'run_realtime_update',
# ----------------------------- 