"""
MT5数据导出器模块

提供将Pandas DataFrame导出为MT5兼容格式的功能
"""

import pandas as pd
from pathlib import Path
import logging
import os
from typing import Optional, Union, Dict, Any

def export_to_mt5_format(df: pd.DataFrame, 
                        output_path: Union[str, Path], 
                        symbol: str,
                        timeframe: str,
                        logger: logging.Logger) -> bool:
    """
    将Pandas DataFrame导出为MetaTrader 5兼容的CSV格式
    
    Args:
        df: 包含OHLCV数据的DataFrame
        output_path: 输出文件路径或目录
        symbol: 交易品种名称
        timeframe: 时间周期字符串 (M1, M5, H1等)
        logger: 日志记录器实例 (必需)
        
    Returns:
        bool: 导出成功返回True，失败返回False
    """
    logger.info(f"开始导出 {symbol} {timeframe} 到 {output_path}")
    
    if df is None or df.empty:
        logger.warning(f"输入 DataFrame 为空，无法导出 {symbol} {timeframe}")
        return False
    
    required_columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"数据缺少必要列: {', '.join(missing_columns)}")
        return False
            
    if isinstance(output_path, str):
        output_path = Path(output_path)
            
    if output_path.is_dir():
        filename = f"{symbol}_{timeframe}_mt5.csv"
        output_path = output_path / filename
            
    output_path.parent.mkdir(parents=True, exist_ok=True)
        
    export_df = df.copy()
        
    if not pd.api.types.is_datetime64_any_dtype(export_df['time']):
        logger.warning("时间列不是datetime类型，尝试转换")
        export_df['time'] = pd.to_datetime(export_df['time'])
        
    export_df['<DATE>'] = export_df['time'].dt.strftime('%Y.%m.%d')
    export_df['<TIME>'] = export_df['time'].dt.strftime('%H:%M')
        
    mt5_df = pd.DataFrame({
        '<TICKER>': symbol,
        '<PERIOD>': timeframe,
        '<DATE>': export_df['<DATE>'],
        '<TIME>': export_df['<TIME>'],
        '<OPEN>': export_df['open'],
        '<HIGH>': export_df['high'],
        '<LOW>': export_df['low'],
        '<CLOSE>': export_df['close'],
        '<TICKVOL>': export_df['volume'],
        '<VOL>': 0,
        '<SPREAD>': 0
    })
        
    mt5_df.to_csv(output_path, index=False)
    logger.info(f"成功导出 {len(df)} 条数据到 {output_path}")
    return True

def convert_and_export_historical(df: pd.DataFrame, 
                                  output_dir: Union[str, Path],
                                  symbol: str,
                                  timeframe: str,
                                  logger: Optional[logging.Logger] = None) -> bool:
    """
    转换并导出历史数据到MT5格式
    
    Args:
        df: 包含历史数据的DataFrame
        output_dir: 输出目录
        symbol: 交易品种名称
        timeframe: 时间周期字符串
        logger: 可选的日志记录器
        
    Returns:
        bool: 导出成功返回True
    """
    if logger is None:
        logger = logging.getLogger('MT5HistoryExporter')
        logger.setLevel(logging.INFO)
    
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return export_to_mt5_format(df, output_dir, symbol, timeframe, logger) 