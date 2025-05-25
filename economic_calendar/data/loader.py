"""
数据加载模块
负责从CSV文件加载经济日历数据
"""
import os
import csv
import logging
import pandas as pd
from datetime import datetime

# 直接定义支持的编码列表
SUPPORTED_ENCODINGS = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']

# 设置日志记录器
logger = logging.getLogger('economic_calendar.data.loader')

def load_input_file(file_path):
    """
    加载CSV文件到pandas DataFrame
    
    参数:
        file_path (str): CSV文件路径
        
    返回:
        DataFrame: 加载的数据，如果失败则返回None
    """
    if not os.path.exists(file_path):
        logger.error(f"错误: 文件不存在 - {file_path}")
        return None
    
    try:
        # 尝试不同的编码
        for encoding in SUPPORTED_ENCODINGS:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                logger.info(f"使用 {encoding} 编码成功读取文件 {file_path}")
                logger.info(f"成功加载 {len(df)} 条记录")
                return df
            except UnicodeDecodeError:
                continue  # 尝试下一个编码
        
        # 如果所有编码都失败
        logger.error(f"无法使用支持的编码读取文件 {file_path}")
        return None
    except Exception as e:
        logger.error(f"加载文件时出错: {e}")
        return None

def load_events(file_path):
    """
    加载经济事件数据
    
    参数:
        file_path (str): CSV文件路径
        
    返回:
        list: 事件列表，每个事件为字典格式
    """
    events = []
    
    if not os.path.exists(file_path):
        logger.error(f"错误: 文件不存在 - {file_path}")
        return events
    
    try:
        # 尝试不同的编码
        success = False
        
        for encoding in SUPPORTED_ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        events.append(row)
                success = True
                logger.info(f"使用 {encoding} 编码成功读取文件")
                break  # 如果成功读取，就跳出循环
            except UnicodeDecodeError:
                continue  # 尝试下一个编码
    
        if success:
            logger.info(f"成功从 {file_path} 加载了 {len(events)} 条事件数据")
            return events
        else:
            logger.error(f"无法使用支持的编码读取文件 {file_path}")
            return []
    except Exception as e:
        logger.error(f"加载事件数据时出错: {e}")
        return []

def validate_event_data(events):
    """
    验证事件数据格式
    
    参数:
        events (list): 事件列表
    
    返回:
        bool: 数据是否有效
    """
    if not events:
        logger.warning("事件列表为空")
        return False
    
    # 检查第一个事件是否包含所需字段
    required_fields = ['日期', '时间', '货币', '事件', '重要性']
    first_event = events[0]
    
    for field in required_fields:
        if field not in first_event:
            logger.error(f"事件数据缺少必要字段: {field}")
            return False
    
    # 检查日期格式是否为YYYY-MM-DD
    for event in events:
        date = event.get('日期', '')
        if not (len(date) == 10 and date[4] == '-' and date[7] == '-'):
            logger.warning(f"事件日期格式不正确: {date}")
            # 不返回False，仅警告
    
    return True 

def load_data(file_path):
    """
    加载经济日历数据文件
    
    参数:
        file_path (str): 文件路径
        
    返回:
        DataFrame: 加载的数据
    """
    try:
        _, ext = os.path.splitext(file_path)
        if ext.lower() == '.csv':
            return pd.read_csv(file_path)
        elif ext.lower() in ['.xls', '.xlsx']:
            return pd.read_excel(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    except Exception as e:
        logger.error(f"加载文件 {file_path} 时出错: {str(e)}")
        raise

def load_local_data(directory, start_date=None, end_date=None):
    """
    从指定目录加载日期范围内的所有数据文件
    
    参数:
        directory (str): 数据文件目录
        start_date (str, optional): 开始日期 (YYYY-MM-DD)
        end_date (str, optional): 结束日期 (YYYY-MM-DD)
        
    返回:
        DataFrame: 合并后的数据
    """
    all_data = []
    
    try:
        files = os.listdir(directory)
        for file in files:
            file_path = os.path.join(directory, file)
            if os.path.isfile(file_path):
                # 从文件名中提取日期
                try:
                    file_date_str = file.split('_')[0]  # 假设文件名格式为: YYYY-MM-DD_其他信息.csv
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                    
                    # 检查日期范围
                    if start_date and file_date < datetime.strptime(start_date, "%Y-%m-%d"):
                        continue
                    if end_date and file_date > datetime.strptime(end_date, "%Y-%m-%d"):
                        continue
                        
                    df = load_data(file_path)
                    all_data.append(df)
                except (ValueError, IndexError) as e:
                    logger.warning(f"无法从文件名 {file} 解析日期: {str(e)}")
                    continue
        
        if not all_data:
            logger.warning(f"在目录 {directory} 中未找到符合条件的数据文件")
            return pd.DataFrame()
            
        return pd.concat(all_data, ignore_index=True)
    except Exception as e:
        logger.error(f"加载目录 {directory} 中的数据时出错: {str(e)}")
        raise 