#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库筛选逻辑模块

提供直接在数据库层面筛选财经事件的功能
"""

import logging
import sqlite3
import pandas as pd
from typing import List, Optional, Union

logger = logging.getLogger('economic_calendar.event_filter.db')

def filter_events_from_db(
    db_path: str, 
    min_importance: int = 2, 
    days: int = 7, 
    currencies: Optional[List[str]] = None,
    start_date: Optional[str] = None, # 添加开始日期参数 (YYYY-MM-DD)
    end_date: Optional[str] = None,   # 添加结束日期参数 (YYYY-MM-DD)
    table_name: str = 'events_history' # 允许指定表名
) -> pd.DataFrame:
    """
    从 SQLite 数据库中筛选财经事件
    
    参数:
        db_path (str): SQLite 数据库文件路径
        min_importance (int): 最小重要性 (1-3)
        days (int): 【已废弃，使用 start_date/end_date 代替】向前筛选的天数 (相对于'now')
        currencies (list, optional): 需要筛选的货币代码列表，如 ['USD', 'EUR']
        start_date (str, optional): 筛选开始日期 (YYYY-MM-DD)，包含。
                                    如果为 None，则不限制开始日期 (或从'now'开始，取决于days参数是否移除)。
                                    推荐使用此参数代替 days。
        end_date (str, optional): 筛选结束日期 (YYYY-MM-DD)，包含。
                                  如果为 None，则不限制结束日期。
        table_name (str): 要查询的表名，默认为 'events_history'
    
    返回:
        pd.DataFrame: 筛选后的事件数据 (Pandas DataFrame)
    """
    # 兼容性警告：days 参数即将移除
    if days != 7 and (start_date is None and end_date is None):
        logger.warning("'days' 参数已不推荐使用，请改用 'start_date' 和 'end_date'。基于 'days' 的筛选将从 date('now') 开始。")
    elif days != 7:
         logger.warning("'days' 参数已被 'start_date'/'end_date' 覆盖，将被忽略。")

    # 构建筛选条件日志
    filter_log = []
    if start_date or end_date or (days != 7 and start_date is None and end_date is None):
        date_range_log = []
        if start_date:
            date_range_log.append(f"从 {start_date}")
        elif days != 7 and end_date is None: # 兼容旧的 days 逻辑
             date_range_log.append(f"从 date('now')")
             
        if end_date:
            date_range_log.append(f"到 {end_date}")
        elif days != 7 and start_date is None:
             date_range_log.append(f"向前 {days} 天")
        filter_log.append(f"日期范围: {' '.join(date_range_log)}")
    if min_importance > 0:
        filter_log.append(f"最小重要性={min_importance}")
    if currencies:
        filter_log.append(f"货币={currencies}")
    filter_log_str = ", ".join(filter_log) if filter_log else "无特定条件"

    logger.info(f"开始从数据库 '{db_path}' 表 '{table_name}' 筛选事件: {filter_log_str}")
    
    try:
        # 连接到数据库
        conn = sqlite3.connect(db_path)
        
        # 构建基础SQL查询
        # 使用参数化查询防止 SQL 注入
        query = f"SELECT * FROM {table_name} WHERE 1=1"
        params = []
        
        # 添加日期筛选 (优先使用 start_date/end_date)
        if start_date:
            query += " AND date >= ?"
            # 检查是否为 Timestamp 对象，如果是则格式化
            start_date_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, pd.Timestamp) else start_date
            params.append(start_date_str)
        # 兼容旧的 days 逻辑 (如果 start_date 未提供)
        elif days != 7 and end_date is None: 
            query += " AND date >= date('now')" 

        if end_date:
            query += " AND date <= ?"
            # 检查是否为 Timestamp 对象，如果是则格式化
            end_date_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, pd.Timestamp) else end_date
            params.append(end_date_str)
        # 兼容旧的 days 逻辑 (如果 start_date 未提供)
        elif days != 7 and start_date is None:
            query += f" AND date <= date('now', '+{days} days')" 

        # 添加重要性筛选
        if min_importance > 0:
            query += f" AND importance >= ?"
            params.append(min_importance)
        
        # 添加货币筛选
        if currencies:
            # 构建占位符 (?, ?, ?) 并添加到查询
            placeholders = ', '.join('?' * len(currencies))
            query += f" AND currency IN ({placeholders})"
            params.extend(currencies)
        
        # 执行查询
        df = pd.read_sql_query(query, conn, params=tuple(params))
        conn.close()
        
        # --- 添加时间戳处理 ---
        if not df.empty and 'Date' in df.columns and 'Time' in df.columns:
            try:
                # 合并日期和时间字符串
                datetime_str = df['Date'] + ' ' + df['Time']
                # 转换为 datetime 对象
                df['timestamp'] = pd.to_datetime(datetime_str, errors='coerce')
                # 移除转换失败的行
                df = df.dropna(subset=['timestamp']) 
                
                # Corrected Timezone Handling:
                # Assume naive datetimes from DB (combined Date + Time) represent Beijing Time (Asia/Shanghai)
                # Localize to BJT first, then convert to UTC.
                if not df.empty and 'timestamp' in df.columns: # Ensure timestamp column exists after dropna
                    if df['timestamp'].dt.tz is None:
                        logger.info("Localizing naive 'timestamp' from DB as Asia/Shanghai and converting to UTC.")
                        df['timestamp'] = df['timestamp'].dt.tz_localize('Asia/Shanghai', ambiguous='infer').dt.tz_convert('UTC')
                    else:
                        logger.info("Converting existing timezone-aware 'timestamp' to UTC.")
                        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
                
                    logger.info(f"已成功处理 Date 和 Time 列为 UTC timestamp。")
                else:
                    logger.info("'timestamp' column is empty or not found after NA drop, skipping timezone processing.")

            except Exception as dt_e:
                 logger.error(f"处理日期时间列时出错: {dt_e}，将返回未处理的 DataFrame。")
        elif not df.empty:
             logger.warning("DataFrame 中缺少 'Date' 或 'Time' 列，无法生成 timestamp。")
        # ---------------------
        
        logger.info(f"数据库筛选完成: 共筛选到 {len(df)} 条事件")
        return df
        
    except sqlite3.Error as e:
        logger.error(f"数据库操作失败: {e}")
        if conn:
            conn.close()
        return pd.DataFrame() # 返回空 DataFrame
    except Exception as e:
        logger.error(f"筛选事件时发生未知错误: {str(e)}")
        if conn:
            conn.close()
        return pd.DataFrame()

# 注意：原 db_filter.py 中的导出和命令行相关功能未迁移到此模块 