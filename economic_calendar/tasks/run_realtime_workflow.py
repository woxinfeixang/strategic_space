#!/usr/bin/env python
# -*- coding: utf-8 -*-
print("--- SCRIPT START: run_realtime_workflow.py ---") # 添加调试打印

# --- Standard Imports ---
import sys
import logging
import argparse
import shutil
import time
from pathlib import Path # 使用 pathlib
from typing import List, Optional
from omegaconf import DictConfig, OmegaConf # Import DictConfig and OmegaConf from omegaconf
import os # <-- 添加导入 os

# --- Project Path Setup ---
# 该脚本位于 economic_calendar/tasks/ 下
# PROJECT_ROOT 应为 economic_calendar 的父目录
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
    from core.utils import load_app_config, get_absolute_path # 修改为从core模块导入
    from core.utils import setup_logging # <-- 导入 core.utils.setup_logging
    from economic_calendar.utils.environment import check_environment
    from economic_calendar.utils.process import run_command # 假设此工具函数存在且可用
except ImportError as e:
    print(f"ERROR: Failed to import necessary modules: {e}. "
          "Ensure the project structure is correct and all dependencies are installed.")
    sys.exit(1)

# --- 日志配置 ---
# 使用绝对路径或相对于项目根目录的路径来配置日志文件位置可能更健壮
# log_dir = PROJECT_ROOT / "logs" # 不再需要手动拼接路径
# log_dir.mkdir(exist_ok=True)

# -- 加载配置 -- 
config: Optional[DictConfig] = None # <--- DictConfig 类型提示
try:
    # 假设工作流配置也包含在 processing.yaml 或 common.yaml 中，并可通过 load_app_config 加载
    # 需要确定 economic_calendar 模块的基础配置文件路径
    config = load_app_config('economic_calendar/config/processing.yaml') 
    # 如果工作流有独立的配置文件，则修改此路径
except Exception as e:
    print(f"CRITICAL: Failed to load configuration for Realtime Workflow: {e}", file=sys.stderr)
    sys.exit(1)

# -- 设置日志 (使用 core.utils.setup_logging) --
logger: Optional[logging.Logger] = None
try:
    log_filename = OmegaConf.select(config, 'logging.realtime_workflow_log_filename', default='realtime_workflow_fallback.log')
    logger = setup_logging(
        log_config=config.logging, 
        log_filename=log_filename,
        logger_name="RealtimeWorkflow"
    )
except Exception as log_setup_e:
    # Fallback to basic logging if setup fails
    print(f"ERROR: Failed to setup logging via core.utils: {log_setup_e}", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('RealtimeWorkflow_Fallback')
    logger.error("Logging setup failed, using basic config.", exc_info=True)

if logger is None: # 再次检查，确保 logger 实例存在
    print("Logger initialization failed completely. Exiting.")
    sys.exit(1)

logger.info(f"Project Root: {PROJECT_ROOT}")

# --- 辅助函数：构造筛选参数 (保持不变，但使用更安全的类型检查) ---
def build_filter_args(filter_settings) -> List[str]:
    args_list = []
    if filter_settings:
        try:
            # 尝试将 OmegaConf 配置转换为 Python 字典
            if OmegaConf.is_config(filter_settings):
                set_settings = OmegaConf.to_container(filter_settings, resolve=True)
            elif isinstance(filter_settings, dict):
                 set_settings = filter_settings
            else:
                 logger.warning(f"无法处理的 filter_settings 类型: {type(filter_settings)}")
                 set_settings = {} # 或者抛出错误

        except Exception as e:
            logger.error(f"转换 filter_settings 时出错: {e}", exc_info=True)
            set_settings = {}

        for key, value in set_settings.items():
            if value is None:
                continue
            # 检查是否未解析（虽然 load_app_config 应该已经处理）
            if isinstance(value, str) and '${' in value:
                logger.warning(f"配置键 '{key}' 的值 '{value}' 可能未被解析，跳过。")
                continue

            arg_name = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    args_list.append(arg_name)
            elif isinstance(value, (list, tuple)): # 处理列表/元组
                args_list.append(arg_name)
                args_list.extend([str(v) for v in value]) # 确保元素是字符串
            else:
                args_list.append(arg_name)
                args_list.append(str(value))
    return args_list

# --- 主函数 ---
def main():
    # --- 加载并验证配置 ---
    module_config_rel_path = "economic_calendar/config/processing.yaml" # 模块特定配置
    config = load_app_config(module_config_rel_path) # 使用共享加载器 (包含 common.yaml)
    if config is None:
        logger.error("无法加载或合并配置 (common.yaml + processing.yaml)，工作流终止。")
        return
    logger.info("共享配置和模块配置加载并合并成功。")

    # --- 获取当前激活的 MT5 配置 (用于结果复制) ---
    active_mt5_config = None
    active_profile_name = OmegaConf.select(config, "economic_calendar.mt5_data_copy.active_profile")
    mt5_profiles = OmegaConf.select(config, "economic_calendar.mt5_data_copy.profiles")

    if active_profile_name and mt5_profiles:
        if active_profile_name in mt5_profiles:
            # active_mt5_config = mt5_profiles.get(active_profile_name) # OmegaConf 对象直接访问
            active_mt5_config = mt5_profiles[active_profile_name]
            logger.info(f"当前激活的 MT5 配置 (用于复制): {active_profile_name}")
        else:
            logger.warning(f"配置文件中指定的活动 MT5 配置 '{active_profile_name}' 不存在于 economic_calendar.mt5_data_copy.profiles 中。")
    else:
        logger.warning("配置文件中未指定活动的 MT5 配置 (economic_calendar.mt5_data_copy.active_profile) 或 profiles 为空。")

    # --- 参数解析 (保持不变，但使用 OmegaConf.select 获取默认值) ---
    parser = argparse.ArgumentParser(description="实时数据处理工作流")
    default_retries_download = OmegaConf.select(config, "retries.download_realtime", default=1)
    default_retries_filter = OmegaConf.select(config, "retries.filter_realtime_data", default=1)
    default_delay = OmegaConf.select(config, "retries.delay_seconds", default=3)

    parser.add_argument("--download-retries", type=int, default=default_retries_download, help=f"下载步骤的最大重试次数 (默认: {default_retries_download} 来自配置)")
    parser.add_argument("--filter-retries", type=int, default=default_retries_filter, help=f"筛选步骤的最大重试次数 (默认: {default_retries_filter} 来自配置)")
    parser.add_argument("--retry-delay", type=int, default=default_delay, help=f"重试之间的延迟秒数 (默认: {default_delay} 来自配置)")
    args = parser.parse_args()

    # --- 获取 MT5 目标路径 ---
    mt5_target_path_str = None
    if active_mt5_config:
         # 使用 OmegaConf.select 或 .get 获取，避免属性错误
         mt5_target_path_str = OmegaConf.select(active_mt5_config, 'directory', default=None)
         if mt5_target_path_str is None:
             logger.warning(f"激活的 MT5 配置 '{active_profile_name}' 中缺少 'directory' 路径。")

    logger.info(f"使用参数: download_retries={args.download_retries}, filter_retries={args.filter_retries}, retry_delay={args.retry_delay}")
    if active_mt5_config and mt5_target_path_str:
        mt5_target_path = Path(mt5_target_path_str) # 转换为 Path 对象
        logger.info(f"激活的 MT5 配置 (用于复制): {active_profile_name}, 目标目录: {mt5_target_path}")
    elif active_mt5_config:
         logger.warning(f"激活的 MT5 配置 '{active_profile_name}' 未指定目标目录，将无法执行 MT5 文件复制。")
         mt5_target_path = None
    else:
        logger.warning("未找到有效的激活 MT5 配置，将无法执行 MT5 文件复制操作。")
        mt5_target_path = None

    # --- 环境检查 ---
    if not check_environment():
        logger.error("环境检查失败，工作流终止。")
        return
    logger.info("环境检查通过。")

    # --- 步骤 1: 执行实时下载脚本 (恢复原始逻辑) ---
    logger.info("--- 步骤 1: 开始执行实时数据下载脚本 (使用 Playwright) ---")
    download_script_path = PROJECT_ROOT / "economic_calendar" / "economic_calendar_realtime" / "download_investing_calendar.py"
    if not download_script_path.is_file():
        logger.error(f"实时下载脚本未找到: {download_script_path}")
        return
    logger.info(f"将执行实时下载脚本: {download_script_path}")

    # 确定此步骤的预期输出文件，以便 run_command 可以验证
    raw_live_dir = get_absolute_path(config, "economic_calendar.paths.raw_live_dir")
    if raw_live_dir is None:
        logger.error("无法解析原始实时数据目录路径 (economic_calendar.paths.raw_live_dir)，无法验证下载结果。")
        download_expected_output_path = None
    else:
        # --- 修改：读取 CSV 文件名配置，而不是 HTML --- 
        # raw_live_html_name = OmegaConf.select(config, "economic_calendar.files.raw_live_html", default="realtime_calendar.html")
        raw_live_csv_name = OmegaConf.select(config, "economic_calendar.files.raw_live_csv", default="upcoming.csv") # 使用 CSV 配置键和默认值
        # download_expected_output_path = raw_live_dir / raw_live_html_name
        download_expected_output_path = raw_live_dir / raw_live_csv_name # 使用 CSV 文件名构建路径
        # --- 修改结束 ---
        raw_live_dir.mkdir(parents=True, exist_ok=True) # 确保目录存在
        # logger.info(f"实时下载脚本预期输出到: {download_expected_output_path}")
        logger.info(f"实时下载脚本预期输出到 (CSV): {download_expected_output_path}") # 修改日志信息

    # 构造下载命令 (假设 download_investing_calendar.py 不需要额外参数)
    download_command = [sys.executable, str(download_script_path)]

    # 使用 run_command 执行下载脚本
    download_success = run_command(
        download_command,
        expected_output_path=str(download_expected_output_path) if download_expected_output_path else None,
        max_retries=args.download_retries,
        retry_delay=args.retry_delay
    )

    if not download_success:
        logger.error("实时下载脚本执行失败或未生成预期文件，工作流终止。")
        return
    logger.info("步骤 1: 实时下载脚本执行成功，预期 CSV 文件已生成。")


    # --- 步骤 2: 执行核心筛选脚本，使用中间 CSV 作为输入 ---
    # (此步骤基本保持不变，输入已经是 process_html_expected_output_path)
    logger.info("--- 步骤 2: 开始执行核心筛选脚本 (使用下载的 CSV) ---")

    filter_script_path = PROJECT_ROOT / "economic_calendar" / "tasks" / "filter_data_step.py"
    if not filter_script_path.is_file():
        logger.error(f"筛选脚本未找到: {filter_script_path}")
        return
    logger.info(f"将直接执行筛选脚本: {filter_script_path}")

    # 筛选输出路径保持不变
    filter_output_dir = get_absolute_path(config, "economic_calendar.paths.filtered_live_dir")
    if filter_output_dir is None:
        logger.error("无法解析筛选后实时数据目录路径 (economic_calendar.paths.filtered_live_dir)，工作流终止。")
        return
    filtered_prefix = OmegaConf.select(config, "economic_calendar.files.filtered_csv_prefix", default="filtered_")
    filtered_live_output_name = f"{filtered_prefix}live.csv"
    filter_output_full_path = filter_output_dir / filtered_live_output_name
    filter_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"筛选脚本将输出到: {filter_output_full_path}")

    # 确保上一步生成的 CSV 存在
    if not download_expected_output_path or not download_expected_output_path.is_file():
         logger.error(f"找不到步骤1下载的 CSV 文件: {download_expected_output_path}，筛选中止。")
         return

    input_arg = ["--input-file", str(download_expected_output_path)]
    output_arg = ["--output-file", str(filter_output_full_path)]

    # 获取 filter_settings
    filter_settings = OmegaConf.select(config, "economic_calendar.filtering", default=None)

    filter_command = [
        sys.executable,
        str(filter_script_path),
        *input_arg,
        *output_arg,
    ]

    # --- 修改：假设 run_command 成功时只返回布尔值 (针对 filter_data_step.py) ---
    filter_success = run_command(
        filter_command,
        expected_output_path=str(filter_output_full_path),
        max_retries=args.filter_retries,
        retry_delay=args.retry_delay
    )

    if not filter_success:
        logger.error("核心筛选脚本执行失败，工作流终止。")
        return
    logger.info("核心筛选脚本执行成功。")

    # --- 步骤 3: (可选) 复制结果到 MT5 目录 ---
    if active_mt5_config and mt5_target_path:
        logger.info(f"--- 步骤 3: 尝试将结果复制到 MT5 目录: {mt5_target_path} ---")
        if not filter_output_full_path.is_file():
            logger.error(f"筛选后的输出文件不存在，无法复制: {filter_output_full_path}")
        else:
            try:
                # 确定目标文件名 (可以使用与源文件相同的名称)
                # target_filename = active_mt5_config.get('filename', filtered_live_output_name) # 从配置获取目标文件名或默认
                target_filename = OmegaConf.select(active_mt5_config, 'filename', default=filtered_live_output_name)
                target_full_path = mt5_target_path / target_filename

                # 确保目标目录存在
                mt5_target_path.mkdir(parents=True, exist_ok=True)

                shutil.copy2(filter_output_full_path, target_full_path) # copy2 保留元数据
                logger.info(f"成功将 {filter_output_full_path} 复制到 {target_full_path}")
            except Exception as copy_err:
                logger.error(f"复制文件到 MT5 目录时出错: {copy_err}", exc_info=True)
    else:
        logger.info("--- 步骤 3: 跳过复制到 MT5 目录 (未配置或目标路径无效) ---")

    logger.info("实时数据处理工作流成功完成。")


if __name__ == "__main__":
    main()
    print("--- SCRIPT END: run_realtime_workflow.py ---")
