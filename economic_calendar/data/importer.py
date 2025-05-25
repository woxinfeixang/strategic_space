"""
数据导入模块
负责从不同来源导入经济日历数据
"""
import pandas as pd
import numpy as np
import logging
import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 设置日志记录器
logger = logging.getLogger('economic_calendar.data.importer')

class EconomicCalendarImporter:
    """
    经济日历数据导入器
    支持从多种来源导入经济数据
    """
    
    def __init__(self, config=None):
        """
        初始化数据导入器
        
        参数:
            config (dict): 配置参数
        """
        self.config = config or {}
        # 默认保存路径
        self.default_save_dir = self.config.get('save_dir', 'economic_calendar/data')
        
        # 确保保存目录存在
        Path(self.default_save_dir).mkdir(parents=True, exist_ok=True)
        
        # 初始化API配置
        self.api_keys = self.config.get('api_keys', {})
    
    def import_from_csv(self, file_path, encoding='utf-8', date_format=None):
        """
        从CSV文件导入经济日历数据
        
        参数:
            file_path (str): CSV文件路径
            encoding (str): 文件编码
            date_format (str): 日期格式
            
        返回:
            DataFrame: 导入的数据框
        """
        try:
            # 解析日期列
            parse_dates = None
            if date_format:
                parse_dates = [0]  # 假设第一列是日期
            
            df = pd.read_csv(file_path, encoding=encoding, parse_dates=parse_dates)
            logger.info(f"从CSV文件导入了 {len(df)} 条记录: {file_path}")
            return df
        
        except Exception as e:
            logger.error(f"从CSV导入数据时出错: {e}")
            return pd.DataFrame()  # 返回空数据框
    
    def import_from_excel(self, file_path, sheet_name=0, date_format=None):
        """
        从Excel文件导入经济日历数据
        
        参数:
            file_path (str): Excel文件路径
            sheet_name (str|int): 工作表名称或索引
            date_format (str): 日期格式
            
        返回:
            DataFrame: 导入的数据框
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # 处理日期列
            if date_format:
                date_cols = [col for col in df.columns if '日期' in col or 'date' in col.lower()]
                for col in date_cols:
                    df[col] = pd.to_datetime(df[col], format=date_format, errors='coerce')
            
            logger.info(f"从Excel文件导入了 {len(df)} 条记录: {file_path}")
            return df
        
        except Exception as e:
            logger.error(f"从Excel导入数据时出错: {e}")
            return pd.DataFrame()  # 返回空数据框
    
    def import_from_json(self, file_path):
        """
        从JSON文件导入经济日历数据
        
        参数:
            file_path (str): JSON文件路径
            
        返回:
            DataFrame: 导入的数据框
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 将JSON转换为DataFrame
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                # 如果是嵌套结构，尝试提取事件数据
                if 'events' in data:
                    df = pd.DataFrame(data['events'])
                elif 'data' in data:
                    df = pd.DataFrame(data['data'])
                else:
                    # 如果没有明确的结构，尝试从第一层键提取数据
                    for key, value in data.items():
                        if isinstance(value, list):
                            df = pd.DataFrame(value)
                            break
                    else:
                        logger.warning(f"JSON文件结构无法识别: {file_path}")
                        return pd.DataFrame()
            
            logger.info(f"从JSON文件导入了 {len(df)} 条记录: {file_path}")
            return df
        
        except Exception as e:
            logger.error(f"从JSON导入数据时出错: {e}")
            return pd.DataFrame()  # 返回空数据框
    
    def import_from_api(self, api_name, start_date=None, end_date=None, **kwargs):
        """
        从API导入经济日历数据
        
        参数:
            api_name (str): API名称
            start_date (str): 开始日期
            end_date (str): 结束日期
            **kwargs: 其他API特定参数
            
        返回:
            DataFrame: 导入的数据框
        """
        # 默认日期范围 - 如果未指定则使用今天和未来7天
        if not start_date:
            start_date = datetime.now().strftime('%Y-%m-%d')
        if not end_date:
            end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        # 根据API名称调用相应的处理函数
        api_handlers = {
            'investing': self._import_from_investing,
            'myfxbook': self._import_from_myfxbook,
            'forexfactory': self._import_from_forexfactory,
            'tradingeconomics': self._import_from_tradingeconomics
        }
        
        handler = api_handlers.get(api_name.lower())
        if handler:
            return handler(start_date=start_date, end_date=end_date, **kwargs)
        else:
            logger.error(f"不支持的API: {api_name}")
            return pd.DataFrame()
    
    def _import_from_investing(self, start_date, end_date, **kwargs):
        """从Investing.com导入数据"""
        try:
            api_key = self.api_keys.get('investing')
            if not api_key:
                logger.error("缺少Investing.com API密钥")
                return pd.DataFrame()
            
            # 构建API请求
            url = "https://api.investing.com/economic-calendar"
            headers = {
                "X-API-KEY": api_key,
                "User-Agent": "Mozilla/5.0"
            }
            params = {
                "from": start_date,
                "to": end_date,
                "country": kwargs.get('countries', ''),
                "importance": kwargs.get('importance', '')
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            df = pd.DataFrame(data.get('data', []))
            
            logger.info(f"从Investing.com API导入了 {len(df)} 条记录")
            return df
        
        except Exception as e:
            logger.error(f"从Investing.com导入数据时出错: {e}")
            return pd.DataFrame()
    
    def _import_from_myfxbook(self, start_date, end_date, **kwargs):
        """从MyFxBook导入数据"""
        try:
            # MyFxBook API通常是公开的，不需要API密钥
            url = "https://www.myfxbook.com/api/get-calendar.json"
            
            params = {
                "start": start_date,
                "end": end_date
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get('error', True):
                logger.error(f"MyFxBook API返回错误: {data.get('message')}")
                return pd.DataFrame()
            
            df = pd.DataFrame(data.get('calendar', []))
            
            logger.info(f"从MyFxBook API导入了 {len(df)} 条记录")
            return df
        
        except Exception as e:
            logger.error(f"从MyFxBook导入数据时出错: {e}")
            return pd.DataFrame()
    
    def _import_from_forexfactory(self, start_date, end_date, **kwargs):
        """从ForexFactory导入数据"""
        try:
            # ForexFactory没有官方API，这里实现网页抓取或使用第三方API
            logger.warning("ForexFactory数据导入尚未实现")
            return pd.DataFrame()
        
        except Exception as e:
            logger.error(f"从ForexFactory导入数据时出错: {e}")
            return pd.DataFrame()
    
    def _import_from_tradingeconomics(self, start_date, end_date, **kwargs):
        """从TradingEconomics导入数据"""
        try:
            api_key = self.api_keys.get('tradingeconomics')
            if not api_key:
                logger.error("缺少TradingEconomics API密钥")
                return pd.DataFrame()
            
            # 构建API请求
            url = "https://api.tradingeconomics.com/calendar"
            headers = {
                "Authorization": f"Client {api_key}"
            }
            
            countries = kwargs.get('countries', '')
            indicator = kwargs.get('indicator', '')
            
            params = {
                "from": start_date,
                "to": end_date
            }
            
            if countries:
                params['country'] = countries
            if indicator:
                params['indicator'] = indicator
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            df = pd.DataFrame(data)
            
            logger.info(f"从TradingEconomics API导入了 {len(df)} 条记录")
            return df
        
        except Exception as e:
            logger.error(f"从TradingEconomics导入数据时出错: {e}")
            return pd.DataFrame()
    
    def import_from_multiple_sources(self, sources):
        """
        从多个来源导入数据并合并
        
        参数:
            sources (list): 数据源配置列表
            
        返回:
            DataFrame: 合并后的数据框
        """
        dfs = []
        
        for source in sources:
            source_type = source.get('type')
            
            if source_type == 'csv':
                df = self.import_from_csv(
                    file_path=source.get('path'),
                    encoding=source.get('encoding', 'utf-8'),
                    date_format=source.get('date_format')
                )
            
            elif source_type == 'excel':
                df = self.import_from_excel(
                    file_path=source.get('path'),
                    sheet_name=source.get('sheet_name', 0),
                    date_format=source.get('date_format')
                )
            
            elif source_type == 'json':
                df = self.import_from_json(file_path=source.get('path'))
            
            elif source_type == 'api':
                df = self.import_from_api(
                    api_name=source.get('api_name'),
                    start_date=source.get('start_date'),
                    end_date=source.get('end_date'),
                    **source.get('params', {})
                )
            
            else:
                logger.warning(f"不支持的数据源类型: {source_type}")
                continue
            
            if not df.empty:
                dfs.append(df)
        
        if not dfs:
            logger.warning("所有数据源都未返回数据")
            return pd.DataFrame()
        
        # 合并数据框
        merged_df = pd.concat(dfs, ignore_index=True)
        logger.info(f"从 {len(sources)} 个来源合并了 {len(merged_df)} 条记录")
        
        return merged_df
    
    def save_data(self, df, file_path=None, format='csv', encoding='utf-8'):
        """
        保存数据到文件
        
        参数:
            df (DataFrame): 要保存的数据框
            file_path (str): 保存路径
            format (str): 保存格式(csv, excel, json)
            encoding (str): 文件编码
            
        返回:
            bool: 是否保存成功
        """
        if df.empty:
            logger.warning("没有数据可保存")
            return False
        
        # 如果没有提供文件路径，生成默认路径
        if not file_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = os.path.join(self.default_save_dir, f'economic_calendar_{timestamp}.{format}')
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 根据格式保存
            if format.lower() == 'csv':
                df.to_csv(file_path, encoding=encoding, index=False)
            
            elif format.lower() == 'excel':
                df.to_excel(file_path, index=False)
            
            elif format.lower() == 'json':
                df.to_json(file_path, orient='records', force_ascii=False, indent=4)
            
            else:
                logger.error(f"不支持的保存格式: {format}")
                return False
            
            logger.info(f"成功保存 {len(df)} 条记录到: {file_path}")
            return True
        
        except Exception as e:
            logger.error(f"保存数据时出错: {e}")
            return False 