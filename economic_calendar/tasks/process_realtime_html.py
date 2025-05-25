#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
处理实时下载的 HTML 文件 (realtime_calendar.html)，
使用 BeautifulSoup 解析，应用与历史数据处理相同的初步逻辑 (get_text(strip=True))，
并将结果保存为中间 CSV 文件 (processed_live.csv)。
"""
import pandas as pd
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timedelta
import argparse
from pathlib import Path
import sys
import logging
from typing import Optional, Dict, Any, List

# --- 添加：确保项目根目录在 sys.path 中 ---
try:
    # process_realtime_html.py 位于 economic_calendar/tasks/ 下
    # 因此根目录是向上 2 级
    _project_root = Path(__file__).resolve().parents[2]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
        print(f"--- Added {_project_root} to sys.path in process_realtime_html.py ---")
except IndexError:
    print("ERROR: Could not determine project root directory from process_realtime_html.py.")
    pass
# --- 添加结束 ---

# --- 导入共享配置加载器和日志设置器 ---
from core.utils import load_app_config, setup_logging, get_absolute_path
from omegaconf import OmegaConf, DictConfig

# --- 日志和配置设置 ---
config: Optional[DictConfig] = None
logger = logging.getLogger(__name__) # Default logger initially

try:
    config = load_app_config('economic_calendar/config/processing.yaml')
    # 使用一个新的日志文件名，或者复用 calendar_log_filename? 暂时复用
    log_filename = OmegaConf.select(config, 'logging.calendar_log_filename', default='economic_calendar_fallback.log')
    logger = setup_logging(
        log_config=config.logging,
        log_filename=log_filename,
        logger_name='RealtimeHTMLProcessor'
    )
    logger.info("实时 HTML 处理脚本日志已配置")
except Exception as e:
    print(f"ERROR: Failed to load config or setup logging for RealtimeHTMLProcessor: {e}. Using basic logging.", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('RealtimeHTMLProcessor_Fallback')
    logger.error("Config load or Logging setup failed!", exc_info=True)
    # 考虑退出
    # sys.exit(1)

# --- 从 process_calendar.py 复制并调整 HTML 解析函数 ---
def parse_html_to_dataframe(html_path: str, config: DictConfig) -> Optional[pd.DataFrame]:
    """
    解析 Investing.com 经济日历 HTML 文件（现在只包含表格），提取数据到 pandas DataFrame。
    从配置中读取 HTML 解析参数。与 process_calendar.py 中的逻辑保持一致。
    """
    logger.info(f"开始解析实时 HTML 文件 (仅含表格): {html_path}")
    try:
        parsing_cfg = config.get('economic_calendar', {}).get('html_parsing', {})
        target_table_id = parsing_cfg.get('target_table_id', 'economicCalendarData')
        date_row_class = parsing_cfg.get('date_row_class', 'theDay')
        col_idx = parsing_cfg.get('col_idx', {
            'time': 0, 'currency': 1, 'importance': 2, 'event': 3,
            'actual': 4, 'forecast': 5, 'previous': 6
        })
        col_idx = {k.lower(): v for k, v in col_idx.items()}

        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            # --- 调试打印：HTML 内容 (少量) ---
            print(f"DEBUG [Parser]: Read HTML content (first 500 chars):\n{html_content[:500]}\n...")
            # --- 调试打印结束 ---
    except FileNotFoundError:
        logger.error(f"实时 HTML 文件未找到: {html_path}")
        return None
    except KeyError as e:
        logger.error(f"访问 HTML 解析配置时出错，缺少键: {e}")
        return None
    except Exception as e:
        logger.error(f"读取实时 HTML 文件或配置时出错: {e}")
        return None

    logger.info("使用 lxml 解析 HTML...")
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as bs_error:
        logger.error(f"初始化 BeautifulSoup 时出错: {bs_error}")
        return None

    # --- 恢复：通过 ID 查找表格 --- 
    logger.info(f"尝试查找 ID 为 '{target_table_id}' 的表格...") # 使用配置中的 target_table_id
    try:
        calendar_table = soup.find('table', {'id': target_table_id})
    except Exception as find_error:
        logger.error(f"查找表格时出错: {find_error}")
        return None
    # print(f"DEBUG [Parser]: Trying to find the first <table> tag in the input HTML...")
    # calendar_table = soup.find('table') # 撤销之前的错误修改
    # --- 恢复结束 ---

    if not calendar_table:
        logger.error(f"无法在输入的 HTML 中找到 ID 为 '{target_table_id}' 的表格。文件内容可能有误。")
        print(f"ERROR [Parser]: Could not find table with id='{target_table_id}' in the input HTML.")
        return None
        
    # --- 调试打印：找到的表格对象 ---
    # print(f"DEBUG [Parser]: Found table object: {str(calendar_table)[:200]}...") # 可以暂时注释掉
    # --- 调试打印结束 ---
    
    logger.info("表格找到，开始遍历行...")

    data = []
    current_date_str = None
    current_weekday_str = None
    processed_rows = 0
    data_rows_found = 0

    rows = calendar_table.find_all('tr')
    # --- 调试打印：找到的行数 ---
    print(f"DEBUG [Parser]: Found {len(rows)} <tr> rows in the table.")
    # --- 调试打印结束 ---

    for i, row in enumerate(rows):
        processed_rows += 1
        # --- 调试打印：当前行 HTML ---
        print(f"DEBUG [Parser]: Processing row {i+1}: {str(row)}")
        # --- 调试打印结束 ---
        
        header_cell = row.find('td', class_=date_row_class)
        if header_cell:
             # --- 调试打印：进入日期行逻辑 ---
             print(f"DEBUG [Parser]: Row {i+1} identified as date row (found td.{date_row_class}).")
             # --- 调试打印结束 ---
             full_text = header_cell.get_text(strip=True)
             match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)\s*(星期.)', full_text)
             if match:
                 current_date_str = match.group(1)
                 current_weekday_str = match.group(2)
                 # --- 调试打印：提取的日期 ---
                 print(f"DEBUG [Parser]: Extracted date: {current_date_str}, weekday: {current_weekday_str}")
                 # --- 调试打印结束 ---
                 logger.debug(f"找到日期行: {current_date_str} ({current_weekday_str})")
             else:
                 logger.warning(f"第 {i+1} 行: 找到 class='{date_row_class}' 但无法匹配日期格式: {full_text}")
             continue # 日期行不包含数据

        # 识别数据行
        cells = row.find_all('td')
        min_expected_cols = max(col_idx.values()) + 1 if col_idx else 7
        
        # --- 调试打印：进入数据行逻辑或跳过 ---
        if len(cells) < min_expected_cols or not current_date_str:
            print(f"DEBUG [Parser]: Skipping row {i+1}. Cells: {len(cells)}/{min_expected_cols}, HasDate: {bool(current_date_str)}")
            continue
        else:
            print(f"DEBUG [Parser]: Row {i+1} identified as data row (Cells: {len(cells)}/{min_expected_cols}, HasDate: {bool(current_date_str)}). Attempting to extract data...")
        # --- 调试打印结束 ---

        try:
            time_val = cells[col_idx['time']].get_text(strip=True)
            currency_cell = cells[col_idx['currency']]
            currency_code = currency_cell.get_text(strip=True)
            importance_cell = cells[col_idx['importance']]
            importance_val = 0
            importance_text = importance_cell.get_text(strip=True)
            if importance_text == '假日':
                importance_val = 0
            else:
                filled_stars = importance_cell.find_all('i', class_='grayFullBullishIcon')
                importance_val = len(filled_stars)
            event_val = cells[col_idx['event']].get_text(strip=True)
            actual_val = cells[col_idx['actual']].get_text(strip=True)
            forecast_val = cells[col_idx['forecast']].get_text(strip=True)
            previous_val = cells[col_idx['previous']].get_text(strip=True)
            
            # --- 调试打印：提取的数据 ---
            print(f"DEBUG [Parser]: Row {i+1} Extracted - Time: '{time_val}', Currency: '{currency_code}', ImpStars: {importance_val}, Event: '{event_val}', Actual: '{actual_val}', Forecast: '{forecast_val}', Previous: '{previous_val}'")
            # --- 调试打印结束 ---

            # --- 重要性文本格式化 ---
            importance_formatted_text = ""
            if importance_val == 0:
                importance_formatted_text = f"{importance_val}星"
            elif importance_val == 1:
                importance_formatted_text = f"{importance_val}星 (重要性较低)"
            elif importance_val == 2:
                importance_formatted_text = f"{importance_val}星 (重要性中等)"
            elif importance_val == 3:
                importance_formatted_text = f"{importance_val}星 (重要性较高)"
            else: # 处理 > 3 或其他异常情况
                importance_formatted_text = f"{importance_val}星 (重要性未知)"
            # --- 格式化结束 ---

            data.append({
                'Date': current_date_str,
                'Weekday': current_weekday_str,
                'Time': time_val,
                'Currency': currency_code,
                'Importance': importance_val, # <-- 改回保存数值型的 importance_val
                'Event': event_val, # 保存 strip 处理后的文本
                'Actual': actual_val,
                'Forecast': forecast_val,
                'Previous': previous_val
            })
            data_rows_found += 1
        except IndexError:
             logger.warning(f"第 {i+1} 行: 处理单元格时索引越界。可能是 col_idx 配置错误或 HTML 结构异常。单元格数: {len(cells)}")
             # --- 调试打印：索引错误 ---
             print(f"ERROR [Parser]: IndexError on row {i+1}. Cells: {len(cells)}, Max Index Needed: {max(col_idx.values())}")
             # --- 调试打印结束 ---
        except Exception as e:
            logger.warning(f"第 {i+1} 行: 处理时发生未知错误: {e}。行内容 (部分):\n{str(row)[:200]}\n")
            # --- 调试打印：其他错误 ---
            print(f"ERROR [Parser]: Exception on row {i+1}: {e}")
            # --- 调试打印结束 ---

    logger.info(f"行遍历完成。共处理 {processed_rows} 行，提取到 {data_rows_found} 条有效数据记录。")

    if not data:
        logger.warning("未能从实时 HTML 表格中提取任何有效数据记录。")
        return None # 返回 None 而不是空 DataFrame? 或者返回空 DataFrame

    df = pd.DataFrame(data)

    logger.info("开始数据清理 (主要是日期格式)...")
    try:
        df['Date'] = pd.to_datetime(df['Date'], format='%Y年%m月%d日', errors='coerce').dt.strftime('%Y-%m-%d')
        # 处理转换失败的日期 (变成 NaT)
        invalid_dates = df['Date'].isna().sum()
        if invalid_dates > 0:
             logger.warning(f"有 {invalid_dates} 条记录的日期格式转换失败，将被置空。")
             df['Date'] = df['Date'].fillna('') # 将 NaT 替换为空字符串或其他标记

        logger.debug("日期格式已转换为 YYYY-MM-DD。")
    except Exception as e:
        logger.warning(f"日期格式转换失败: {e}。将保留原始格式或 NaT。")

    logger.info("数据清理完成。")
    return df
# --- 解析函数结束 ---

def main():
    """主函数：读取实时 HTML，解析，保存为中间 CSV"""
    if not config:
        print("ERROR: 配置未加载，无法执行处理。")
        logger.error("配置未加载，无法执行处理。")
        sys.exit(1)

    logger.info("--- 开始处理实时 HTML 文件 ---")

    # 1. 获取输入 HTML 文件路径
    input_dir_path = get_absolute_path(config, "economic_calendar.paths.raw_live_dir")
    input_filename = OmegaConf.select(config, "economic_calendar.files.raw_live_html", default="realtime_calendar.html")
    input_html_path = input_dir_path / input_filename if input_dir_path else None

    if not input_html_path or not input_html_path.is_file():
        logger.error(f"输入的实时 HTML 文件未找到: {input_html_path}")
        print(f"ERROR: 输入的实时 HTML 文件未找到: {input_html_path}")
        sys.exit(1)

    # 2. 解析 HTML
    parsed_df = parse_html_to_dataframe(str(input_html_path), config)

    if parsed_df is None or parsed_df.empty:
        logger.error("解析实时 HTML 后未能生成有效的 DataFrame。处理终止。")
        print("ERROR: 解析实时 HTML 后未能生成有效的 DataFrame。处理终止。")
        # 根据需要决定是否创建空的输出文件
        # sys.exit(1) # 暂时不退出，允许后续步骤处理空文件的情况
    else:
         logger.info(f"成功从实时 HTML 解析出 {len(parsed_df)} 条记录。")

    # 3. 获取输出 CSV 文件路径
    output_dir_path = get_absolute_path(config, "economic_calendar.paths.processed_live_dir")
    if not output_dir_path:
        logger.error("无法从配置解析处理后实时数据目录路径 (processed_live_dir)，无法保存 CSV。")
        print("ERROR: 无法从配置解析处理后实时数据目录路径 (processed_live_dir)")
        sys.exit(1)

    output_filename = OmegaConf.select(config, "economic_calendar.files.processed_live_csv", default="processed_live.csv")
    output_csv_path = output_dir_path / output_filename
    os.makedirs(output_dir_path, exist_ok=True) # 确保目录存在

    # 4. 保存为 CSV
    try:
        # 如果解析失败或为空，创建一个空的或只包含头部的 CSV？
        # 当前逻辑：如果 df 为 None 或 empty，不执行保存
        if parsed_df is not None and not parsed_df.empty:
             # --- 确保只选择和排序需要的列 --- 
             fieldnames = ["Date", "Weekday", "Time", "Currency", "Importance", "Event", "Actual", "Forecast", "Previous"]
             # 检查 parsed_df 是否包含所有需要的列
             missing_cols = [col for col in fieldnames if col not in parsed_df.columns]
             if missing_cols:
                  logger.error(f"解析后的 DataFrame 缺少必要的列: {missing_cols}，无法保存。")
                  # 可以选择退出或抛出异常
                  sys.exit(1) 
             
             # 只选择明确定义的列，并使用 .copy() 防止 SettingWithCopyWarning
             output_df = parsed_df[fieldnames].copy()
             # --- 选择结束 ---

             encoding = OmegaConf.select(config, "economic_calendar.export.csv_encoding", default="utf-8")
             output_df.to_csv(output_csv_path, index=False, encoding=encoding)
             logger.info(f"处理后的实时数据已保存到中间 CSV: {output_csv_path}")
             print(f"处理后的实时数据已保存到中间 CSV: {output_csv_path}")
        else:
             logger.warning("解析后的 DataFrame 为空，不保存中间 CSV 文件。")
             # 创建一个空文件或只含表头的文件？
             # touch a file or write header?
             # with open(output_csv_path, 'w', encoding='utf-8') as f:
             #     f.write(','.join(fieldnames) + '\\n')
             # logger.info(f"创建了空的中间 CSV 文件: {output_csv_path}")

    except Exception as e:
        logger.error(f"保存中间 CSV 文件时出错: {e}", exc_info=True)
        print(f"ERROR: 保存中间 CSV 文件时出错: {e}")
        sys.exit(1)

    logger.info("--- 实时 HTML 文件处理完成 ---")

if __name__ == "__main__":
    main() 