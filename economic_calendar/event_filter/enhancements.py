import pandas as pd
import logging

logger = logging.getLogger(__name__) # 使用模块名作为 logger 名称

def add_strategy_metadata(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    为财经日历事件 DataFrame 添加 'strategy_tag' 元数据标签。
    标签格式: <currency>_<importance>_vol<volatility_percentage>
    
    Args:
        events_df (pd.DataFrame): 包含事件数据的 DataFrame。
                                   需要包含 'currency', 'importance', 'volatility' 列。
                                   
    Returns:
        pd.DataFrame: 添加了 'strategy_tag' 列的 DataFrame。
    """
    if events_df is None or events_df.empty:
        logger.warning("Input DataFrame for add_strategy_metadata is empty or None. Returning as is.")
        return events_df

    required_cols = ['currency', 'importance', 'volatility']
    if not all(col in events_df.columns for col in required_cols):
        logger.warning(f"Input DataFrame is missing one or more required columns ({required_cols}). Cannot add strategy tag.")
        # 可以在这里添加一个空的 'strategy_tag' 列以保持列结构一致性，或者直接返回
        events_df['strategy_tag'] = None 
        return events_df

    def create_tag(row):
        try:
            # 确保 importance 是整数或可以转换为整数
            importance = int(row['importance'])
            # 处理 volatility 可能为 NaN 或非数值的情况
            volatility = pd.to_numeric(row['volatility'], errors='coerce')
            if pd.isna(volatility):
                 vol_tag = "volNA"
            else:
                 vol_tag = f"vol{int(volatility * 100)}"
                 
            currency = str(row['currency']).upper() if pd.notna(row['currency']) else "NOCURR"
            
            return f"{currency}_{importance}_{vol_tag}"
        except (ValueError, TypeError) as e:
            logger.warning(f"Error creating tag for row {row.get('id', '')}: {e}. Row data: {row}")
            return None # 返回 None 表示此行无法生成标签

    logger.info("Adding 'strategy_tag' column to events DataFrame...")
    events_df['strategy_tag'] = events_df.apply(create_tag, axis=1)
    logger.info("'strategy_tag' column added.")
    return events_df

# --- 可以添加 __init__.py 在 economic_calendar/event_filter/ 目录中，如果还没有的话 --- 
# # economic_calendar/event_filter/__init__.py
# from .logic import apply_memory_filters, process_events # 等
# from .db import filter_events_from_db
# from .enhancements import add_strategy_metadata # 导出新函数
#
# __all__ = [
#     'apply_memory_filters', 
#     'process_events',
#     'filter_events_from_db',
#     'add_strategy_metadata' # 添加到导出列表
# ] 