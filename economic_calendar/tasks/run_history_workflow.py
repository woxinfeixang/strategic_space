#!/usr/bin/env python
# -*- coding: utf-8 -*-
print("--- SCRIPT START: run_history_workflow.py ---") # 添加调试打印

# --- Standard Imports ---
import sys
import logging
import argparse
import time
from pathlib import Path # 使用 pathlib
from typing import List, Optional
from omegaconf import OmegaConf, DictConfig

# --- Project Path Setup ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
        print(f"--- Added {PROJECT_ROOT} to sys.path ---")
except IndexError:
    print("ERROR: Could not determine project root directory. Please check script location.")
    sys.exit(1)

# --- Project-specific Imports (after path setup) ---
try:
    from core.utils import load_app_config, get_absolute_path
    # 尝试从 economic_calendar.utils 导入，如果不存在则报错
    # from economic_calendar.utils.logging_config import setup_logging # 删除旧导入
    from core.utils import setup_logging # <-- 导入 core.utils.setup_logging
    from economic_calendar.utils.environment import check_environment
    from economic_calendar.utils.process import run_command
except ImportError as e:
    # 检查是否是 economic_calendar.utils 的问题
    if 'economic_calendar.utils' in str(e):
         print(f"ERROR: Failed to import from economic_calendar.utils: {e}. "
               "Ensure this module and its functions (logging_config, environment, process) exist.")
    else:
        print(f"ERROR: Failed to import necessary modules: {e}. Check project structure and dependencies.")
    sys.exit(1)

# --- 日志配置 (移动到 main 函数内部，并在筛选前重新配置) ---
# log_dir = PROJECT_ROOT / "logs"
# log_dir.mkdir(exist_ok=True)

# -- 加载配置 -- 
config: Optional[DictConfig] = None
try:
    config = load_app_config('economic_calendar/config/processing.yaml') 
except Exception as e:
    print(f"CRITICAL: Failed to load configuration for History Workflow: {e}", file=sys.stderr)
    sys.exit(1)

# -- 设置日志 (将在 main 函数中进行，以便可以根据操作切换) --
logger: Optional[logging.Logger] = None
# try:
#     log_filename = OmegaConf.select(config, 'logging.history_workflow_log_filename', default='history_workflow_fallback.log')
#     logger = setup_logging(
#         log_config=config.logging, 
#         log_filename=log_filename,
#         logger_name="HistoryWorkflow"
#     )
# except Exception as log_setup_e:
#     print(f"ERROR: Failed to setup logging via core.utils: {log_setup_e}", file=sys.stderr)
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#     logger = logging.getLogger('HistoryWorkflow_Fallback')
#     logger.error("Logging setup failed, using basic config.", exc_info=True)
#
# if logger is None: # 再次检查
#     print("Logger initialization failed completely. Exiting.")
#     sys.exit(1)
#
# logger.info(f"Project Root: {PROJECT_ROOT}")

# --- 主函数 ---
def main():
    global logger # 声明 logger 为全局变量，以便在函数内修改

    # --- 加载并验证配置 ---
    module_config_rel_path = "economic_calendar/config/processing.yaml"
    config = load_app_config(module_config_rel_path)
    if config is None:
        print("CRITICAL: Failed to load or merge configuration (common.yaml + processing.yaml), workflow terminating.", file=sys.stderr)
        # 尝试使用基本日志记录错误
        logging.basicConfig(level=logging.ERROR)
        logging.error("无法加载或合并配置 (common.yaml + processing.yaml)，工作流终止。")
        return

    # --- 初始日志设置 (使用 history_workflow_log_filename) ---
    try:
        log_filename = OmegaConf.select(config, 'logging.history_workflow_log_filename', default='history_workflow.log')
        logger = setup_logging(
            log_config=config.logging,
            log_filename=log_filename,
            logger_name="HistoryWorkflow"
        )
        logger.info("初始日志设置完成，使用文件: %s", log_filename)
    except Exception as log_setup_e:
        print(f"ERROR: Failed to setup initial logging: {log_setup_e}", file=sys.stderr)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logger = logging.getLogger('HistoryWorkflow_Fallback')
        logger.error("Initial logging setup failed, using basic config.", exc_info=True)

    if logger is None:
        print("Logger initialization failed completely. Exiting.")
        sys.exit(1)

    logger.info("共享配置和模块配置加载并合并成功。")

    # --- 环境检查 ---
    if not check_environment():
        logger.error("环境检查失败，工作流终止。")
        return
    logger.info("环境检查通过。")

    # --- 参数解析 (添加日期范围) ---
    parser = argparse.ArgumentParser(description="历史数据处理工作流")
    default_retries_process = OmegaConf.select(config, "retries.process_history", default=1)
    default_retries_filter = OmegaConf.select(config, "retries.filter_history", default=1) # 添加筛选重试次数
    default_delay = OmegaConf.select(config, "retries.delay_seconds", default=3)

    parser.add_argument("--process-retries", type=int, default=default_retries_process, help=f"处理步骤的最大重试次数 (默认: {default_retries_process} 来自配置)")
    parser.add_argument("--filter-retries", type=int, default=default_retries_filter, help=f"筛选步骤的最大重试次数 (默认: {default_retries_filter} 来自配置)") # 添加筛选重试参数
    parser.add_argument("--retry-delay", type=int, default=default_delay, help=f"重试之间的延迟秒数 (默认: {default_delay} 来自配置)")
    parser.add_argument("--start-date", type=str, default=None, help="处理的开始日期 (YYYY-MM-DD)。如果未提供，脚本内部应有默认逻辑。")
    parser.add_argument("--end-date", type=str, default=None, help="处理的结束日期 (YYYY-MM-DD)。如果未提供，脚本内部应有默认逻辑。")

    args = parser.parse_args()

    logger.info(f"使用参数: process_retries={args.process_retries}, filter_retries={args.filter_retries}, retry_delay={args.retry_delay}, start_date={args.start_date}, end_date={args.end_date}")

    # --- 步骤 1: 执行历史数据处理脚本 (解析 HTML -> 生成中间 Processed CSV) ---
    logger.info("--- 步骤 1: 开始执行历史数据处理脚本 (生成中间 Processed CSV) ---")
    process_script_info = OmegaConf.select(config, "scripts.process_calendar")
    if not process_script_info or not OmegaConf.select(process_script_info, 'path'):
        logger.error("配置中缺少 scripts.process_calendar 或其 path 键。")
        return

    # --- 构造脚本路径 ---
    process_script_rel_path = OmegaConf.select(process_script_info, 'path')
    process_script_path = PROJECT_ROOT / process_script_rel_path
    if not process_script_path.is_file():
        logger.error(f"历史处理脚本未找到: {process_script_path}")
        return

    # --- 获取期望的输出 Processed CSV 路径 (用于验证) ---
    processed_dir = get_absolute_path(config, "economic_calendar.paths.processed_history_dir")
    if processed_dir is None:
        logger.error("无法解析处理后历史数据目录路径 (economic_calendar.paths.processed_history_dir)，工作流终止。")
        return
    # 修改：从配置获取处理后的历史 CSV 文件名
    try:
        processed_history_csv_filename = config.economic_calendar.files.processed_history_csv
        if not processed_history_csv_filename:
             raise ValueError("配置中 processed_history_csv 值为空")
        logger.info(f"配置中指定的中间 CSV 文件名: {processed_history_csv_filename}")
    except Exception as e:
        logger.error(f"无法从配置 economic_calendar.files.processed_history_csv 获取中间文件名: {e}")
        sys.exit(1)

    # 修改：使用配置中的文件名构建预期输出路径
    expected_output_step1 = processed_dir / processed_history_csv_filename
    # expected_output_step1 = processed_dir / "economic_calendar_history_processed.csv" # 移除硬编码

    # --- 构造传递给处理脚本的参数 ---
    process_cmd_base_args = OmegaConf.select(process_script_info, 'args', default=[])
    date_args = []
    if args.start_date:
        date_args.extend(["--start-date", args.start_date])
    if args.end_date:
        date_args.extend(["--end-date", args.end_date])

    process_command = (
        [sys.executable, str(process_script_path)]
        + process_cmd_base_args
        + date_args
    )

    # --- 执行命令 (验证中间 CSV) ---
    if not run_command(process_command, expected_output_path=str(expected_output_step1), max_retries=args.process_retries, retry_delay=args.retry_delay):
        logger.error("历史数据处理脚本执行失败 (生成中间 CSV 失败)，工作流终止。")
        return
    logger.info("步骤 1: 历史数据处理脚本执行成功 (中间 CSV 已生成)。")

    # --- 步骤 2: 执行核心筛选脚本 (读取中间 CSV -> 筛选 -> 写入数据库和 Filtered CSV) ---
    logger.info("--- 步骤 2: 开始执行核心筛选脚本 (筛选并写入数据库/Filtered CSV) ---")
    filter_script_info = OmegaConf.select(config, "scripts.main") # 假设配置中有 main 脚本信息
    if not filter_script_info or not OmegaConf.select(filter_script_info, 'path'):
        logger.warning("配置中缺少 scripts.main 或其 path 键，将尝试直接使用 economic_calendar/main.py")
        # 回退到默认路径
        filter_script_rel_path = "economic_calendar/main.py"
        filter_script_path = PROJECT_ROOT / filter_script_rel_path
    else:
        filter_script_rel_path = OmegaConf.select(filter_script_info, 'path')
        filter_script_path = PROJECT_ROOT / filter_script_rel_path

    if not filter_script_path.is_file():
        logger.error(f"核心筛选脚本未找到: {filter_script_path}")
        return

    # --- 获取期望的输出 DB 和 Filtered CSV 路径 (用于验证) ---
    # Filtered CSV 路径
    filtered_dir = get_absolute_path(config, "economic_calendar.paths.filtered_history_dir")
    if filtered_dir is None:
        logger.error("无法解析筛选后历史数据目录路径 (economic_calendar.paths.filtered_history_dir)，工作流终止。")
        return
    # 修改：使用配置中的 DB 文件名构建预期路径
    try:
        db_filename = config.economic_calendar.files.events_db
        if not db_filename:
             raise ValueError("配置中 events_db 值为空")
    except Exception as e:
        logger.error(f"无法从配置 economic_calendar.files.events_db 获取 DB 文件名: {e}")
        sys.exit(1)
    expected_output_step2_db = filtered_dir / db_filename
    # expected_output_step2_db = filtered_dir / "economic_calendar.db" # 移除硬编码

    # --- 添加：定义最终筛选后的 CSV 路径 (用于验证) ---
    filtered_csv_filename = "filtered_historical.csv" # 与 main.py 中使用的文件名保持一致
    expected_output_step2_csv = filtered_dir / filtered_csv_filename

    # --- 构造筛选命令 ---
    # main.py 应该能自动读取 processing.yaml 配置，知道输入是 processed CSV，输出是 DB 和 filtered CSV
    # 注意：需要确保 main.py 或其配置将 DB 输出到 filtered 目录！
    filter_command = [
        sys.executable,
        str(filter_script_path),
        "--workflow", "history",
        "--action", "filter"
        # "--config-path", str(processed_dir.parent), # 移除：main.py 不接受此参数
        # "--config-name", processed_dir.stem      # 移除：main.py 不接受此参数
    ]

    # --- 在执行筛选步骤前，重新配置日志以使用 filter_log_filename ---
    try:
        filter_log_filename = OmegaConf.select(config, 'logging.filter_log_filename', default='calendar_filter.log')
        logger.info(f"重新配置日志以进行筛选步骤，将使用文件: {filter_log_filename}")
        # 关闭现有处理程序
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        # 重新设置日志
        logger = setup_logging(
            log_config=config.logging, # 使用相同的基本配置
            log_filename=filter_log_filename,
            logger_name="HistoryWorkflow_Filter" # 可以考虑使用不同的名称，或保持一致
        )
        logger.info("日志已重新配置为筛选步骤。")
    except Exception as e:
        logger.error(f"为筛选步骤重新配置日志失败: {e}", exc_info=True)
        # 如果重新配置失败，至少记录一个错误，然后继续使用旧的日志器

    # --- 执行筛选命令 (验证 DB 或 Filtered CSV) ---
    # 优先验证 Filtered CSV
    if not run_command(filter_command, expected_output_path=str(expected_output_step2_csv), max_retries=args.filter_retries, retry_delay=args.retry_delay):
        logger.error("核心筛选脚本执行失败，工作流终止。")
        return
    
    # --- 添加：执行后额外检查数据库文件是否存在于 filtered 目录 --- 
    if not expected_output_step2_csv.exists() or not expected_output_step2_db.exists():
        logger.warning(f"筛选脚本执行成功 (Filtered CSV已生成)，但数据库文件 {expected_output_step2_db} 在 filtered 目录中未找到。请检查 main.py 的数据库写入逻辑是否正确配置到 filtered 目录。")
    else:
        logger.info(f"数据库文件 {expected_output_step2_db} 在 filtered 目录已确认存在/更新。")

    logger.info("步骤 2: 核心筛选脚本执行成功 (数据已筛选并写入 Filtered CSV，数据库应位于 filtered 目录)。") # 更新日志

    logger.info("历史数据处理工作流成功完成。")

if __name__ == "__main__":
    # --- 修改：将日志记录移到 main 函数内部 ---
    # logger.info("开始执行历史数据工作流...") # <-- 移动
    main()
    # logger.info("历史数据工作流执行结束。") # <-- 移动
    print("--- SCRIPT END: run_history_workflow.py ---")