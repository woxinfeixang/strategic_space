import pandas as pd
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timedelta # 导入 timedelta
import argparse
import glob # 导入 glob 用于查找文件
from datetime import timezone # 导入 timezone
from pathlib import Path
import sys
import logging
from typing import Optional, Dict, Any, List # 添加类型提示

# --- 添加：确保项目根目录在 sys.path 中 ---
try:
    # process_calendar.py 位于 economic_calendar/economic_calendar_history/scripts/ 下
    # 因此根目录是向上 3 级
    _project_root = Path(__file__).resolve().parents[3]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
        print(f"--- Added {_project_root} to sys.path in process_calendar.py ---")
except IndexError:
    print("ERROR: Could not determine project root directory from process_calendar.py.")
    # 在这种情况下，导入 core.utils 可能会失败，让它自然失败以便调试
    pass
# --- 添加结束 ---

# --- 修改：导入共享配置加载器和日志设置器 --- 
from core.utils import load_app_config, setup_logging, get_absolute_path # <-- 导入 get_absolute_path
from omegaconf import OmegaConf, DictConfig

# --- 项目路径设置 (确保一致性) ---
try:
    # process_calendar.py 位于 economic_calendar/economic_calendar_history/scripts/ 下
    PROJECT_ROOT = Path(__file__).resolve().parents[3] 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except IndexError:
    print("ERROR: Could not determine project root directory from process_calendar.py. Check script location.")
    sys.exit(1)

# --- 修改：使用共享配置和日志设置 --- 
config: Optional[DictConfig] = None
logger = logging.getLogger(__name__) # Default logger initially

try:
    print("DEBUG [process_calendar]: Attempting to load config...") # Debug
    config = load_app_config('economic_calendar/config/processing.yaml')
    print("DEBUG [process_calendar]: Config loaded successfully.") # Debug
    
    print("DEBUG [process_calendar]: Selecting log filename...") # Debug
    log_filename = OmegaConf.select(config, 'logging.calendar_log_filename', default='economic_calendar_fallback.log')
    print(f"DEBUG [process_calendar]: Log filename selected: {log_filename}") # Debug
    
    print("DEBUG [process_calendar]: Accessing config.logging...") # Debug
    log_config = config.logging # Access the logging section
    print("DEBUG [process_calendar]: Accessed config.logging successfully.") # Debug

    print("DEBUG [process_calendar]: Calling setup_logging...") # Debug
    logger = setup_logging(
        log_config=log_config, # Pass the section directly
        log_filename=log_filename, 
        logger_name='CalendarHistoryProcessor' 
    )
    print("DEBUG [process_calendar]: setup_logging call finished.") # Debug

    # --- 精确测试 logger 对象 --- 
    try:
        print("DEBUG [process_calendar]: Attempting logger.debug...")
        logger.debug("--- Logger Test: DEBUG message ---") # 尝试 DEBUG 级别日志
        print("DEBUG [process_calendar]: logger.debug call successful.")
        
        print("DEBUG [process_calendar]: Attempting logger.info...")
        logger.info("已使用 core.utils.setup_logging 配置日志") # 尝试 INFO 级别日志 (会写文件)
        print("DEBUG [process_calendar]: logger.info call successful.")
    except Exception as log_call_e:
        print(f"ERROR [process_calendar]: Exception during logger call: {log_call_e}", file=sys.stderr)
        # 如果这里出错，说明 logger 对象有问题
    # -----------------------------

except Exception as e:
    print(f"ERROR: Failed to load config or setup logging using core.utils: {e}. Using basic logging.", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('CalendarHistoryProcessor_Fallback')
    logger.error("Config load or Logging setup failed!", exc_info=True)
    # 如果配置加载失败，可能无法继续，考虑退出
    # sys.exit(1)

# --- 辅助函数：格式化 Importance 为 N星 --- G
def format_importance_for_csv(imp_num):
    if pd.isna(imp_num):
        return "" # 处理空值
    try:
        num = int(imp_num)
        if num > 0:
            return f"{num}星"
        else:
            # return "0星" # 如果希望 0 也显示为 0星
            return "" # 否则 0 星显示为空字符串
    except (ValueError, TypeError):
        return str(imp_num) # 如果不是有效数字，返回原始值

# --- 修改：主解析函数接收配置 ---
def parse_html_to_dataframe(html_path: str, config: DictConfig) -> Optional[pd.DataFrame]:
    """
    解析 Investing.com 经济日历 HTML 文件，提取数据到 pandas DataFrame。
    现在从配置中读取 HTML 解析参数。
    """
    logger.info(f"开始解析 HTML 文件: {html_path}")
    try:
        # --- 从配置读取 HTML 解析参数 ---
        parsing_cfg = config.get('economic_calendar', {}).get('html_parsing', {})
        target_table_id = parsing_cfg.get('target_table_id', 'economicCalendarData')
        date_row_class = parsing_cfg.get('date_row_class', 'theDay')
        importance_selector = parsing_cfg.get('importance_element_selector', 'td span[title]')
        # fallback_importance = parsing_cfg.get('fallback_importance_text', True)
        col_idx = parsing_cfg.get('col_idx', {
            'time': 0, 'currency': 1, 'importance': 2, 'event': 3,
            'actual': 4, 'forecast': 5, 'previous': 6
        })
        # 将字典键转为小写以防万一
        col_idx = {k.lower(): v for k, v in col_idx.items()}

        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        logger.error(f"文件未找到: {html_path}")
        return None
    except KeyError as e:
        logger.error(f"访问 HTML 解析配置时出错，缺少键: {e}")
        return None
    except Exception as e:
        logger.error(f"读取文件或配置时出错: {e}")
        return None

    logger.info("使用 lxml 解析 HTML...")
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as bs_error:
        logger.error(f"初始化 BeautifulSoup 时出错: {bs_error}")
        return None

    logger.info(f"尝试查找 ID 为 '{target_table_id}' 的表格...")
    try:
        calendar_table = soup.find('table', {'id': target_table_id})
    except Exception as find_error:
        logger.error(f"查找表格时出错: {find_error}")
        return None

    if not calendar_table:
        logger.error(f"无法在 HTML 中找到 ID 为 '{target_table_id}' 的表格。请检查配置 economic_calendar.html_parsing.target_table_id")
        return None
    logger.info("表格找到，开始遍历行...")

    data = []
    current_date_str = None
    current_weekday_str = None
    processed_rows = 0
    data_rows_found = 0

    rows = calendar_table.find_all('tr')
    logger.debug(f"共找到 {len(rows)} 行 <tr>。") # 改为 debug

    for i, row in enumerate(rows):
        processed_rows += 1
        # 尝试识别日期/星期标题行
        header_cell = row.find('td', class_=date_row_class)
        if header_cell:
             full_text = header_cell.get_text(strip=True)
             match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)\s*(星期.)', full_text)
             if match:
                 current_date_str = match.group(1)
                 current_weekday_str = match.group(2)
             else:
                 logger.warning(f"第 {i+1} 行: 找到 class='{date_row_class}' 的单元格，但无法匹配日期格式: {full_text}")
             continue

        # 识别数据行
        cells = row.find_all('td')
        min_expected_cols = max(col_idx.values()) + 1

        if len(cells) < min_expected_cols or not current_date_str:
            continue

        try:
            time_val = cells[col_idx['time']].get_text(strip=True)
            currency_cell = cells[col_idx['currency']]
            currency_code = currency_cell.get_text(strip=True)

            importance_cell = cells[col_idx['importance']]
            importance_text = importance_cell.get_text(strip=True)
            importance_val = 0 # 默认值为 0
            if importance_text == '假日':
                importance_val = 0 # 将"假日"也视为 0 星
            else:
                # 计算 class="grayFullBullishIcon" 的 <i> 标签数量
                filled_stars = importance_cell.find_all('i', class_='grayFullBullishIcon')
                importance_val = len(filled_stars) # 数量即为重要性星级

            event_val = cells[col_idx['event']].get_text(strip=True)
            actual_val = cells[col_idx['actual']].get_text(strip=True)
            forecast_val = cells[col_idx['forecast']].get_text(strip=True)
            previous_val = cells[col_idx['previous']].get_text(strip=True)

            data.append({
                'Date': current_date_str,
                'Weekday': current_weekday_str,
                'Time': time_val,
                'Currency': currency_code,
                'Importance': importance_val, # 现在是数值 0, 1, 2, 3
                'Event': event_val,
                'Actual': actual_val.strip(),
                'Forecast': forecast_val.strip(),
                'Previous': previous_val.strip()
            })
            data_rows_found += 1
        except IndexError:
             logger.warning(f"第 {i+1} 行: 处理单元格时索引越界。可能是 col_idx 配置错误或 HTML 结构异常。单元格数: {len(cells)}")
        except Exception as e:
            logger.warning(f"第 {i+1} 行: 处理时发生未知错误: {e}。行内容:\n{row.prettify()}\n")

    logger.info(f"行遍历完成。共处理 {processed_rows} 行，提取到 {data_rows_found} 条有效数据记录。")

    if not data:
        logger.error("未能从表格中提取任何有效数据记录。请检查 HTML 文件内容和脚本配置。")
        return None

    df = pd.DataFrame(data)

    logger.info("开始数据清理...")
    try:
        # 转换日期格式
        df['Date'] = pd.to_datetime(df['Date'], format='%Y年%m月%d日').dt.strftime('%Y-%m-%d')
        logger.debug("日期格式已转换为 YYYY-MM-DD。")
    except Exception as e:
        logger.warning(f"日期格式转换失败: {e}。将保留原始格式。")

    logger.info("数据清理完成。")
    return df

def get_sort_key_from_filename(filename):
    """ 从 HTML 文件名中提取用于排序的日期 YYYYMMDD """
    match = re.search(r'(\d{8})\s*-\s*\d{8}', filename)
    if match:
        return match.group(1) # 返回 YYYYMMDD 字符串
    else:
        logger.warning(f"无法从文件名 '{filename}' 提取排序日期，将使用文件名本身排序。")
        return filename # 无法解析则按原文件名排序

def get_year_month_from_filename(filename):
    """ 从 HTML 文件名中提取年份和月份 YYYY_MM """
    match = re.search(r'(\d{4})(\d{2})\d{2}\s*-\s*\d{8}', filename)
    if match:
        year = match.group(1)
        month = match.group(2)
        return year, month
    else:
        logger.warning(f"无法从文件名 '{filename}' 中按 'YYYYMMDD-YYYYMMDD' 格式提取年月。")
        return None, None

# --- 修改：主处理函数，现在只解析并返回原始 DataFrame ---
def process_html_file(html_path: str, config: DictConfig) -> Optional[pd.DataFrame]: # 返回原始 DataFrame
    """处理单个 HTML 文件：仅解析 -> 返回原始 DataFrame。不进行筛选和数据库保存。"""
    logger.info(f"--- 开始处理文件: {html_path} ---")
    # 1. 解析 HTML
    df_parsed = parse_html_to_dataframe(html_path, config)
    if df_parsed is None or df_parsed.empty:
        logger.warning(f"解析 HTML 文件 {html_path} 未产生有效数据。")
        return None   # 返回 None 表示无数据或解析失败

    # 2. 不再进行筛选
    # df_filtered = filter_dataframe(df_parsed, config)
    # ... (移除筛选逻辑调用)

    # 3. 不再保存到数据库
    # save_to_db(...)

    logger.info(f"--- 文件解析完成: {html_path}，原始 {len(df_parsed)} 条 ---")
    return df_parsed

# --- 修改：主函数，添加日期过滤和移除 CSV 输出 ---
def main():
    # --- 移除或注释掉不再需要的 argparse --- 
    # parser = argparse.ArgumentParser(description="解析历史经济日历 HTML 文件，合并并保存为原始 CSV。")
    # parser.add_argument("--config-path", default="config", help="配置目录的相对路径")
    # parser.add_argument("--config-name", default="economic_calendar", help="主配置文件名 (无扩展名)")
    # args = parser.parse_args()

    try:
        print("DEBUG [main]: Loading config inside main...")
        config = load_app_config("economic_calendar/config/processing.yaml")
        if config is None:
            logger.error("无法加载应用配置，退出。")
            sys.exit(1)
        logger.info("应用配置已成功加载。")
        print("DEBUG [main]: Config loaded.")

        print("DEBUG [main]: Checking necessary config paths...")
        if not OmegaConf.select(config, "economic_calendar.paths.raw_history_dir") or \
           not OmegaConf.select(config, "economic_calendar.paths.processed_history_dir"): 
            logger.error("配置 economic_calendar.yaml 中缺少必要的原始历史目录或处理后历史目录。请检查配置文件。")
            sys.exit(1)
        print("DEBUG [main]: Necessary config paths check passed.")

    except Exception as e:
        # logger might not be fully configured if load_app_config failed earlier
        print(f"ERROR [main]: 加载或验证配置时发生错误: {e}", file=sys.stderr) 
        logger.exception(f"加载或验证配置时发生错误: {e}")
        sys.exit(1)

    try:
        print("DEBUG [main]: Getting absolute paths...")
        input_dir_path = get_absolute_path(config, "economic_calendar.paths.raw_history_dir")
        output_dir_path = get_absolute_path(config, "economic_calendar.paths.processed_history_dir")

        if not input_dir_path or not output_dir_path:
             logger.error("无法从配置中解析输入或输出目录路径。请检查 economic_calendar.paths 下的 raw_history_dir 和 processed_history_dir")
             return

        logger.info(f"输入目录 (原始HTML): {input_dir_path}")
        logger.info(f"输出目录 (合并原始CSV): {output_dir_path}")

        # --- 新增：获取输出文件名 --- 
        try:
            processed_csv_filename = OmegaConf.select(config, "economic_calendar.files.processed_history_csv", default=None)
            if not processed_csv_filename:
                logger.error("配置中缺少 economic_calendar.files.processed_history_csv 文件名。")
                return
            output_file_path = output_dir_path / processed_csv_filename
            logger.info(f"完整输出文件路径: {output_file_path}")
        except Exception as e:
            logger.error(f"获取输出文件名或构建路径时出错: {e}", exc_info=True)
            return
        # --- 结束新增 ---

        # 确保输出目录存在
        output_dir_path.mkdir(parents=True, exist_ok=True)

    except KeyError as e:
        logger.error(f"访问配置路径时出错，缺少键: {e}")
        return
    except Exception as e:
        logger.error(f"获取路径或创建目录时出错: {e}", exc_info=True) # 打印 traceback
        return

    print("DEBUG [main]: Finding HTML files...")
    html_files = glob.glob(os.path.join(input_dir_path, '*.html'))
    if not html_files:
        logger.warning(f"在目录 '{input_dir_path}' 中未找到任何 HTML 文件。") 
        sys.exit(0) # Exit gracefully if no files found
    print(f"DEBUG [main]: Found {len(html_files)} HTML files.")

    print("DEBUG [main]: Sorting HTML files...")
    html_files.sort(key=get_sort_key_from_filename)
    logger.info(f"找到 {len(html_files)} 个 HTML 文件，将按时间顺序处理。")
    print("DEBUG [main]: HTML files sorted.")

    all_data = []
    print("DEBUG [main]: Starting HTML file processing loop...")
    for i, html_file in enumerate(html_files):
        print(f"DEBUG [main]: Processing file {i+1}/{len(html_files)}: {html_file}")
        df_raw = process_html_file(html_file, config)
        if df_raw is not None and not df_raw.empty:
            all_data.append(df_raw)
        else:
             logger.warning(f"文件 {html_file} 未能解析或返回空数据，已跳过。")
    print("DEBUG [main]: HTML file processing loop finished.")

    if not all_data:
        logger.error("所有 HTML 文件都未能成功解析或提取数据。无法生成合并文件。")
        sys.exit(1)
    print("DEBUG [main]: Data extracted from HTML files.")

    try:
        print("DEBUG [main]: Concatenating DataFrames...")
        all_data_df = pd.concat(all_data, ignore_index=True)
        print("DEBUG [main]: DataFrames concatenated.")

        print("DEBUG [main]: Sorting and dropping duplicates...")
        try:
            all_data_df['DateTimeUTC'] = pd.to_datetime(all_data_df['Date'] + ' ' + all_data_df['Time'], errors='coerce')
            all_data_df = all_data_df.sort_values(by='DateTimeUTC').drop(columns=['DateTimeUTC'])
        except Exception as dt_err:
            logger.warning(f"根据日期时间排序时出错: {dt_err}。将尝试仅按日期排序。")
            try:
                all_data_df['DateObj'] = pd.to_datetime(all_data_df['Date'], errors='coerce')
                all_data_df = all_data_df.sort_values(by='DateObj').drop(columns=['DateObj'])
            except Exception as date_err:
                logger.error(f"仅按日期排序也失败: {date_err}。数据将按合并顺序排列。")
        original_count = len(all_data_df)
        all_data_df = all_data_df.drop_duplicates(subset=['Date', 'Time', 'Currency', 'Event'], keep='first')
        duplicates_removed = original_count - len(all_data_df)
        logger.info(f"合并完成。总共有 {len(all_data_df)} 条唯一原始事件记录 (移除了 {duplicates_removed} 条重复记录)。")
        print("DEBUG [main]: Sorting and deduplication finished.")
    except Exception as e:
        logger.exception(f"合并 DataFrame 时出错: {e}")
        sys.exit(1)

    try:
        print(f"DEBUG [main]: Writing processed data to CSV: {output_file_path}")
        logger.info(f"将合并后的处理数据 ({len(all_data_df)} 条) 写入到: {output_file_path}")
        all_data_df.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        logger.info("合并处理数据 CSV 文件写入成功。")
        print("DEBUG [main]: CSV writing successful.")
    except Exception as e:
        logger.exception(f"无法将合并的处理数据写入 CSV 文件: {e}")
        sys.exit(1)

    logger.info("历史 HTML 解析和数据处理流程结束。")
    print("DEBUG [main]: Script finished successfully.") # Add final success message

if __name__ == "__main__":
    main() 