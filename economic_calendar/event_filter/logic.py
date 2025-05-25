#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
事件筛选逻辑模块 (内存处理)

包含基于关键词、时间、重要性等的筛选功能

# 筛选模块入口点
# 从子模块导入公共接口

# 示例 (将在后续步骤中填充):
# from .logic import filter_events_in_memory
# from .db import filter_events_from_db
"""

import re
import logging
from typing import List, Dict, Any, Optional, Union, Pattern
from datetime import datetime, time as dt_time # 导入 time 并重命名避免冲突
import os
import pandas as pd
import shutil
import yaml
import json
import sqlite3
import pytz
from datetime import timedelta

# ---> 添加导入
# 移除 sort_events，因为它定义在 logic.py 内部
# 同样移除 get_event_importance, filter_by_* 等函数，它们也定义在 logic.py 内部
# 只导入确实来自 utils 且被使用的函数
from .utils import add_market_open_events, WEEKDAY_MAP_ZH, merge_event_lists
# 如果 logic.py 中还用到了 utils.py 的其他函数, 需要也加在这里

# 获取 logger 实例
logger = logging.getLogger(__name__)

# 配置日志
logger.info("--- economic_calendar.event_filter.logic module loaded --- ")

# --- 修正关键词导入 ---
# 直接尝试相对导入，如果失败则日志记录并使用空值
try:
    from ..config.keywords import (
        CURRENCY_KEYWORDS, # 可能仍被旧代码使用，保留以防万一
        CRITICAL_EVENTS,
        IMPORTANT_SPEAKERS,
        HIGH_IMPACT_KEYWORDS,
        CURRENCY_SPECIFIC_2STAR_KEYWORDS,
        US_MARKET_OPEN_TIME,
        US_MARKET_OPEN_WINDOW,
        US_MARKET_TIMEZONE,
        EU_MARKET_OPEN_TIME,
        EU_MARKET_TIMEZONE,
        EU_MARKET_OPEN_WINDOW,
    )
    logger.info("Successfully imported keywords configuration using relative path.")
except ImportError as e:
    logger.error(f"Failed to import keywords configuration using relative path: {e}. Using empty defaults.")
    # 定义空值以避免 NameError
    CURRENCY_KEYWORDS = {}
    CRITICAL_EVENTS = []
    IMPORTANT_SPEAKERS = []
    HIGH_IMPACT_KEYWORDS = []
    CURRENCY_SPECIFIC_2STAR_KEYWORDS = {}
    US_MARKET_OPEN_TIME = "09:30"
    US_MARKET_OPEN_WINDOW = 15
    US_MARKET_TIMEZONE = "America/New_York"
    EU_MARKET_OPEN_TIME = "08:00"
    EU_MARKET_TIMEZONE = "Europe/Berlin"
    EU_MARKET_OPEN_WINDOW = 15
# --- 关键词导入结束 ---

# 从data.loader模块导入load_input_file函数
from ..data.loader import load_input_file
from ..data.exporter import export_to_csv, export_to_sqlite, STANDARD_COLUMNS # 导入 STANDARD_COLUMNS

# 直接从economic_calendar导入，不使用回退机制
# 注意：这里的路径 economic_calendar.config.keywords 可能需要根据实际项目结构调整
# 如果 keywords.py 在 event_filter 同级的 config 目录下，路径应为 ..config.keywords
# 如果 keywords.py 在项目根目录的 config 下，则需要调整 sys.path 或使用绝对导入
try:
    # 尝试相对导入 (假设 config 在 economic_calendar 下)
    from ..config.keywords import (
        CURRENCY_KEYWORDS, CRITICAL_EVENTS, IMPORTANT_SPEAKERS,
        US_MARKET_OPEN_TIME, US_MARKET_OPEN_WINDOW, HIGH_IMPACT_KEYWORDS,
        CURRENCY_SPECIFIC_2STAR_KEYWORDS # 添加导入2星事件关键词配置
    )
    logger.debug("Successfully imported keywords config using relative path.")
except ImportError:
    logger.warning("Relative import of keywords config failed. Trying absolute path assumption.")
    # 尝试绝对导入 (假设 economic_calendar 在顶层, config 也在顶层)
    # 这需要确保项目根目录在 sys.path 中
    try:
        from config.keywords import (
            CURRENCY_KEYWORDS, CRITICAL_EVENTS, IMPORTANT_SPEAKERS,
            US_MARKET_OPEN_TIME, US_MARKET_OPEN_WINDOW, HIGH_IMPACT_KEYWORDS,
            CURRENCY_SPECIFIC_2STAR_KEYWORDS
        )
        logger.debug("Successfully imported keywords config using absolute path.")
    except ImportError as e:
         logger.error(f"Failed to import keywords configuration. Ensure 'config/keywords.py' exists and project structure is correct. Error: {e}")
         # 定义空值以避免 NameError，但这会影响功能
         CURRENCY_KEYWORDS = {}
         CRITICAL_EVENTS = []
         IMPORTANT_SPEAKERS = []
         US_MARKET_OPEN_TIME = "09:30"
         US_MARKET_OPEN_WINDOW = 15
         HIGH_IMPACT_KEYWORDS = []
         CURRENCY_SPECIFIC_2STAR_KEYWORDS = {}
         US_MARKET_TIMEZONE = "America/New_York"
         EU_MARKET_OPEN_TIME = "08:00"
         EU_MARKET_TIMEZONE = "Europe/Berlin"
         EU_MARKET_OPEN_WINDOW = 15


# --- 从原 src/filters/keywords.py 迁移过来的函数 ---

def normalize_text(text: str) -> str:
    """
    标准化文本，移除特殊字符并转换为小写

    Args:
        text: 原始文本

    Returns:
        str: 标准化后的文本
    """
    if not text or not isinstance(text, str): # 添加类型检查
        return ""
    # 转换为小写
    text = text.lower()
    # 移除特殊字符，但保留空格、数字和字母以及中文字符
    # 修改正则表达式以保留中文字符 \u4e00-\u9fff
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
    # 合并多个空格为单个空格
    text = re.sub(r'\s+', ' ', text)
    # 移除首尾空格
    text = text.strip()
    return text

# --- 修改：添加检查中文字符的辅助函数 ---
def contains_chinese(text):
    """检查字符串是否包含中文字符"""
    for char in text:
        # 使用 Unicode 范围判断
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False
# --- 修改结束 ---

def create_keyword_pattern(keywords: List[str]) -> Pattern:
    """
    创建关键词匹配的正则表达式模式

    Args:
        keywords: 关键词列表

    Returns:
        Pattern: 正则表达式模式
    """
    # 对关键词进行预处理
    processed_keywords = []
    for keyword in keywords:
        # 标准化关键词
        normalized = normalize_text(keyword)
        if normalized:
            # --- 修改：根据是否包含中文决定是否加 \b ---
            if contains_chinese(normalized):
                # 中文关键词，不加单词边界，直接转义特殊字符
                processed_keywords.append(re.escape(normalized))
            else:
                # 非中文关键词，加单词边界，并转义
                processed_keywords.append(r'\b' + re.escape(normalized) + r'\b')
            # --- 修改结束 ---

    # 组合所有关键词为一个正则表达式，使用|表示"或"
    pattern_str = '|'.join(processed_keywords)
    if not pattern_str: # 处理空关键词列表的情况
        return re.compile('a^') # 返回一个永远不匹配的模式

    # 编译正则表达式
    try:
        return re.compile(pattern_str, re.IGNORECASE)
    except re.error as e:
        logger.error(f"编译关键词正则表达式时出错: {e}. Keywords: {keywords}")
        return re.compile('a^') # 返回不匹配模式

def keyword_match(text: str, keywords: List[str]) -> bool:
    """
    检查文本是否匹配任一关键词

    Args:
        text: 要检查的文本
        keywords: 关键词列表

    Returns:
        bool: 是否匹配
    """
    # --- 添加调试: 打印原始输入 ---
    # print(f"DEBUG [Matcher]: Original Text: '{text}'")
    # --- 调试结束 ---

    normalized_text = normalize_text(text)
    if not normalized_text:
        # --- 添加调试: 打印标准化结果和空文本跳过 ---
        print(f"DEBUG [Matcher]: Normalized Text: '{normalized_text}' -> Skipping (empty)")
        # --- 调试结束 ---
        return False

    # 编译关键词列表为正则表达式模式
    pattern = create_keyword_pattern(keywords)
    # --- 修改：移除 potential_match 检查，强制打印 ---
    # 为了减少日志量，只在文本可能包含关键词时打印详细信息 (启发式)
    # potential_match = any(kw.lower() in normalized_text for kw in keywords if len(kw)>1) # 简单检查
    # if potential_match:
    print(f"DEBUG [Matcher]: Normalized Text: '{normalized_text}'")
    print(f"DEBUG [Matcher]: Pattern: '{pattern.pattern}'")
    # --- 修改结束 ---

    # 使用search()在文本中查找模式
    match_result = pattern.search(normalized_text)

    # --- 修改：移除 potential_match 检查，强制打印 ---
    # if potential_match:
    print(f"DEBUG [Matcher]: Match Result: {bool(match_result)}")
    # --- 修改结束 ---

    return bool(match_result)

def extract_matched_keywords(text: str, keywords: List[str]) -> List[str]:
    """
    提取文本中匹配的关键词

    Args:
        text: 要检查的文本
        keywords: 关键词列表

    Returns:
        List[str]: 匹配的关键词列表
    """
    if not text or not keywords:
        return []

    # 标准化文本
    normalized_text = normalize_text(text)
    if not normalized_text:
        return []

    # 匹配结果
    matched = []
    # 创建关键词匹配模式 (修复中文匹配问题)
    pattern = create_keyword_pattern(keywords)

    # 找到所有匹配项
    # 注意: findall 直接返回匹配的字符串，而不是原始关键词
    # 为了返回原始关键词，我们仍然需要迭代
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword:
            try:
                # 重新构建单关键词的 pattern (考虑中文)
                single_pattern_str = r'\b' + re.escape(normalized_keyword) + r'\b' if not contains_chinese(normalized_keyword) else re.escape(normalized_keyword)
                if re.search(single_pattern_str, normalized_text, re.IGNORECASE):
                    matched.append(keyword) # 返回原始关键词
            except re.error as e:
                logger.warning(f"构建关键词 '{normalized_keyword}' 的正则表达式时出错: {e}")

    # 去重（如果同一个原始关键词因不同形式匹配多次）
    return list(set(matched))

# ================================================
# ========== filter_by_keywords 函数修改 ==========
# ================================================
def filter_by_keywords(events: List[Dict[str, Any]],
                        critical_events: List[str],
                        important_speakers: List[str],
                        currency_keywords: Dict[str, List[str]], # 旧参数，保留接口但忽略
                        high_impact_keywords: List[str],
                        currency_specific_2star_keywords: Dict[str, List[str]]
                       ) -> List[Dict[str, Any]]:
    """
    按照统一的关键词列表筛选事件(内存中)。
    所有传入的事件（已通过重要性筛选）只要匹配任一重要关键词即被保留。
    """
    # --- 修改点：合并所有关键词为一个统一列表 --- 
    all_keywords = set() # 使用 set 自动去重
    all_keywords.update(critical_events or [])
    all_keywords.update(important_speakers or [])
    all_keywords.update(high_impact_keywords or [])
    # 展开 specific 2 star keywords
    if currency_specific_2star_keywords:
        for kw_list in currency_specific_2star_keywords.values():
            all_keywords.update(kw_list or [])

    unified_keyword_list = list(all_keywords)
    # --- 添加详细日志：打印合并后的关键词列表和数量 ---
    logger.debug(f"Unified Keywords Count: {len(unified_keyword_list)}")
    # logger.debug(f"Unified Keywords List: {sorted(unified_keyword_list)}") # 取消注释以查看完整列表
    # --- 详细日志结束 ---
    if not unified_keyword_list:
        logger.warning("关键词列表为空，将不会基于关键词进行筛选。")
        return events # 如果没有关键词，返回所有事件

    logger.info(f"使用合并后的 {len(unified_keyword_list)} 个关键词进行统一筛选...")
    # --- 修改结束 ---

    filtered_events = []
    # --- 修改点：统一筛选逻辑 --- 
    for event in events:
        event_text = event.get('Event', '')
        # 对所有事件应用统一的关键词匹配 (已修复中文匹配问题)
        if keyword_match(event_text, unified_keyword_list):
            filtered_events.append(event)
    # --- 修改结束 ---

    # 更新日志
    logger.info(f"统一关键词筛选完成: 共筛选出 {len(filtered_events)} / {len(events)} 条事件")

    return filtered_events

# ================================================
# ======= filter_by_keywords 函数修改结束 ========
# ================================================


# --- 辅助函数：获取事件重要性 ---
def get_event_importance(event: Dict[str, Any]) -> int:
    """
    从事件字典中提取重要性级别。
    更新：能够处理 "X星 (描述)" 格式。

    Args:
        event (Dict[str, Any]): 事件字典，应包含 'Importance' 键。

    Returns:
        int: 重要性级别 (1, 2, 或 3)，如果无法确定则返回 0。
    """
    # 修改为优先查找标准PascalCase列名，然后才是兼容性查找
    importance_val = event.get('Importance', event.get('重要性', event.get('importance')))
    if importance_val is None:
        return 0

    # 尝试从 "X星..." 格式提取数字
    if isinstance(importance_val, str):
        match = re.match(r'(\d+)\s*星', importance_val) # 匹配开头的数字和 "星"
        if match:
            try:
                importance = int(match.group(1))
                if 1 <= importance <= 3:
                    return importance
                else:
                    # logger.debug(f"从字符串 '{importance_val}' 提取的重要性值 '{importance}' 超出范围 [1, 3]，视为 0。")
                    return 0
            except (ValueError, IndexError):
                 # logger.debug(f"无法从字符串 '{importance_val}' 中提取有效的星级数字。")
                 return 0 # 提取失败

    # 如果不是 "X星..." 格式，尝试直接转换
    try:
        importance = int(importance_val)
        if 1 <= importance <= 3:
            return importance
        else:
            # logger.debug(f"事件重要性值 '{importance_val}' 超出范围 [1, 3]，视为 0。")
            return 0
    except (ValueError, TypeError):
        # logger.debug(f"无法将事件重要性 '{importance_val}' 解析为整数或从 'X星' 格式提取，视为 0。")
        return 0

# --- 从 src/filters/importance.py 迁移 ---
def filter_by_importance(events: List[Dict[str, Any]], min_importance_threshold: int = 1) -> List[Dict[str, Any]]:
    """
    根据重要性级别筛选事件列表 (内存中)。

    Args:
        events (List[Dict[str, Any]]): 事件字典列表。
        min_importance_threshold (int): 最小重要性阈值 (包含)。例如，设置为 2 会保留 2 星和 3 星事件。

    Returns:
        List[Dict[str, Any]]: 筛选后的事件列表。
    """
    if not (1 <= min_importance_threshold <= 3):
        logger.warning(f"无效的最小重要性阈值: {min_importance_threshold}。应在 [1, 3] 范围内。将使用默认值 1。")
        min_importance_threshold = 1

    logger.info(f"开始根据重要性筛选事件，最小阈值: {min_importance_threshold} 星...")
    filtered_events = [event for event in events if get_event_importance(event) >= min_importance_threshold]
    logger.info(f"重要性筛选完成: {len(filtered_events)} / {len(events)} 条事件满足条件。")
    return filtered_events

# --- 从 src/filters/currency.py 迁移 ---
def filter_by_currencies(events: List[Dict[str, Any]], target_currencies: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    根据目标货币列表筛选事件 (内存中)。

    Args:
        events (List[Dict[str, Any]]): 事件字典列表，应包含 'Currency' 键。
        target_currencies (Optional[List[str]]): 要保留的货币代码列表 (大写)。如果为 None 或空列表，则不进行货币筛选。

    Returns:
        List[Dict[str, Any]]: 筛选后的事件列表。
    """
    if not target_currencies:
        logger.info("未指定目标货币，跳过货币筛选。")
        return events # 不筛选，直接返回原列表

    # 确保目标货币列表是大写的，以便不区分大小写比较
    target_set = set(c.upper() for c in target_currencies)
    logger.info(f"开始根据目标货币筛选事件: {target_set}")

    filtered_events = []
    for event in events:
        # 优先查找标准化的PascalCase列名，然后才是兼容性查找
        event_currency = str(event.get('Currency', event.get('货币', event.get('currency', '')))).upper()
        if event_currency in target_set:
            filtered_events.append(event)

    logger.info(f"货币筛选完成: {len(filtered_events)} / {len(events)} 条事件满足条件。")
    return filtered_events

# --- 从 src/filters/time.py 迁移 (如果需要) ---
def filter_by_time_range(events: List[Dict[str, Any]], start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    根据时间范围筛选事件 (内存中)。时间为北京时间。

    Args:
        events (List[Dict[str, Any]]): 事件字典列表，应包含 'Time' 键 (格式 HH:MM)。
        start_time (Optional[str]): 开始时间字符串 (HH:MM)。
        end_time (Optional[str]): 结束时间字符串 (HH:MM)。

    Returns:
        List[Dict[str, Any]]: 筛选后的事件列表。
    """
    if start_time is None and end_time is None:
        logger.info("未指定时间范围，跳过时间筛选。")
        return events

    start_obj: Optional[dt_time] = None
    end_obj: Optional[dt_time] = None

    try:
        if start_time:
            start_obj = datetime.strptime(start_time, '%H:%M').time()
        if end_time:
            end_obj = datetime.strptime(end_time, '%H:%M').time()

        logger.info(f"开始根据时间范围筛选事件: {start_time or '不限'} - {end_time or '不限'} (北京时间)")

        filtered_events = []
        for event in events:
            # 优先查找标准化的PascalCase列名，然后才是兼容性查找
            event_time_str = event.get('Time', event.get('时间', event.get('time')))
            if not event_time_str or not isinstance(event_time_str, str):
                # logger.debug(f"事件缺少有效时间字段，跳过时间筛选: {event.get('Event', event.get('事件', '未知事件'))}")
                continue

            try:
                # 处理 '全天' 或 'Tentative' 等特殊时间
                if event_time_str.lower() in ['全天', 'tentative', '']:
                    filtered_events.append(event) # 保留全天事件
                    continue

                event_time_obj = datetime.strptime(event_time_str, '%H:%M').time()

                # 执行时间范围比较
                in_range = True
                if start_obj is not None and event_time_obj < start_obj:
                    in_range = False
                if end_obj is not None and event_time_obj >= end_obj: # 结束时间通常是开区间
                    in_range = False

                if in_range:
                    filtered_events.append(event)

            except ValueError:
                logger.warning(f"无法解析事件时间 '{event_time_str}'，跳过此事件的时间筛选: {event.get('Event', event.get('事件', '未知事件'))}")
            except Exception as e:
                logger.error(f"处理事件时间时发生意外错误: {e}", exc_info=True)


        logger.info(f"时间范围筛选完成: {len(filtered_events)} / {len(events)} 条事件满足条件。")
        return filtered_events

    except ValueError as e:
        logger.error(f"解析时间范围 ({start_time}, {end_time}) 时出错: {e}。跳过时间筛选。")
        return events


# --- 辅助函数：检查事件是否在时间窗口内 (北京时间) ---
def is_event_in_beijing_window(event: Dict[str, Any], window_start_bj: datetime, window_end_bj: datetime) -> bool:
    """检查单个事件是否落在给定的北京时间窗口内。"""
    event_date_str = event.get('Date')
    event_time_str = event.get('Time')

    if not event_date_str or not event_time_str or not isinstance(event_time_str, str):
        return False # 缺少日期或时间信息

    # 忽略全天事件
    if event_time_str.lower() in ['全天', 'tentative', '']:
        return False

    try:
        event_dt_naive = datetime.combine(
            datetime.strptime(event_date_str, '%Y-%m-%d').date(),
            datetime.strptime(event_time_str, '%H:%M').time()
        )
        # 假设事件时间已经是北京时间 (UTC+8)
        beijing_tz = pytz.timezone('Asia/Shanghai')
        event_dt_bj = beijing_tz.localize(event_dt_naive)

        # 窗口已经是北京时间，直接比较
        return window_start_bj <= event_dt_bj < window_end_bj
    except ValueError:
        # logger.warning(f"检查窗口时无法解析事件时间 {event_date_str} {event_time_str}")
        return False
    except Exception as e:
        logger.error(f"检查事件是否在窗口内时出错: {e}", exc_info=True)
        return False

# --- 辅助函数：生成单个市场开盘事件 --- (修改)
def _generate_market_open_event(date_str: str, market_type: str, open_time_str: str, market_timezone_str: str) -> Dict[str, Any]: # 添加 market_timezone_str 参数
    """为指定日期和市场类型生成开盘事件字典 (使用中文名称和北京时间)。"""
    # 1. 中文事件名称
    if market_type == "EU":
        event_name = "欧盘开盘"
    elif market_type == "US":
        event_name = "美盘开盘"
    else:
        event_name = f"{market_type} Market Open" # 保留备用

    # 2. 计算北京时间
    beijing_time_str = open_time_str # 默认值
    try:
        market_tz = pytz.timezone(market_timezone_str)
        beijing_tz = pytz.timezone('Asia/Shanghai')
        naive_dt = datetime.combine(datetime.strptime(date_str, '%Y-%m-%d').date(),
                                    datetime.strptime(open_time_str, '%H:%M').time())
        market_dt = market_tz.localize(naive_dt)
        beijing_dt = market_dt.astimezone(beijing_tz)
        beijing_time_str = beijing_dt.strftime('%H:%M')
    except Exception as e:
        logger.warning(f"为 {market_type} 开盘事件 ({date_str}) 计算北京时间时出错: {e}")

    # 3. 计算星期 (中文)
    weekday_str = ""
    try:
        weekday_int = datetime.strptime(date_str, '%Y-%m-%d').weekday()
        weekday_str = WEEKDAY_MAP_ZH.get(weekday_int, "")
    except Exception as e:
        logger.warning(f"为开盘事件 ({date_str}) 计算星期时出错: {e}")


    return {
        'Date': date_str,
        'Weekday': weekday_str, # <--- 添加星期
        'Time': beijing_time_str, # <--- 使用北京时间
        'Zone': 'Asia/Shanghai', # <--- 明确时区为北京时间
        'Currency': 'System',
        'Event': event_name, # <--- 使用中文名称
        'Importance': 1, # 开盘事件重要性设为 1
        'Actual': '',
        'Forecast': '',
        'Previous': '',
        'SourceURL': '',
        'ExtractionTimestamp': datetime.now(pytz.utc).isoformat(), # 记录生成时间
        'MatchedKeywords': '', # 开盘事件无匹配关键词
        'FilterReason': 'Market Open Added' # 添加原因
    }

# --- 核心筛选函数 apply_memory_filters --- (修改调用 _generate_market_open_event)
# ================================================ (修改)
# ====== apply_memory_filters 函数修改开始 ======= (修改)
# ================================================
def apply_memory_filters(
    events: Union[List[Dict[str, Any]], pd.DataFrame],
    min_importance_threshold: int = 1,
    target_currencies: Optional[List[str]] = None,
    use_keywords_filter: bool = False,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    add_market_open: bool = False,
    keywords_critical: Optional[List[str]] = None,
    keywords_speakers: Optional[List[str]] = None,
    keywords_high_impact: Optional[List[str]] = None,
    keywords_2star_specific: Optional[Dict[str, List[str]]] = None
) -> List[Dict[str, Any]]:
    """
    在内存中对事件列表或 DataFrame 应用所有筛选条件。
    更新逻辑：
    1. 应用重要性、货币、时间、关键词筛选。
    2. 如果 add_market_open 为 true，则检查每个相关日期的欧/美盘开盘窗口。
    3. 如果特定开盘窗口内无其他事件，则添加对应的开盘事件。
    4. 对最终结果进行排序。

    Args:
        events (Union[List[Dict[str, Any]], pd.DataFrame]): 要筛选的事件列表或DataFrame。
        min_importance_threshold (int): 最小重要性阈值，默认为1。
        target_currencies (Optional[List[str]]): 目标货币代码列表。
        use_keywords_filter (bool): 是否使用关键词筛选。
        start_time (Optional[str]): 开始时间（HH:MM格式）。
        end_time (Optional[str]): 结束时间（HH:MM格式）。
        add_market_open (bool): 如果结果为空，是否添加市场开盘事件。
        keywords_critical (Optional[List[str]]): 关键事件关键词列表。
        keywords_speakers (Optional[List[str]]): 重要讲话者关键词列表。
        keywords_high_impact (Optional[List[str]]): 高影响力关键词列表。
        keywords_2star_specific (Optional[Dict[str, List[str]]]): 按货币划分的二星事件关键词字典。

    Returns:
        List[Dict[str, Any]]: 经过所有筛选步骤后的事件列表。
    """
    # 初始化为空列表
    events_list: List[Dict[str, Any]] = [] 

    # --- 处理输入类型 ---
    if isinstance(events, pd.DataFrame):
        logger.info("输入为 DataFrame，将转换为字典列表进行处理...")
        
        # 直接使用输入DataFrame，假设列名已经是标准的PascalCase英文名
        events_df_processed = events.copy()
        
        # 检查必需的列
        required_cols = ['Date', 'Time', 'Currency', 'Event', 'Importance']
        missing_cols = [col for col in required_cols if col not in events_df_processed.columns]
        if missing_cols:
            logger.warning(f"输入 DataFrame 缺少必需的PascalCase列: {missing_cols}。筛选可能不准确或失败。")
            logger.info(f"当前可用列: {events_df_processed.columns.tolist()}")
        
        # 转换为字典列表，并将NaN值替换为空字符串
        try:
            events_list = events_df_processed.fillna('').to_dict('records')
            logger.info(f"DataFrame 成功转换为 {len(events_list)} 条记录的列表。")
        except Exception as e:
            logger.error(f"将 DataFrame 转换为字典列表时出错: {e}", exc_info=True)
            return []
            
    elif isinstance(events, list):
        events_list = events
        logger.info(f"输入为列表，包含 {len(events_list)} 条记录。")
    else:
        logger.error(f"无效的输入类型: {type(events)}。请输入 DataFrame 或字典列表。")
        return []

    # --- 后续处理 ---
    if not events_list:
        logger.warning("输入的事件列表为空，无需筛选。")
        return []

    # 执行基础筛选
    # 1. 重要性筛选
    filtered_events_step1 = filter_by_importance(events_list, min_importance_threshold)
    # 2. 货币筛选
    filtered_events_step2 = filter_by_currencies(filtered_events_step1, target_currencies)
    # 3. 时间范围筛选
    filtered_events_step3 = filter_by_time_range(filtered_events_step2, start_time, end_time)
    # 4. 关键词筛选
    filtered_events_step4 = filtered_events_step3
    if use_keywords_filter:
        kw_critical = keywords_critical if keywords_critical is not None else []
        kw_speakers = keywords_speakers if keywords_speakers is not None else []
        kw_high_impact = keywords_high_impact if keywords_high_impact is not None else []
        kw_2star = keywords_2star_specific if keywords_2star_specific is not None else {}

        filtered_events_step4 = filter_by_keywords(
            filtered_events_step3,
            critical_events=kw_critical,
            important_speakers=kw_speakers,
            currency_keywords={}, # 旧参数，保留但未使用
            high_impact_keywords=kw_high_impact,
            currency_specific_2star_keywords=kw_2star
        )

    # 基础筛选后的结果
    filtered_events = filtered_events_step4
    logger.info(f"基础筛选完成，得到 {len(filtered_events)} 条事件。")

    # --- 新增：检查并添加开盘事件 --- 
    if add_market_open and filtered_events: # 只有当配置开启且有事件时才需要检查日期
        logger.info("检查是否需要在开盘窗口添加事件...")
        events_to_add = []
        processed_dates = set() # 处理过的日期，避免重复检查

        # 提取所有涉及的日期
        unique_dates = sorted(list(set(e.get('Date') for e in filtered_events if e.get('Date'))))
        if not unique_dates:
             logger.warning("筛选后事件无有效日期，无法添加开盘事件。")
        else:
            logger.info(f"筛选后事件涉及日期: {unique_dates}")
            beijing_tz = pytz.timezone('Asia/Shanghai')

            for date_str in unique_dates:
                try:
                    current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    # 检查是否是周末 (周六=5, 周日=6)
                    if current_date.weekday() >= 5:
                        logger.debug(f"日期 {date_str} 是周末，跳过添加开盘事件。")
                        continue

                    # -- 检查欧盘窗口 --
                    eu_tz_str = EU_MARKET_TIMEZONE
                    eu_open_time_str = EU_MARKET_OPEN_TIME
                    eu_window_minutes = EU_MARKET_OPEN_WINDOW
                    try:
                        eu_tz = pytz.timezone(eu_tz_str)
                        naive_open_dt_eu = datetime.combine(current_date, datetime.strptime(eu_open_time_str, '%H:%M').time())
                        localized_open_dt_eu = eu_tz.localize(naive_open_dt_eu)
                        window_start_eu = localized_open_dt_eu - timedelta(minutes=eu_window_minutes)
                        window_end_eu = localized_open_dt_eu + timedelta(minutes=eu_window_minutes)
                        # 转换为北京时间
                        window_start_bj_eu = window_start_eu.astimezone(beijing_tz)
                        window_end_bj_eu = window_end_eu.astimezone(beijing_tz)

                        # 检查该日期是否有事件落在欧盘窗口
                        eu_window_has_event = False
                        for event in filtered_events:
                            if event.get('Date') == date_str:
                                if is_event_in_beijing_window(event, window_start_bj_eu, window_end_bj_eu):
                                    eu_window_has_event = True
                                    logger.debug(f"日期 {date_str} 欧盘窗口内发现事件: {event.get('Event')}")
                                    break # 找到一个就够了

                        if not eu_window_has_event:
                            logger.info(f"日期 {date_str} 欧盘开盘窗口 [{window_start_bj_eu.strftime('%H:%M')}-{window_end_bj_eu.strftime('%H:%M')}] 无事件，将添加欧盘开盘事件。")
                            # --- 修改：传递时区字符串 --- 
                            events_to_add.append(_generate_market_open_event(date_str, "EU", eu_open_time_str, eu_tz_str))

                    except Exception as e_eu:
                        logger.error(f"处理日期 {date_str} 欧盘窗口时出错: {e_eu}", exc_info=True)

                    # -- 检查美盘窗口 --
                    us_tz_str = US_MARKET_TIMEZONE
                    us_open_time_str = US_MARKET_OPEN_TIME
                    us_window_minutes = US_MARKET_OPEN_WINDOW
                    try:
                        us_tz = pytz.timezone(us_tz_str)
                        naive_open_dt_us = datetime.combine(current_date, datetime.strptime(us_open_time_str, '%H:%M').time())
                        localized_open_dt_us = us_tz.localize(naive_open_dt_us)
                        window_start_us = localized_open_dt_us - timedelta(minutes=us_window_minutes)
                        window_end_us = localized_open_dt_us + timedelta(minutes=us_window_minutes)
                        # 转换为北京时间
                        window_start_bj_us = window_start_us.astimezone(beijing_tz)
                        window_end_bj_us = window_end_us.astimezone(beijing_tz)

                        # 检查该日期是否有事件落在美盘窗口
                        us_window_has_event = False
                        for event in filtered_events:
                            if event.get('Date') == date_str:
                                if is_event_in_beijing_window(event, window_start_bj_us, window_end_bj_us):
                                    us_window_has_event = True
                                    logger.debug(f"日期 {date_str} 美盘窗口内发现事件: {event.get('Event')}")
                                    break

                        if not us_window_has_event:
                            logger.info(f"日期 {date_str} 美盘开盘窗口 [{window_start_bj_us.strftime('%H:%M')}-{window_end_bj_us.strftime('%H:%M')}] 无事件，将添加美盘开盘事件。")
                             # --- 修改：传递时区字符串 --- 
                            events_to_add.append(_generate_market_open_event(date_str, "US", us_open_time_str, us_tz_str))

                    except Exception as e_us:
                        logger.error(f"处理日期 {date_str} 美盘窗口时出错: {e_us}", exc_info=True)

                except ValueError as date_e:
                    logger.warning(f"无法解析日期字符串 '{date_str}'，跳过该日期的开盘事件检查: {date_e}")

            if events_to_add:
                logger.info(f"共计添加 {len(events_to_add)} 条开盘事件。")
                filtered_events.extend(events_to_add)
            else:
                logger.info("所有检查的开盘窗口均已有事件，未添加新的开盘事件。")
    elif not filtered_events and add_market_open:
         # 如果一开始 filtered_events 就为空，但配置了 add_market_open
         # 沿用之前的逻辑：尝试添加当天的开盘事件 (但现在这个逻辑可能需要调整)
         # 暂时保留警告，因为现在主要逻辑是基于有事件时的日期检查
         logger.warning("筛选结果为空，但配置了添加开盘事件。当前逻辑主要在有事件时检查窗口，此情况下的处理可能需要复核。")
         # TODO: 复核当初始筛选结果为空时，如何确定应该添加哪一天的开盘事件？实时模式可能取当天，历史模式？

    # --- 结束添加开盘事件的逻辑 --- (修改)

    # 最终排序
    logger.info(f"开始对最终的 {len(filtered_events)} 条事件进行排序...")
    sorted_events = sort_events(filtered_events)
    logger.info("事件排序完成。")

    return sorted_events
# ================================================
# ====== apply_memory_filters 函数修改结束 ======= (修改)
# ================================================


# --- 排序函数 (从 src/core/main.py 迁移) ---
def sort_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对事件列表进行排序，主要按日期和时间，次要按重要性。

    Args:
        events (List[Dict[str, Any]]): 事件字典列表。

    Returns:
        List[Dict[str, Any]]: 排序后的事件列表。
    """
    def sort_key(event):
        # 获取日期和时间，处理可能的 None 值和格式
        # 优先使用PascalCase列名，然后是兼容性查找
        date_str = event.get('Date', event.get('日期', event.get('date')))
        time_str = event.get('Time', event.get('时间', event.get('time')))
        importance = get_event_importance(event)

        # 默认日期和时间，用于排序，将无效或缺失的排在后面
        dt_obj = datetime.max

        if date_str and time_str:
            try:
                 # 处理 '全天' 等特殊情况
                 if isinstance(time_str, str) and time_str.lower() == '全天':
                     # 给全天事件一个当天最早的时间用于排序
                     time_obj = dt_time.min
                 else:
                     time_obj = datetime.strptime(str(time_str), '%H:%M').time()

                 dt_obj = datetime.combine(datetime.strptime(str(date_str), '%Y-%m-%d').date(), time_obj)
            except (ValueError, TypeError):
                 logger.debug(f"排序时无法解析日期 '{date_str}' 或时间 '{time_str}'")
                 dt_obj = datetime.max # 解析失败的排在最后

        # 排序键：先按日期时间，然后按重要性（降序，越重要越靠前），最后按事件名
        # 优先使用PascalCase Event列名
        return (dt_obj, -importance, event.get('Event', event.get('事件', event.get('event', ''))))

    logger.info(f"开始对 {len(events)} 条事件进行排序...")
    try:
        sorted_events = sorted(events, key=sort_key)
        logger.info("事件排序完成。")
        return sorted_events
    except Exception as e:
        logger.error(f"排序事件时出错: {e}", exc_info=True)
        return events # 排序失败则返回原列表


# --- 主处理函数 process_events ---
# 这个函数封装了从文件加载、筛选、排序和导出的完整流程

def process_events(
    input_path: str,
    output_path: str,
    mode: str, # <--- 添加 mode 参数
    db_output_path: Optional[str] = None, # 可选的数据库输出路径
    min_importance: int = 1,
    target_currencies: Optional[List[str]] = None,
    # keywords: Optional[List[str]] = None, # 【旧】参数，保留接口但可能不再使用
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    add_market_open: bool = False,
    # 添加用于新关键词逻辑的参数
    keywords_critical: Optional[List[str]] = None,
    keywords_speakers: Optional[List[str]] = None,
    keywords_high_impact: Optional[List[str]] = None,
    keywords_2star_specific: Optional[Dict[str, List[str]]] = None,
    # 添加 use_keywords_filter 参数，并从调用者接收
    use_keywords_filter_from_caller: bool = False
) -> bool:
    """
    处理经济日历事件的完整流程：加载、筛选、排序、导出。

    Args:
        input_path (str): 输入 CSV 文件路径。
        output_path (str): 输出 CSV 文件路径。
        mode (str): 运行模式 ('realtime' 或 'historical')，用于确定数据库表名。
        db_output_path (Optional[str]): 输出 SQLite 数据库路径 (如果提供)。
        min_importance (int): 最小重要性。
        target_currencies (Optional[List[str]]): 目标货币。
        start_time (Optional[str]): 开始时间 (HH:MM)。
        end_time (Optional[str]): 结束时间 (HH:MM)。
        add_market_open (bool): 是否添加开盘事件。
        keywords_critical (Optional[List[str]]): CRITICAL_EVENTS 列表。
        keywords_speakers (Optional[List[str]]): IMPORTANT_SPEAKERS 列表。
        keywords_high_impact (Optional[List[str]]): HIGH_IMPACT_KEYWORDS 列表。
        keywords_2star_specific (Optional[Dict[str, List[str]]]): CURRENCY_SPECIFIC_2STAR_KEYWORDS 字典。
        use_keywords_filter_from_caller (bool): 是否启用关键词筛选（由调用者决定）。

    Returns:
        bool: 处理是否成功。
    """
    # --- 添加：规范化 mode 参数 ---
    mode = str(mode).strip().lower()
    # --- 添加结束 ---
    logger.info(f"====== 开始处理事件文件 (模式: {mode}): {input_path} ======") # 添加 mode 到日志
    # use_kw_filter_flag = bool(keywords_critical or keywords_speakers or keywords_high_impact or keywords_2star_specific) # <-- 不再根据参数计算
    logger.info(f"筛选参数: min_importance={min_importance}, currencies={target_currencies}, "
                f"time_range=[{start_time}-{end_time}], add_market_open={add_market_open}, "
                f"use_keywords_filter={use_keywords_filter_from_caller}") # <-- 使用调用者传递的标志

    try:
        # 1. 加载数据
        input_df = load_input_file(input_path)
        if input_df is None:
            logger.error(f"无法加载输入文件: {input_path}")
            return False
        logger.info(f"成功从 {input_path} 加载 {len(input_df)} 条记录到 DataFrame。")

        # --- 添加诊断日志 ---
        logger.info(f"加载后的 DataFrame 列名: {input_df.columns.tolist()}")
        # --- 诊断日志结束 ---

        # 2. 执行内存筛选
        filtered_events_list = apply_memory_filters(
            events=input_df, # 直接传递 DataFrame
            min_importance_threshold=min_importance,
            target_currencies=target_currencies,
            use_keywords_filter=use_keywords_filter_from_caller, # <-- 直接传递调用者的标志
            start_time=start_time,
            end_time=end_time,
            add_market_open=add_market_open,
            # 传递从 config/keywords.py 加载的列表
            keywords_critical=keywords_critical if keywords_critical is not None else [],
            keywords_speakers=keywords_speakers if keywords_speakers is not None else [],
            keywords_high_impact=keywords_high_impact if keywords_high_impact is not None else [],
            keywords_2star_specific=keywords_2star_specific if keywords_2star_specific is not None else {}
        )

        # 3. 对筛选结果进行排序
        sorted_events_list = sort_events(filtered_events_list)

        # 4. 将排序后的结果转换为 DataFrame 以便导出
        # 注意：列名在 apply_memory_filters 内部可能已经是标准化的
        if not sorted_events_list:
            logger.warning("筛选和排序后没有事件可导出。")
            # 如果没有事件，可以创建一个空的 DataFrame 来覆盖旧文件/表，或直接跳过导出
            output_df = pd.DataFrame(columns=STANDARD_COLUMNS) # 创建空 DataFrame
        else:
            output_df = pd.DataFrame(sorted_events_list)

        # --- 确保导出前的 DataFrame 列符合标准 ---
        # 检查并添加缺失的标准列
        for col in STANDARD_COLUMNS:
            if col not in output_df.columns:
                output_df[col] = "" # 添加缺失列并填充空字符串
        # 重新排序列顺序
        output_df = output_df[STANDARD_COLUMNS]


        # 5. 导出到 CSV
        logger.info(f"准备导出 {len(output_df)} 条事件到 CSV: {output_path}")
        if not export_to_csv(output_df, output_path): # 调用 data.exporter 中的函数
            logger.error("导出 CSV 文件失败。")
            # 是否要在这里返回 False？取决于是否认为 CSV 导出失败是致命的
            # return False

        # 6. 导出到数据库 (如果提供了路径)
        if db_output_path:
            logger.info(f"准备导出 {len(output_df)} 条事件到数据库: {db_output_path}")

            # --- 确定数据库表名 ---
            logger.debug(f"数据库导出：判断模式前，mode 的值为: '{mode}' (类型: {type(mode)})", extra={'markup': True}) # 添加调试日志
            if mode == 'realtime':
                db_table_name = 'events_live'
            elif mode == 'history': 
                db_table_name = 'events_history'
            else:
                # 打印错误日志，包含 mode 的值和类型
                logger.error(f"未知的处理模式 '{mode}' (类型: {type(mode)})，无法确定数据库表名。跳过数据库导出。")
                db_table_name = None

            if db_table_name:
                # --- 为数据库准备 DataFrame ---
                # 数据库需要数值型的重要性，而不是 "N星"
                # apply_memory_filters 返回的字典列表中 Importance 应该是数值
                # 转换为 DataFrame 时应该保持为数值，除非中间有错误
                # 检查 output_df['Importance'] 的类型
                df_for_db = output_df.copy()
                if 'Importance' in df_for_db.columns:
                    # 尝试将 Importance 列转换为整数，处理潜在的字符串或错误
                    original_dtype = df_for_db['Importance'].dtype
                    try:
                        # 尝试从 "N星" 转换回数字 (如果需要)
                        def importance_str_to_int(val):
                            if isinstance(val, str) and val.endswith('星'):
                                try: return int(val[:-1])
                                except: return 0
                            try: return int(val)
                            except: return 0
                        
                        df_for_db['Importance'] = df_for_db['Importance'].apply(importance_str_to_int).astype(int)
                        logger.debug(f"数据库导出：Importance 列已转换为整数。")
                    except Exception as e:
                        logger.warning(f"数据库导出：转换 Importance 列 ({original_dtype}) 为整数时出错: {e}。将尝试保留原样。")
                else:
                    logger.warning("数据库导出：DataFrame 中缺少 Importance 列。")

                # 调用 data.exporter 中的导出函数
                # export_to_sqlite(output_df, db_output_path, table_name="events")
                if not export_to_sqlite(df_for_db, db_output_path, table_name=db_table_name):
                    logger.error(f"导出到数据库表 '{db_table_name}' 失败。")
                    # return False # 同样，数据库导出失败是否致命？

        logger.info(f"====== 事件文件处理成功完成: {input_path} ======")
        return True

    except Exception as e:
        logger.exception(f"处理事件文件 {input_path} 时发生未处理的异常") # 使用 exception 记录完整堆栈
        return False

# --- 可以添加一个简单的命令行接口用于测试 ---
if __name__ == '__main__':
    # 配置基本日志记录以便测试
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("Running logic.py directly for testing...")

    # 示例：创建一个模拟的输入 DataFrame 或列表
    mock_events_data = [
        {'日期': '2024-01-01', '时间': '09:30', '货币': 'USD', '事件': '美国ISM制造业PMI', '重要性': 3, '实际': '50.1', '预测': '50.0', '前值': '49.9'}, # 3星, USD, 匹配二星关键词?
        {'日期': '2024-01-01', '时间': '10:00', '货币': 'EUR', '事件': '欧元区CPI年率初值', '重要性': 3, '实际': '', '预测': '2.8%', '前值': '2.9%'}, # 3星, EUR, 匹配关键事件?
        {'日期': '2024-01-01', '时间': '15:00', '货币': 'GBP', '事件': '英国央行行长贝利讲话', '重要性': 2, '实际': '', '预测': '', '前值': ''}, # 2星, GBP, 不匹配关键词?
        {'日期': '2024-01-01', '时间': '21:30', '货币': 'USD', '事件': '美国初请失业金人数', '重要性': 2, '实际': '', '预测': '210K', '前值': '205K'}, # 2星, USD, 匹配关键词?
        {'日期': '2024-01-02', '时间': '全天', '货币': 'JPY', '事件': '日本银行假日', '重要性': 1, '实际': '', '预测': '', '前值': ''}, # 1星, 过滤掉
        {'日期': '2024-01-02', '时间': '08:00', '货币': 'EUR', '事件': '德国零售销售月率', '重要性': 1, '实际': '', '预测': '0.5%', '前值': '-0.8%'}, # 1星, 过滤掉
        {'日期': '2024-01-02', '时间': '21:30', '货币': 'USD', '事件': '美国非农就业人数变化', '重要性': 3, '实际': '', '预测': '180K', '前值': '150K'}, # 3星, USD, 匹配关键事件?
         {'日期': '2024-01-02', '时间': '23:00', '货币': 'USD', '事件': '美联储主席鲍威尔发表讲话', '重要性': 3, '实际': '', '预测': '', '前值': ''}, # 3星讲话
         {'日期': '2024-01-03', '时间': '10:00', '货币': 'USD', '事件': 'API原油库存周报', '重要性': 2, '实际': '', '预测': '', '前值': ''}, # 2星USD，匹配石油关键词?
         {'日期': '2024-01-03', '时间': '11:00', '货币': 'EUR', '事件': '欧元区服务业PMI终值', '重要性': 2, '实际': '', '预测': '', '前值': ''}, # 2星EUR，匹配关键词?
         {'日期': '2024-01-03', '时间': '11:30', '货币': 'XAU', '事件': '现货黄金 技术面分析', '重要性': 1, '实际': '', '预测': '', '前值': ''}, # 1星, XAU, 过滤掉
    ]
    mock_events_df = pd.DataFrame(mock_events_data)

    # 定义测试用的路径
    test_input_dir = "temp_test_data"
    test_output_dir = "temp_test_output"
    os.makedirs(test_input_dir, exist_ok=True)
    os.makedirs(test_output_dir, exist_ok=True)
    test_input_path = os.path.join(test_input_dir, "mock_input.csv")
    test_output_path = os.path.join(test_output_dir, "mock_output.csv")
    test_db_path = os.path.join(test_output_dir, "mock_output.db")

    # 保存模拟输入数据
    mock_events_df.to_csv(test_input_path, index=False, encoding='utf-8')
    logger.info(f"模拟输入数据已保存到: {test_input_path}")

    # --- 定义筛选参数 (模拟从 config 加载) ---
    test_min_importance = 2
    test_target_currencies = ['USD', 'EUR', 'GBP', 'XAU', 'XTI'] # 包含添加的货币
    test_add_market_open = True # 测试条件化添加
    test_start_time = "08:00" # 测试时间范围
    test_end_time = "22:00"
    # 假设从 config/keywords.py 获取了这些 (需要确保导入成功)
    test_keywords_critical = CRITICAL_EVENTS
    test_keywords_speakers = IMPORTANT_SPEAKERS
    test_keywords_high_impact = HIGH_IMPACT_KEYWORDS
    test_keywords_2star_specific = CURRENCY_SPECIFIC_2STAR_KEYWORDS


    # --- 调用主处理函数 ---
    success = process_events(
        input_path=test_input_path,
        output_path=test_output_path,
        mode='realtime',
        db_output_path=test_db_path,
        min_importance=test_min_importance,
        target_currencies=test_target_currencies,
        keywords=None, # 不再使用旧的 keywords 参数
        start_time=test_start_time,
        end_time=test_end_time,
        add_market_open=test_add_market_open,
        keywords_critical=test_keywords_critical,
        keywords_speakers=test_keywords_speakers,
        keywords_high_impact=test_keywords_high_impact,
        keywords_2star_specific=test_keywords_2star_specific,
        use_keywords_filter_from_caller=True
    )

    if success:
        logger.info(f"测试处理成功完成。结果见: {test_output_path} 和 {test_db_path}")
        # 可以选择读取输出文件进行验证
        if os.path.exists(test_output_path):
            try:
                result_df = pd.read_csv(test_output_path)
                logger.info(f"输出 CSV 内容预览:\n{result_df.head().to_string()}") # 使用 to_string 避免截断
            except pd.errors.EmptyDataError:
                 logger.info("输出 CSV 文件为空。")
            except Exception as read_e:
                 logger.error(f"读取输出 CSV 时出错: {read_e}")
    else:
        logger.error("测试处理失败。")

    # 清理测试文件 (默认注释掉)
    # try:
    #     shutil.rmtree(test_input_dir)
    #     shutil.rmtree(test_output_dir)
    #     logger.info("测试目录已清理。")
    # except Exception as clean_e:
    #     logger.error(f"清理测试目录时出错: {clean_e}")
