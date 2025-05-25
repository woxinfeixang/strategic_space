#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专门用于经济日历数据筛选的脚本步骤。

接收一个输入 CSV 文件路径和一个输出 CSV 文件路径作为参数，
加载统一配置，应用筛选规则，并将结果写入输出文件。
不执行数据库写入操作。
"""
import pandas as pd
import argparse
import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from omegaconf import DictConfig, OmegaConf

# --- 项目路径设置 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2] # economic_calendar/tasks/filter_data_step.py -> economic_calendar -> project_root
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except IndexError:
    print("ERROR: Could not determine project root directory from filter_data_step.py. Check script location.")
    sys.exit(1)

# 从core模块导入共享工具函数（移到sys.path设置之后）
from core.utils import load_app_config, get_absolute_path
from core.utils import setup_logging # <-- Import setup_logging from core.utils

# --- 导入共享工具和筛选逻辑 ---
try:
    # 假设筛选逻辑封装在 event_filter.logic 中
    from economic_calendar.event_filter.logic import apply_memory_filters # <--- 正确导入共享逻辑
    from economic_calendar.data.loader import load_input_file # 确保导入 load_input_file

    # 日志配置（如果需要单独配置）
    # from economic_calendar.utils.logging_config import setup_logging # <-- Remove this incorrect import
except ImportError as e:
    # 提供更明确的错误信息
    print(f"ERROR: Failed to import required modules: {e}. "
          "Ensure project structure is correct and dependencies installed.")
    sys.exit(1)

# 设置日志 (使用从 core.utils 导入的 setup_logging)
# Load config earlier to use for logging setup
cfg_for_log = load_app_config("economic_calendar/config/processing.yaml") 
log_dir_cfg = get_absolute_path(cfg_for_log, "paths.log_dir") # Use config to get log dir
if log_dir_cfg:
    log_dir = log_dir_cfg
    log_dir.mkdir(exist_ok=True)
else:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    print(f"Warning: Log directory not found in config, using default: {log_dir}")

# Use a specific logger name for this script
logger_name = "FilterDataStep"
log_filename_cfg = OmegaConf.select(cfg_for_log, "logging.filter_data_step_log_filename", default=f"{logger_name.lower()}.log")
logger = setup_logging(
    log_config=cfg_for_log.logging if cfg_for_log else None, 
    log_filename=log_filename_cfg,
    logger_name=logger_name
)

if logger is None:
    # Fallback if setup_logging fails
    print(f"Failed to setup logging using core.utils in {log_dir}. Using basic logging.")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(logger_name) # Still use the specific name

def main():
    parser = argparse.ArgumentParser(description="Filter economic calendar data based on configuration.")
    parser.add_argument("--input-file", type=str, required=True, help="Path to the input CSV file (e.g., raw live data).")
    parser.add_argument("--output-file", type=str, required=True, help="Path to save the filtered output CSV file.")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    logger.info(f"开始筛选步骤...")
    logger.info(f"输入文件: {input_path}")
    logger.info(f"输出文件: {output_path}")

    # 检查输入文件是否存在
    if not input_path.is_file():
        logger.error(f"输入文件未找到: {input_path}")
        sys.exit(1)

    # 加载配置
    config = load_app_config("economic_calendar/config/processing.yaml")
    if config is None:
        logger.error("无法加载配置，脚本终止。")
        sys.exit(1)

    # 准备调用 apply_memory_filters 所需的参数
    filter_cfg = config.get('economic_calendar', {}).get('filtering', {})
    currencies = config.get('economic_calendar', {}).get('currencies', [])
    keywords_cfg = config.get('economic_calendar', {}).get('keywords_config', {})
    
    min_importance = filter_cfg.get('min_importance', 0)
    target_currencies_list = currencies # 使用从配置加载的列表
    use_keywords = filter_cfg.get('use_keywords_filter', False)
    start_time_str = filter_cfg.get('start_time') if filter_cfg.get('time_filter_enabled') else None
    end_time_str = filter_cfg.get('end_time') if filter_cfg.get('time_filter_enabled') else None
    add_market_open_flag = filter_cfg.get('add_market_open', False)
    
    keywords_crit = keywords_cfg.get('CRITICAL_EVENTS', [])
    keywords_spk = keywords_cfg.get('IMPORTANT_SPEAKERS', [])
    keywords_high = keywords_cfg.get('HIGH_IMPACT_KEYWORDS', [])
    keywords_spec = keywords_cfg.get('CURRENCY_SPECIFIC_2STAR_KEYWORDS', {})

    # 读取输入 CSV (使用 load_input_file 更好，它处理 DataFrame 转换)
    input_data = load_input_file(str(input_path)) 
    if input_data is None:
        logger.error(f"无法加载输入文件: {input_path}")
        sys.exit(1)

    # --- 新增：显式转换 DataFrame 为 List[Dict]，确保与 process_events 一致 ---
    events_list_for_filtering: List[Dict[str, Any]]
    if isinstance(input_data, pd.DataFrame):
        logger.info("输入数据为 DataFrame，显式转换为字典列表...")
        events_list_for_filtering = input_data.to_dict('records')
        logger.info(f"成功将 DataFrame 转换为 {len(events_list_for_filtering)} 条记录的列表。")
    elif isinstance(input_data, list):
        logger.info("输入数据已经是字典列表。")
        # 可以在这里加一步验证列表内容是否为字典，但暂时省略
        events_list_for_filtering = input_data
    else:
        logger.error(f"load_input_file 返回了无法处理的数据类型: {type(input_data)}")
        sys.exit(1)
    # --- 新增结束 ---

    # 应用筛选逻辑 (调用共享函数)
    logger.info("调用共享的 apply_memory_filters 函数进行筛选...")
    filtered_events_list = apply_memory_filters(
        events=events_list_for_filtering, 
        min_importance_threshold=min_importance,
        target_currencies=target_currencies_list,
        use_keywords_filter=use_keywords,
        start_time=start_time_str,
        end_time=end_time_str,
        add_market_open=add_market_open_flag,
        keywords_critical=keywords_crit,
        keywords_speakers=keywords_spk,
        keywords_high_impact=keywords_high,
        keywords_2star_specific=keywords_spec
    )

    if filtered_events_list is None: # apply_memory_filters 返回 List 或 None
        logger.error("数据筛选失败，请检查日志。")
        sys.exit(1)

    if not filtered_events_list:
        logger.info("筛选后无数据，不写入输出文件。")
        # 创建一个空的输出文件或保留旧文件？通常不写比较好
        # 为了明确表示完成，可以写入一个空文件或只记录日志
        # 暂时：不写入文件，并以成功代码退出
        print("筛选后无数据。")
        sys.exit(0)

    # 保存筛选结果到输出 CSV
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True) # 确保输出目录存在
        encoding = OmegaConf.select(config, "economic_calendar.export.csv_encoding", default="utf-8")
        logger.info(f"准备将 {len(filtered_events_list)} 条筛选后的数据写入输出文件 {output_path} (编码: {encoding})...")
        pd.DataFrame(filtered_events_list).to_csv(output_path, index=False, encoding=encoding)
        logger.info("筛选结果成功写入输出文件。")
    except Exception as e:
        logger.error(f"写入输出 CSV 文件时出错: {e}", exc_info=True)
        sys.exit(1)

    logger.info("筛选步骤成功完成。")

if __name__ == "__main__":
    main() 