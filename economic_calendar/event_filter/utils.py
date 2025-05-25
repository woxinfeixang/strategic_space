# 筛选模块辅助工具函数 

import logging
import pytz
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Any, List, Optional

# 从同级 constants 模块导入常量
from .constants import US_HOLIDAYS, WEEKEND_DAYS

logger = logging.getLogger('economic_calendar.event_filter.utils')

# --- 时区定义 ---
TZ_UTC = pytz.utc
TZ_ET = pytz.timezone('US/Eastern')      # 美国东部时间 (处理 EST/EDT)
TZ_LONT = pytz.timezone('Europe/London')  # 伦敦时间 (处理 GMT/BST)
TZ_BJ = pytz.timezone('Asia/Shanghai')   # 北京时间 (UTC+8)

# 定义中文星期映射 (添加到这里)
WEEKDAY_MAP_ZH = {
    0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"
}

# 映射重要性等级
IMPORTANCE_MAP = {
    1: "低",
    2: "中",
    3: "高"
}

# 映射事件实际值、预测值、前值的好坏标签
ACTUAL_LABEL_MAP = {
    "better": "好于预期",
    "worse": "差于预期",
    "equal": "符合预期",
    None: ""  # 处理空值
}

def is_market_holiday(date_str: str) -> bool:
    """
    判断给定日期是否为美国市场假日
    
    Args:
        date_str: 日期字符串，格式为 YYYY-MM-DD
        
    Returns:
        bool: 是否为市场假日
    """
    return date_str in US_HOLIDAYS

def is_weekend(date_str: str) -> bool:
    """
    判断给定日期是否为周末
    
    Args:
        date_str: 日期字符串，格式为 YYYY-MM-DD
        
    Returns:
        bool: 是否为周末
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.weekday() in WEEKEND_DAYS
    except ValueError:
        logger.error(f"日期格式无效: {date_str}")
        return False # 或者抛出异常？取决于调用者如何处理

def is_market_open_day(date_str: str) -> bool:
    """
    判断给定日期是否为市场开盘日 (非周末，非美国节假日)
    
    Args:
        date_str: 日期字符串，格式为 YYYY-MM-DD
        
    Returns:
        bool: 是否为市场开盘日
    """
    if is_weekend(date_str):
        return False
    if is_market_holiday(date_str):
        return False
    # 可以在这里添加其他市场关闭日的判断逻辑
    return True

# is_market_open_time 函数依赖 US_STOCK_MARKET_OPEN/CLOSE
# 并且与 is_market_open_day 耦合，暂时不移到 utils
# 考虑将其与时间范围筛选一起放在 logic.py 或单独的 time_logic.py?

# get_next_market_open_day 也可以放在这里
def get_next_market_open_day(date_str: str) -> str:
    """
    获取下一个市场开盘日 (跳过周末和节假日)
    
    Args:
        date_str: 日期字符串，格式为 YYYY-MM-DD
        
    Returns:
        str: 下一个市场开盘日，格式为 YYYY-MM-DD
    """
    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d')
        next_date = current_date + timedelta(days=1)
        
        # 循环直到找到一个开盘日
        while not is_market_open_day(next_date.strftime('%Y-%m-%d')):
            next_date += timedelta(days=1)
            
        return next_date.strftime('%Y-%m-%d')
    except ValueError:
        logger.error(f"无法解析日期: {date_str}")
        # 返回明天作为一种容错？或者抛出异常？
        tomorrow = datetime.now().date() + timedelta(days=1)
        return tomorrow.strftime('%Y-%m-%d')

# --- 从 src/filters/market_events.py 迁移 ---

def _get_event_id(event: Dict[str, Any]) -> str:
    """
    获取事件的唯一标识 (基于日期、时间、货币、事件名)
    
    Args:
        event: 事件数据字典
        
    Returns:
        事件唯一标识字符串
    """
    # 兼容不同 key 名
    date = event.get('date', event.get('Date', event.get('日期', '')))
    time = event.get('time', event.get('Time', event.get('时间', '')))
    currency = event.get('currency', event.get('Currency', event.get('货币', '')))
    name = event.get('event', event.get('Event', event.get('事件', '')))
    
    # 确保各部分是字符串
    return f"{str(date)}-{str(time)}-{str(currency)}-{str(name)}"

def merge_event_lists(*lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并多个事件列表并去重
    
    Args:
        *lists: 一个或多个事件列表
            
    Returns:
        合并并去重后的事件列表
    """
    event_ids = set()
    merged = []
    
    for event_list in lists:
        if not isinstance(event_list, list):
            logger.warning(f"输入不是列表，跳过: {type(event_list)}")
            continue
            
        for event in event_list:
            if not isinstance(event, dict):
                logger.warning(f"列表中的元素不是字典，跳过: {type(event)}")
                continue
                
            event_id = _get_event_id(event)
            if event_id not in event_ids:
                merged.append(event)
                event_ids.add(event_id)
                
    logger.info(f"合并去重完成，最终包含 {len(merged)} 条事件。")
    return merged

# TODO: 添加更多通用的日期/时间处理函数 

# --- 新增：生成市场开盘事件函数 ---

def generate_market_open_event(
    target_date_str: str,
    local_open_time: dt_time,
    local_tz: pytz.BaseTzInfo,
    event_name: str,
    currency: str,
    importance_str: str = "" # 默认重要性为空字符串
) -> Optional[Dict[str, Any]]:
    """
    通用的生成市场开盘事件函数。

    Args:
        target_date_str: 目标日期 (YYYY-MM-DD)。
        local_open_time: 本地开盘时间 (datetime.time 对象)。
        local_tz: 本地时区 (pytz 时区对象)。
        event_name: 事件名称。
        currency: 货币代码。
        importance_str: 重要性描述 (字符串)。

    Returns:
        事件字典 (北京时间) 或 None (如果当天不开盘或出错)。
    """
    if not is_market_open_day(target_date_str):
        # logger.debug(f"{target_date_str} 不是开盘日，不生成 {event_name} 事件。")
        return None

    try:
        # 1. 创建本地日期时间对象 (naive)
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        naive_dt = datetime.combine(target_date, local_open_time)

        # 2. 本地化时间 (处理夏令时)
        local_dt = local_tz.localize(naive_dt, is_dst=None) # is_dst=None 让 pytz 自动判断

        # 3. 转换为北京时间
        beijing_dt = local_dt.astimezone(TZ_BJ)

        # 4. 计算中文星期
        weekday_zh = WEEKDAY_MAP_ZH.get(beijing_dt.weekday(), '') # 获取中文星期

        # 5. 构建事件字典 (加入 Weekday)
        event = {
            "Date": beijing_dt.strftime('%Y-%m-%d'),
            "Weekday": f"星期{weekday_zh}", # 添加 Weekday 字段，格式如 "星期一"
            "Time": beijing_dt.strftime('%H:%M'),
            "Currency": currency,
            "Event": event_name,
            "Importance": importance_str, # 使用传入的或默认的空字符串
            "Actual": "",
            "Forecast": "",
            "Previous": ""
            # Source 和 TimestampUTC 已在之前的修改中移除
        }
        # logger.debug(f"成功生成事件: {event}")
        return event

    except Exception as e:
        logger.error(f"生成 {event_name} 事件时出错 (日期: {target_date_str}): {e}", exc_info=True)
        return None

def generate_us_market_open_event(date_str: str, open_time: dt_time, timezone_str: str) -> Optional[Dict[str, Any]]:
    """生成美股开盘事件 (北京时间)。"""
    try:
        local_tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        logger.error(f"未知的美国时区: {timezone_str}")
        return None

    return generate_market_open_event(
        target_date_str=date_str,
        local_open_time=open_time,
        local_tz=local_tz,
        event_name="美股开盘",
        currency="USD",
        importance_str="" # 美股开盘重要性设为空字符串
    )

def generate_eu_market_open_event(date_str: str, open_time: dt_time, timezone_str: str) -> Optional[Dict[str, Any]]:
    """生成欧盘开盘事件 (基于指定时区，输出北京时间)。"""
    try:
        local_tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        logger.error(f"未知的欧洲时区: {timezone_str}")
        return None
    # 假设以法兰克福/柏林时间为基准，货币用 EUR
    return generate_market_open_event(
        target_date_str=date_str,
        local_open_time=open_time,
        local_tz=local_tz,
        event_name="欧盘开盘(法兰克福)", # 更明确的名称
        currency="EUR",
        importance_str="" # 欧盘开盘重要性设为空字符串
    )

def add_market_open_events(
    target_dates: List[str],
    add_us_open: bool = True,
    add_eu_open: bool = True,
    us_open_time_str: str = "09:30",
    us_timezone_str: str = "America/New_York",
    us_open_window_minutes: int = 15,
    eu_open_time_str: str = "08:00",
    eu_timezone_str: str = "Europe/Berlin",
    eu_open_window_minutes: int = 15
) -> List[Dict[str, Any]]:
    """
    为给定的日期列表批量生成美股和/或欧盘开盘事件。
    使用传入的具体时间和时区配置。
    """
    open_events = []
    logger.info(f"准备为 {len(target_dates)} 个日期生成开盘事件 (US: {add_us_open}, EU: {add_eu_open})")

    # 解析时间字符串
    try:
        us_hour, us_minute = map(int, us_open_time_str.split(':'))
        us_open_time_obj = dt_time(us_hour, us_minute)
    except ValueError:
        logger.error(f"无效的美国开盘时间格式: {us_open_time_str}. 使用默认 09:30.")
        us_open_time_obj = dt_time(9, 30)

    try:
        eu_hour, eu_minute = map(int, eu_open_time_str.split(':'))
        eu_open_time_obj = dt_time(eu_hour, eu_minute)
    except ValueError:
        logger.error(f"无效的欧洲开盘时间格式: {eu_open_time_str}. 使用默认 08:00.")
        eu_open_time_obj = dt_time(8, 0)

    us_generated = 0
    eu_generated = 0
    skipped_days = 0

    for date_str in target_dates:
        us_event = None
        eu_event = None

        # 首先检查是否是开盘日
        if not is_market_open_day(date_str):
            skipped_days += 1
            continue # 跳过非开盘日

        if add_us_open:
            us_event = generate_us_market_open_event(date_str, us_open_time_obj, us_timezone_str)
            if us_event:
                open_events.append(us_event)
                us_generated += 1

        if add_eu_open:
            eu_event = generate_eu_market_open_event(date_str, eu_open_time_obj, eu_timezone_str)
            if eu_event:
                open_events.append(eu_event)
                eu_generated += 1

    logger.info(f"共生成 {us_generated} 个美股开盘事件，{eu_generated} 个欧盘开盘事件。跳过 {skipped_days} 个非开盘日。")
    return open_events

# --- 可以添加一个通用时区转换函数 (如果其他地方需要) ---
def convert_event_time_to_beijing(
    event: Dict[str, Any],
    original_tz: pytz.BaseTzInfo,
    date_key: str = 'Date',
    time_key: str = 'Time'
) -> Optional[Dict[str, Any]]:
    """
    将事件字典中的日期和时间从原始时区转换为北京时间。
    注意：这会修改传入的字典。
    如果原始时间和日期无效，会返回 None。
    """
    date_str = event.get(date_key)
    time_str = event.get(time_key)

    if not date_str or not time_str:
        logger.warning(f"事件缺少日期或时间字段: {event}")
        return None

    try:
        # 假设时间格式为 HH:MM 或 H:MM
        try:
            naive_time = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
             # 尝试解析 H:MM (例如 9:30)
             naive_time = datetime.strptime(time_str, '%H:%M').time()
             # 如果这里再次失败，会被外层捕获

        naive_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        naive_dt = datetime.combine(naive_date, naive_time)

        # 本地化到原始时区
        original_dt = original_tz.localize(naive_dt, is_dst=None)

        # 转换为北京时间
        beijing_dt = original_dt.astimezone(TZ_BJ)

        # 更新事件字典中的时间和日期
        event[date_key] = beijing_dt.strftime('%Y-%m-%d')
        event[time_key] = beijing_dt.strftime('%H:%M')
        event['TimestampUTC'] = beijing_dt.timestamp() # 更新或添加UTC时间戳

        return event

    except ValueError as e:
        logger.error(f"无法解析事件中的日期 '{date_str}' 或时间 '{time_str}': {e}")
        return None
    except Exception as e:
        logger.error(f"转换事件时间到北京时间时出错: {e}", exc_info=True)
        return None

# 可以在文件末尾添加简单的测试代码
if __name__ == '__main__':
    # 测试日期
    test_date_weekday = "2024-07-22" # 周一
    test_date_weekend = "2024-07-21" # 周日
    test_date_holiday = "2024-07-04" # 美国独立日
    test_date_dst_on = "2024-10-27" # 欧洲夏令时结束前
    test_date_dst_off = "2024-11-03" # 美国夏令时结束

    print(f"--- 测试日期 {test_date_weekday} ---")
    print(f"Is market open day? {is_market_open_day(test_date_weekday)}")
    us_open = generate_us_market_open_event(test_date_weekday, dt_time(9, 30), "America/New_York")
    eu_open = generate_eu_market_open_event(test_date_weekday, dt_time(8, 0), "Europe/Berlin")
    print(f"US Open Event (BJ Time): {us_open}")
    print(f"EU Open Event (BJ Time): {eu_open}")

    print(f"\n--- 测试日期 {test_date_weekend} (周末) ---")
    print(f"Is market open day? {is_market_open_day(test_date_weekend)}")
    us_open_wk = generate_us_market_open_event(test_date_weekend, dt_time(9, 30), "America/New_York")
    eu_open_wk = generate_eu_market_open_event(test_date_weekend, dt_time(8, 0), "Europe/Berlin")
    print(f"US Open Event: {us_open_wk}")
    print(f"EU Open Event: {eu_open_wk}")

    print(f"\n--- 测试日期 {test_date_holiday} (假日) ---")
    print(f"Is market open day? {is_market_open_day(test_date_holiday)}")
    us_open_hol = generate_us_market_open_event(test_date_holiday, dt_time(9, 30), "America/New_York")
    eu_open_hol = generate_eu_market_open_event(test_date_holiday, dt_time(8, 0), "Europe/Berlin")
    print(f"US Open Event: {us_open_hol}")
    print(f"EU Open Event: {eu_open_hol}")

    print(f"\n--- 测试日期 {test_date_dst_on} (夏令时期间) ---")
    us_open_dst_on = generate_us_market_open_event(test_date_dst_on, dt_time(9, 30), "America/New_York")
    eu_open_dst_on = generate_eu_market_open_event(test_date_dst_on, dt_time(8, 0), "Europe/Berlin")
    print(f"US Open Event (BJ Time): {us_open_dst_on}")
    print(f"EU Open Event (BJ Time): {eu_open_dst_on}")

    print(f"\n--- 测试日期 {test_date_dst_off} (夏令时结束) ---")
    us_open_dst_off = generate_us_market_open_event(test_date_dst_off, dt_time(9, 30), "America/New_York")
    eu_open_dst_off = generate_eu_market_open_event(test_date_dst_off, dt_time(8, 0), "Europe/Berlin")
    print(f"US Open Event (BJ Time): {us_open_dst_off}")
    print(f"EU Open Event (BJ Time): {eu_open_dst_off}")

    print("\n--- 批量添加测试 ---")
    dates_to_add = [test_date_weekday, test_date_weekend, test_date_dst_off, "invalid-date"]
    open_events = add_market_open_events(dates_to_add, True, True)
    print(f"Generated {len(open_events)} events:")
    for ev in open_events:
        print(ev)

    print("\n--- 时区转换测试 ---")
    test_event_et = {'Date': '2024-07-22', 'Time': '10:00', 'Event': 'Test ET'}
    converted_et = convert_event_time_to_beijing(test_event_et, TZ_ET)
    print(f"Original ET: {{'Date': '2024-07-22', 'Time': '10:00'}}, Converted: {converted_et}")

    test_event_lont = {'Date': '2024-07-22', 'Time': '14:00', 'Event': 'Test LONT'}
    converted_lont = convert_event_time_to_beijing(test_event_lont, TZ_LONT)
    print(f"Original LONT: {{'Date': '2024-07-22', 'Time': '14:00'}}, Converted: {converted_lont}") 