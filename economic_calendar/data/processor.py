"""
数据处理模块
负责处理和转换经济日历数据
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

# 设置日志记录器
logger = logging.getLogger('economic_calendar.data.processor')

def standardize_columns(df):
    """
    标准化数据列名
    
    参数:
        df (DataFrame): 输入数据框
        
    返回:
        DataFrame: 标准化列名后的数据框
    """
    # 列名映射字典 - 将不同数据源的列名映射到标准列名
    column_mapping = {
        # 英文列名映射
        'date': '日期',
        'time': '时间',
        'currency': '货币',
        'event': '事件',
        'importance': '重要性',
        'actual': '实际值',
        'forecast': '预期值',
        'previous': '前值',
        'Date': '日期',
        'Time': '时间',
        'Currency': '货币',
        'Event': '事件',
        'Impact': '重要性',
        'Actual': '实际值',
        'Forecast': '预期值',
        'Previous': '前值',
        
        # 已经是中文但可能有细微差别的列名
        '日期时间': '日期',
        '发布时间': '时间',
        '公布时间': '时间',
        '货币对': '货币',
        '影响货币': '货币',
        '项目': '事件',
        '指标': '事件',
        '名称': '事件',
        '影响': '重要性',
        '星级': '重要性',
        '实际': '实际值',
        '预期': '预期值',
        '预测': '预期值',
        '先前': '前值',
        '上次值': '前值'
    }
    
    # 重命名列
    renamed_cols = {}
    for col in df.columns:
        if col in column_mapping:
            renamed_cols[col] = column_mapping[col]
    
    if renamed_cols:
        df = df.rename(columns=renamed_cols)
        logger.info(f"列名标准化: {renamed_cols}")
    
    return df

def convert_datetime(df):
    """
    转换并标准化日期和时间格式
    
    参数:
        df (DataFrame): 输入数据框
        
    返回:
        DataFrame: 处理后的数据框
    """
    # 确保日期列存在
    if '日期' not in df.columns:
        logger.error("数据中缺少'日期'列")
        return df
    
    # 创建副本避免修改原始数据
    result = df.copy()
    
    # 尝试转换日期列
    try:
        # 处理日期列可能的不同格式
        if pd.api.types.is_datetime64_any_dtype(result['日期']):
            result['日期'] = result['日期'].dt.strftime('%Y-%m-%d')
        else:
            # 尝试识别和转换不同的日期格式
            try:
                # 首先尝试解析为datetime
                result['日期'] = pd.to_datetime(result['日期']).dt.strftime('%Y-%m-%d')
            except Exception as e:
                logger.warning(f"无法自动转换日期格式: {e}")
    except Exception as e:
        logger.error(f"处理日期列时出错: {e}")
    
    # 处理时间列(如果存在)
    if '时间' in result.columns:
        try:
            # 标准化时间格式为HH:MM
            if pd.api.types.is_datetime64_any_dtype(result['时间']):
                result['时间'] = result['时间'].dt.strftime('%H:%M')
            else:
                # 尝试多种格式转换
                try:
                    # 如果是纯时间字符串(如14:30)
                    result['时间'] = pd.to_datetime(result['时间'], format='%H:%M', errors='coerce').dt.strftime('%H:%M')
                except:
                    # 如果包含日期(可能是完整的日期时间)
                    try:
                        result['时间'] = pd.to_datetime(result['时间'], errors='coerce').dt.strftime('%H:%M')
                    except Exception as e:
                        logger.warning(f"无法自动转换时间格式: {e}")
        except Exception as e:
            logger.error(f"处理时间列时出错: {e}")
    
    return result

def standardize_importance(df):
    """
    标准化重要性指标
    
    参数:
        df (DataFrame): 输入数据框
        
    返回:
        DataFrame: 处理后的数据框
    """
    if '重要性' not in df.columns:
        logger.warning("数据中缺少'重要性'列")
        return df
    
    result = df.copy()
    
    # 重要性映射 - 将不同形式的重要性指标映射为标准形式(高、中、低)
    importance_mapping = {
        # 数字表示
        '3': '高',
        '2': '中',
        '1': '低',
        # 星号表示
        '***': '高',
        '**': '中',
        '*': '低',
        # 英文表示
        'High': '高',
        'Medium': '中',
        'Low': '低',
        'high': '高',
        'medium': '中',
        'low': '低',
        # 其他表示
        '高重要性': '高',
        '中重要性': '中',
        '低重要性': '低',
        '重要': '高',
        '一般': '中',
        '较低': '低'
    }
    
    # 应用映射
    result['重要性'] = result['重要性'].astype(str)
    result['重要性'] = result['重要性'].map(lambda x: importance_mapping.get(x, x))
    
    return result

def clean_numerical_values(df):
    """
    清理并标准化数值列(实际值、预期值、前值)
    
    参数:
        df (DataFrame): 输入数据框
        
    返回:
        DataFrame: 处理后的数据框
    """
    result = df.copy()
    
    # 要处理的数值列
    numerical_columns = ['实际值', '预期值', '前值']
    
    for col in numerical_columns:
        if col in result.columns:
            try:
                # 将百分比转换为数字(如 "5.2%" -> 5.2)
                result[col] = result[col].astype(str).str.replace('%', '')
                
                # 处理科学计数法
                result[col] = result[col].str.replace('K', 'e3', regex=False)
                result[col] = result[col].str.replace('M', 'e6', regex=False)
                result[col] = result[col].str.replace('B', 'e9', regex=False)
                result[col] = result[col].str.replace('T', 'e12', regex=False)
                
                # 移除千位分隔符
                result[col] = result[col].str.replace(',', '')
                
                # 转换为数值类型
                result[col] = pd.to_numeric(result[col], errors='coerce')
            except Exception as e:
                logger.warning(f"清理{col}列时出错: {e}")
    
    return result

def add_derived_fields(df):
    """
    添加派生字段
    
    参数:
        df (DataFrame): 输入数据框
        
    返回:
        DataFrame: 添加派生字段后的数据框
    """
    result = df.copy()
    
    # 添加是否已发布字段 - 基于是否有实际值
    if '实际值' in result.columns:
        result['已发布'] = ~result['实际值'].isna()
    
    # 添加偏差字段(实际值与预期值之差)
    if '实际值' in result.columns and '预期值' in result.columns:
        result['偏差'] = result['实际值'] - result['预期值']
    
    # 添加变化率字段(实际值与前值之差的百分比)
    if '实际值' in result.columns and '前值' in result.columns:
        result['变化率'] = (result['实际值'] - result['前值']) / result['前值'].abs() * 100
        result['变化率'] = result['变化率'].round(2)  # 保留两位小数
    
    return result

def filter_events(df, currencies=None, importance=None, start_date=None, end_date=None):
    """
    根据条件筛选事件
    
    参数:
        df (DataFrame): 输入数据框
        currencies (list): 货币列表
        importance (list): 重要性级别列表
        start_date (str): 开始日期 (YYYY-MM-DD)
        end_date (str): 结束日期 (YYYY-MM-DD)
        
    返回:
        DataFrame: 筛选后的数据框
    """
    result = df.copy()
    
    # 筛选货币
    if currencies and '货币' in result.columns:
        result = result[result['货币'].isin(currencies)]
    
    # 筛选重要性
    if importance and '重要性' in result.columns:
        result = result[result['重要性'].isin(importance)]
    
    # 筛选日期范围
    if '日期' in result.columns:
        if start_date:
            result = result[result['日期'] >= start_date]
        if end_date:
            result = result[result['日期'] <= end_date]
    
    return result

def process_data(df):
    """
    对经济日历数据进行完整处理
    
    参数:
        df (DataFrame): 原始数据框
        
    返回:
        DataFrame: 处理后的数据框
    """
    try:
        # 应用处理步骤
        df = standardize_columns(df)
        df = convert_datetime(df)
        df = standardize_importance(df)
        df = clean_numerical_values(df)
        df = add_derived_fields(df)
        
        # 确保必要的列存在
        required_columns = ['日期', '时间', '货币', '事件', '重要性']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            logger.warning(f"处理后的数据缺少以下列: {missing_columns}")
        
        # 按日期和时间排序
        if '日期' in df.columns:
            if '时间' in df.columns:
                df = df.sort_values(['日期', '时间'])
            else:
                df = df.sort_values('日期')
        
        logger.info(f"数据处理完成，共 {len(df)} 条记录")
        return df
    
    except Exception as e:
        logger.error(f"数据处理过程中发生错误: {e}")
        # 返回原始数据
        return df 