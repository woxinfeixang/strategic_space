# strategies/utils/key_time_detector.py
# 关键时间检测工具类

import pytz
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Any, Optional, Union, Set, Tuple


class KeyTimeDetector:
    """
    关键时间检测工具类，支持事件相对时间和固定时间段
    """
    
    def __init__(self, logger):
        """
        初始化关键时间检测器
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger
        # 记录已触发过的关键时间点，避免重复触发
        self._triggered_key_times: Dict[Any, bool] = {}
        
    def get_timeframe_minutes(self, timeframe: str) -> int:
        """
        获取时间框架对应的分钟数
        
        Args:
            timeframe: 时间框架字符串，例如 "M5", "M15", "H1", "H4", "D1"
            
        Returns:
            时间框架对应的分钟数
        """
        tf_map = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
            "D1": 1440,
            "W1": 10080
        }
        return tf_map.get(timeframe.upper(), 60)  # 默认返回H1(60)
    
    def reset_trigger_state(self) -> None:
        """重置关键时间点触发状态"""
        self._triggered_key_times = {}
    
    def is_key_time(self, 
                    current_time_utc: datetime, 
                    space_info: Dict[str, Any],
                    key_time_hours_after_event: List[int] = None,
                    fixed_key_times: List[Dict[str, Any]] = None) -> Optional[datetime]:
        """
        检查当前时间是否为关键时间点
        
        Args:
            current_time_utc: 当前UTC时间
            space_info: 空间信息字典，含 event_data 和 creation_time
            key_time_hours_after_event: 事件发生后的关键小时列表，如 [1, 2, 4]
            fixed_key_times: 固定关键时间段配置列表，例如:
                [{"start":"08:00", "end":"09:00", "tz":"Europe/London", "days_of_week":[0,1,2,3,4]}]
        
        Returns:
            如果是关键时间点，返回关键时间点的UTC时间；否则返回None
        """
        # 检查事件数据和创建时间是否存在
        if not space_info or 'creation_time' not in space_info:
            return None
        
        event_data_dict = space_info.get('event_data')
        if not isinstance(event_data_dict, dict):
            self.logger.debug(f"is_key_time: Expected space_info['event_data'] to be a dict, got {type(event_data_dict)}")
            return None
            
        symbol = event_data_dict.get('symbol')
        if not symbol:
            self.logger.debug(f"is_key_time: 'symbol' not found in space_info['event_data']: {event_data_dict}")
            return None
        
        # 获取空间创建时间（事件发生时间）
        creation_time = space_info['creation_time']
        space_id = space_info.get('space_id', 'unknown')
        
        # 1. 检查事件发生后特定小时数
        if key_time_hours_after_event:
            for hours in key_time_hours_after_event:
                # 计算关键时间点
                key_time_point = creation_time + timedelta(hours=hours)
                
                # 确定唯一触发键
                trigger_key = (space_id, symbol, hours)
                
                # 检查当前时间是否在关键时间点的±30分钟范围内
                time_diff = abs((current_time_utc - key_time_point).total_seconds() / 60)
                
                if time_diff <= 30 and not self._triggered_key_times.get(trigger_key, False):
                    self.logger.info(f"关键时间点触发: 事件发生后{hours}小时 | 品种:{symbol} | 空间ID:{space_id}")
                    # 标记该关键时间点已触发
                    self._triggered_key_times[trigger_key] = True
                    # 返回关键时间点
                    return key_time_point
        
        # 2. 检查固定关键时间段
        if fixed_key_times:
            for rule in fixed_key_times:
                # 解析规则
                start_time_str = rule.get('start')
                end_time_str = rule.get('end')
                timezone_str = rule.get('tz', 'UTC')
                days_of_week = rule.get('days_of_week')  # 0=周一, 6=周日
                
                if not (start_time_str and end_time_str):
                    continue
                
                # 解析时间
                try:
                    start_hour, start_minute = map(int, start_time_str.split(':'))
                    end_hour, end_minute = map(int, end_time_str.split(':'))
                    
                    # 获取时区对象
                    try:
                        tz = pytz.timezone(timezone_str)
                    except pytz.exceptions.UnknownTimeZoneError:
                        self.logger.warning(f"未知时区: {timezone_str}，使用UTC")
                        tz = pytz.UTC
                        
                    # 将当前UTC时间转换为指定时区
                    local_time = current_time_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
                    
                    # 检查星期几是否匹配（如果指定了）
                    if days_of_week is not None and local_time.weekday() not in days_of_week:
                        continue
                    
                    # 创建当天的开始和结束时间点
                    local_start = local_time.replace(
                        hour=start_hour, minute=start_minute, second=0, microsecond=0
                    )
                    local_end = local_time.replace(
                        hour=end_hour, minute=end_minute, second=0, microsecond=0
                    )
                    
                    # 转换回UTC进行比较
                    utc_start = local_start.astimezone(pytz.UTC)
                    utc_end = local_end.astimezone(pytz.UTC)
                    
                    # 确定唯一触发键
                    rule_desc = f"{start_time_str}-{end_time_str}_{timezone_str}"
                    trigger_key = (space_id, symbol, rule_desc, current_time_utc.date())
                    
                    # 检查当前时间是否在时间段内
                    if utc_start <= current_time_utc <= utc_end and not self._triggered_key_times.get(trigger_key, False):
                        self.logger.info(f"固定关键时间段触发: {start_time_str}-{end_time_str} ({timezone_str}) | 品种:{symbol} | 空间ID:{space_id}")
                        # 标记该关键时间点已触发
                        self._triggered_key_times[trigger_key] = True
                        # 返回关键时间段的开始时间作为触发点
                        return utc_start
                        
                except (ValueError, TypeError) as e:
                    self.logger.error(f"解析固定时间段配置错误: {e} | 规则: {rule}")
                    continue
        
        return None 