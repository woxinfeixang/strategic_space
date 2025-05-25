#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
经济数据综合处理模块
- 下载最新财经日历数据
- 筛选数据
- 导出结果
"""
import os
import sys
import logging
import argparse
import yaml
import re
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from omegaconf import OmegaConf, DictConfig
import asyncio

# --- 添加：确保项目根目录在 sys.path 中 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
        print(f"--- Added {PROJECT_ROOT} to sys.path in main.py ---")
except IndexError:
    print("ERROR: Could not determine project root directory from main.py.")
    pass
# --- 添加结束 ---

# --- 修改：从共享 utils 导入配置加载和路径解析 ---
from core.utils import load_app_config, setup_logging, get_absolute_path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('economic_calendar.main')

# 从economic_calendar模块导入依赖项
from economic_calendar.event_filter.logic import apply_memory_filters, process_events
from economic_calendar.data.loader import load_input_file
from economic_calendar.data.exporter import export_to_csv, export_to_sqlite
from economic_calendar.economic_calendar_realtime.download_investing_calendar import main as downloader_main

def download_realtime_data(config: DictConfig) -> Optional[str]:
    """下载实时经济日历数据"""
    try:
        # 获取下载参数 (虽然 downloader 的 main 会自己加载，但这里获取路径用)
        download_cfg = config.economic_calendar.download
        # days_ahead = download_cfg.get('days_ahead', 7) # 不再需要
        # ... retry_attempts, retry_delay_seconds etc. are handled internally ...

        # 获取预期的输出路径 (使用 get_absolute_path)
        output_dir_path = get_absolute_path(config, "economic_calendar.paths.raw_live_dir")
        if output_dir_path is None:
            logger.error("无法解析原始实时数据目录路径。")
            return None
        output_dir = str(output_dir_path)
        # 从配置获取预期的 CSV 文件名
        output_filename = config.economic_calendar.files.raw_live_csv
        expected_csv_path = Path(output_dir) / output_filename
        os.makedirs(output_dir, exist_ok=True) # 确保目录存在

        # --- 修改：调用 downloader 的 main 函数来执行下载、解析和保存 CSV --- 
        # from economic_calendar.economic_calendar_realtime.download_investing_calendar import scrape_investing_calendar
        # import asyncio # 确保导入 (已在文件顶部导入)

        try:
            logger.info("开始执行实时数据下载、解析和保存流程...")
            # 运行 downloader 脚本的 main 函数
            # downloader_main 会加载自己的配置并执行所有步骤
            asyncio.run(downloader_main()) 
            logger.info("实时数据处理流程执行完毕。")

            # 检查预期的 CSV 文件是否已生成
            if expected_csv_path.exists():
                logger.info(f"数据成功处理并保存到: {expected_csv_path}")
                return str(expected_csv_path) # 返回 CSV 文件路径
            else:
                logger.error(f"处理完成但未找到预期的输出文件: {expected_csv_path}")
                return None
        except Exception as e:
            logger.error(f"执行下载器主流程时出错: {e}", exc_info=True)
            return None
        # --- 修改结束 ---

    except KeyError as e:
        logger.error(f"下载配置错误，缺少键: {e}")
        return None
    except Exception as e:
        logger.error(f"下载数据时发生未知错误: {e}", exc_info=True) # 添加 exc_info
        return None

def filter_data(config: DictConfig, input_file: str, mode: str) -> bool:
    """筛选经济日历数据"""
    try:
        # 获取筛选参数
        filter_cfg = config.economic_calendar.filtering
        min_importance = filter_cfg.min_importance
        currencies = list(config.economic_calendar.currencies)
        start_time_str = filter_cfg.get('start_time') if filter_cfg.time_filter_enabled else None
        end_time_str = filter_cfg.get('end_time') if filter_cfg.time_filter_enabled else None
        add_market_open_flag = filter_cfg.add_market_open # 重命名以避免与函数参数冲突
        use_keywords_filter = filter_cfg.get('use_keywords_filter', False) # 获取开关，但后面直接传递关键词

        # --- 获取新的结构化关键词配置 ---
        kw_cfg = config.get('economic_calendar', {}).get('keywords_config', {})
        keywords_critical = list(kw_cfg.get('CRITICAL_EVENTS', []))
        keywords_speakers = list(kw_cfg.get('IMPORTANT_SPEAKERS', []))
        keywords_high_impact = list(kw_cfg.get('HIGH_IMPACT_KEYWORDS', []))
        keywords_2star_specific_raw = kw_cfg.get('CURRENCY_SPECIFIC_2STAR_KEYWORDS', {})
        keywords_2star_specific = {k: list(v) for k, v in keywords_2star_specific_raw.items()} if isinstance(keywords_2star_specific_raw, dict) else {}
        # --- 关键词获取结束 ---

        # --- 修改：使用 get_absolute_path 获取 DB 输出路径 ---
        db_output_dir_path = get_absolute_path(config, "economic_calendar.paths.db_dir")
        if db_output_dir_path is None:
            logger.error("无法解析数据库输出目录路径。")
            return False
        db_filename = config.economic_calendar.files.events_db
        db_output = str(db_output_dir_path / db_filename) # 这是 db_output_path
        os.makedirs(db_output_dir_path, exist_ok=True)

        # --- 修改：使用 get_absolute_path 获取 CSV 输出路径 ---
        output_dir_path = None
        csv_filename = None
        if mode == 'realtime':
            output_dir_path = get_absolute_path(config, "economic_calendar.paths.filtered_live_dir")
            csv_prefix = config.economic_calendar.files.filtered_csv_prefix
            csv_filename = f"{csv_prefix}{mode}.csv"
        elif mode == 'history':
            output_dir_path = get_absolute_path(config, "economic_calendar.paths.filtered_history_dir")
            csv_filename = "filtered_historical.csv"

        if output_dir_path is None or csv_filename is None:
            logger.error(f"无法解析模式 '{mode}' 的筛选输出目录路径或生成文件名。")
            return False

        csv_output = str(output_dir_path / csv_filename) # 这是 output_path
        os.makedirs(output_dir_path, exist_ok=True)

        # --- 彻底修正 process_events 调用：传递所有需要的具体参数 ---
        success = process_events(
            input_path=input_file,
            output_path=csv_output,
            mode=mode,
            db_output_path=db_output, # 传递计算好的 DB 路径
            # 从 config 中提取并传递具体参数
            min_importance=min_importance,
            target_currencies=currencies,
            start_time=start_time_str,
            end_time=end_time_str,
            add_market_open=add_market_open_flag,
            # 传递所有新的关键词参数
            keywords_critical=keywords_critical,
            keywords_speakers=keywords_speakers,
            keywords_high_impact=keywords_high_impact,
            keywords_2star_specific=keywords_2star_specific,
            # 传递从配置读取的关键词筛选开关
            use_keywords_filter_from_caller=use_keywords_filter 
        )
        # --- 调用修正结束 ---

        if success:
            logger.info(f"数据成功筛选并导出到: {csv_output} 和 {db_output}")
            return True
        else:
            logger.error("筛选数据失败")
            return False
    except KeyError as e:
        logger.error(f"筛选配置错误，缺少键: {e}")
        return False
    except Exception as e:
        logger.error(f"筛选数据时出错: {e}")
        return False

def run_realtime_workflow(config: DictConfig) -> bool:
    """执行完整的实时工作流：下载 -> 筛选 -> (导出) -> (复制)"""
    logger.info("开始执行实时工作流...")
    
    # 1. 下载数据
    # --- 修改：不再在此处配置日志，假设调用方已配置 ---
    # configure_logging(config) # <--- 移除调用
    # --- 修改结束 ---
    downloaded_file = download_realtime_data(config)
    
    if downloaded_file:
        # 2. 筛选数据
        success = filter_data(config, downloaded_file, mode='realtime')
        if success:
            logger.info("实时工作流成功完成。")
            return True
    
    logger.error("实时工作流执行失败。")
    return False

def run_historical_workflow(config: DictConfig, action: str) -> bool:
    """执行历史工作流：下载/解析 -> 筛选 -> (导出)"""
    logger.info(f"开始执行历史工作流 (Action: {action})...")

    # --- 修改：不再在此处配置日志，假设调用方已配置 ---
    # configure_logging(config) # <--- 移除调用
    # --- 修改结束 ---

    if action == 'download':
        # TODO: 实现历史数据下载逻辑
        logger.warning("历史数据下载功能尚未实现。")
        return False
    elif action == 'process':
        # TODO: 实现历史数据原始文件解析逻辑 (类似 process_calendar.py)
        logger.warning("历史数据原始文件解析功能尚未实现。")
        return False
    elif action == 'filter':
        # --- 修改：读取 process_calendar.py 实际生成的中间文件 ---
        try:
            # 1. 获取 Processed 目录路径
            input_dir_path = get_absolute_path(config, "economic_calendar.paths.processed_history_dir") 
            # 2. 获取 Processed CSV 文件名 (由 process_calendar.py 生成)
            input_filename = config.economic_calendar.files.processed_history_csv # <--- 读取这个键
            
            if input_dir_path is None:
                logger.error("无法解析处理后历史数据目录路径 (processed_history_dir)。")
                return False
            if not input_filename:
                 logger.error("配置 economic_calendar.files.processed_history_csv 为空或未找到。")
                 return False
                 
            input_file = str(input_dir_path / input_filename)
            # --- 修改结束 ---
        except KeyError as e:
            logger.error(f"历史筛选配置错误，缺少键: {e}")
            return False
            
        if not os.path.exists(input_file):
             logger.error(f"历史数据源文件 (处理后的) 不存在: {input_file}。请先执行数据处理步骤。") # 更新错误消息
             return False

        # --- 修改：不再调用 filter_data/process_events，改为直接调用 apply_memory_filters --- 
        # # 执行筛选 (旧方法)
        # success = filter_data(config, input_file, mode='history')
        
        logger.info(f"直接调用 apply_memory_filters 处理历史数据: {input_file}")
        try:
            # 1. 加载输入数据 (使用 load_input_file)
            input_data = load_input_file(input_file)
            if input_data is None:
                logger.error(f"无法加载历史输入文件: {input_file}")
                return False

            # 2. 显式转换为字典列表 (与 filter_data_step.py 保持一致)
            events_list_for_filtering: List[Dict[str, Any]]
            if isinstance(input_data, pd.DataFrame):
                logger.info("历史输入数据为 DataFrame，显式转换为字典列表...")
                events_list_for_filtering = input_data.to_dict('records')
                logger.info(f"成功将 DataFrame 转换为 {len(events_list_for_filtering)} 条记录的列表。")
            elif isinstance(input_data, list):
                logger.info("历史输入数据已经是字典列表。")
                events_list_for_filtering = input_data
            else:
                logger.error(f"load_input_file 返回了无法处理的数据类型: {type(input_data)}")
                return False

            # 3. 准备筛选参数 (与 filter_data_step.py 逻辑一致)
            filter_cfg = config.get('economic_calendar', {}).get('filtering', {})
            currencies = config.get('economic_calendar', {}).get('currencies', [])
            keywords_cfg = config.get('economic_calendar', {}).get('keywords_config', {})
            
            min_importance = filter_cfg.get('min_importance', 0)
            target_currencies_list = currencies
            use_keywords = filter_cfg.get('use_keywords_filter', False)
            start_time_str = filter_cfg.get('start_time') if filter_cfg.get('time_filter_enabled') else None
            end_time_str = filter_cfg.get('end_time') if filter_cfg.get('time_filter_enabled') else None
            add_market_open_flag = filter_cfg.get('add_market_open', False)
            
            keywords_crit = keywords_cfg.get('CRITICAL_EVENTS', [])
            keywords_spk = keywords_cfg.get('IMPORTANT_SPEAKERS', [])
            keywords_high = keywords_cfg.get('HIGH_IMPACT_KEYWORDS', [])
            keywords_spec = keywords_cfg.get('CURRENCY_SPECIFIC_2STAR_KEYWORDS', {})

            # 4. 调用 apply_memory_filters
            logger.info("调用 apply_memory_filters 进行历史数据筛选...")
            filtered_events = apply_memory_filters(
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

            if filtered_events is None:
                 logger.error("apply_memory_filters 筛选历史数据失败。")
                 return False
                 
            # 5. 处理输出 (保存 CSV 和 DB，逻辑类似旧的 process_events)
            # --- 准备输出路径 (与 filter_data 函数逻辑类似) ---
            csv_output_dir_path = get_absolute_path(config, "economic_calendar.paths.filtered_history_dir")
            csv_filename = "filtered_historical.csv"
            db_output_dir_path = get_absolute_path(config, "economic_calendar.paths.db_dir")
            db_filename = config.economic_calendar.files.events_db
            
            if csv_output_dir_path is None or db_output_dir_path is None:
                logger.error("无法解析历史筛选的 CSV 或 DB 输出目录路径。")
                return False
                
            csv_output_path = csv_output_dir_path / csv_filename
            db_output_path = db_output_dir_path / db_filename
            csv_output_dir_path.mkdir(parents=True, exist_ok=True)
            db_output_dir_path.mkdir(parents=True, exist_ok=True)
            # --- 输出路径准备结束 ---

            # --- 保存结果 --- 
            save_ok = True
            if filtered_events: # 仅在有数据时保存
                # --- 新增：将列表转换为 DataFrame 以便导出 ---
                logger.info(f"将 {len(filtered_events)} 条筛选结果转换为 DataFrame 以便导出...")
                try:
                    df_to_export = pd.DataFrame(filtered_events)
                    # 可选：确保列顺序与标准一致 (如果 exporter 不处理)
                    # from economic_calendar.data.exporter import STANDARD_COLUMNS
                    # df_to_export = df_to_export[STANDARD_COLUMNS]
                except Exception as df_conv_err:
                    logger.error(f"将筛选结果列表转换为 DataFrame 时出错: {df_conv_err}", exc_info=True)
                    return False # 转换失败则无法保存
                # --- 转换结束 ---
                
                # 保存 CSV
                if not export_to_csv(df_to_export, str(csv_output_path)): # <-- 传递 DataFrame
                    logger.error(f"导出筛选后的历史数据到 CSV {csv_output_path} 失败。")
                    save_ok = False
                # 保存 DB
                if not export_to_sqlite(df_to_export, str(db_output_path), table_name="events_history"): # <-- 传递 DataFrame
                    logger.error(f"导出筛选后的历史数据到 DB {db_output_path} 失败。")
                    save_ok = False
            else:
                logger.info("筛选后无历史数据，不执行保存操作。")
                # 也可以选择写入空文件或清空旧文件
                # 清空旧文件示例 (如果需要)
                # if csv_output_path.exists(): csv_output_path.unlink()
                # ... (数据库可能需要更复杂的清空逻辑，或直接跳过) ...
                
            success = save_ok # 如果没有数据也算成功，如果保存失败则为 False
            # --- 保存结束 --- 

        except Exception as e:
            logger.error(f"直接处理历史数据筛选时发生错误: {e}", exc_info=True)
            success = False
        # --- 修改结束 ---

        if success:
            logger.info(f"历史工作流 (Action: {action}) 成功完成。")
            return True
        else:
            logger.error(f"历史工作流 (Action: {action}) 执行失败。")
            return False
    else:
        logger.error(f"未知的历史工作流动作: {action}")
        return False

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="经济日历数据处理工具 (main.py)")
    parser.add_argument(
        "--workflow", 
        choices=['realtime', 'history'], 
        required=True, 
        help="选择要执行的工作流类型：实时(realtime)或历史(history)"
    )
    parser.add_argument(
        "--action", 
        choices=['download', 'process', 'filter'], 
        required=False, 
        help="指定历史工作流的具体动作 (仅当 --workflow=history 时需要，'filter' 是默认动作)"
    )
    return parser.parse_args()

def main_cli(): # 重命名原始 main 为 main_cli
    args = parse_arguments()
    # --- 修改：传递模块配置路径给 load_app_config ---
    module_config_rel_path = "economic_calendar/config/processing.yaml"
    config = load_app_config(module_config_rel_path) # <--- 传递参数
    # --- 修改结束 ---

    # --- 修改：日志配置由调用脚本处理，这里不再调用 ---
    # configure_logging(config) # <--- 移除调用
    # --- 修改结束 ---

    success = False
    if args.workflow == 'realtime':
        success = run_realtime_workflow(config)
    elif args.workflow == 'history':
        action = args.action if args.action else 'filter' # 默认为 filter
        success = run_historical_workflow(config, action)

    if success:
        logger.info(f"{args.workflow.capitalize()} 工作流执行完毕。")
        sys.exit(0)
    else:
        logger.error(f"{args.workflow.capitalize()} 工作流执行失败。")
        sys.exit(1)

if __name__ == "__main__":
    main_cli() # 调用重命名后的函数 