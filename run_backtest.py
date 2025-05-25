#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
回测执行脚本 (入口点)

负责加载配置、初始化回测引擎并启动回测。
"""

import logging
import sys
import argparse
import os 
from pathlib import Path # <--- 导入 Path

# 将项目根目录添加到 sys.path，确保可以找到 backtesting 包
project_root = Path(__file__).resolve().parent # <--- 定义为 Path 对象
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root)) # 插入到最前面，优先搜索

from omegaconf import DictConfig, OmegaConf
from core.utils import load_app_config, setup_logging

# 导入核心回测引擎
try:
    from backtesting.engine import BacktestEngine
except ImportError:
    logging.basicConfig(level=logging.ERROR) # 基本日志以显示错误
    logging.error("无法导入 BacktestEngine，请确保 backtesting/engine.py 文件存在且路径正确。")
    sys.exit(1)

# --- 主程序入口 ---

def main():
    """
    主执行函数。
    """
    parser = argparse.ArgumentParser(description='运行事件驱动策略回测')
    parser.add_argument('--config', default='backtesting/config/backtest.yaml', 
                        help='模块特定配置文件的路径 (相对于项目根目录，例如 backtesting/config/backtest.yaml)')
    args = parser.parse_args()

    config: Optional[DictConfig] = None
    logger = logging.getLogger(__name__) # Get logger early for config loading errors

    try:
        # 1. 加载配置 using shared utility
        logger.info(f"尝试加载配置 (common.yaml + {args.config} + event_mapping.yaml)...")
        config = load_app_config(
            module_config_rel_path=args.config
        )
        logger.info("配置加载成功。")
        # --- DEBUG: Check config type IMMEDIATELY after loading ---
        logger.info(f"[调试] load_app_config 返回的 config 类型: {type(config)}")
        if not isinstance(config, DictConfig):
             logger.error("[调试] 错误：load_app_config 未返回 DictConfig！")
             # return # 可以选择在这里直接退出
        # -------------------------------------------------------
    except FileNotFoundError as e:
        logger.error(f"无法加载配置文件: {e}。请确保 common.yaml 和 {args.config} 路径正确。")
        return
    except Exception as e:
        logger.error(f"加载配置文件 {args.config} 时发生意外错误: {e}", exc_info=True)
        return

    if not config:
        logger.error("配置文件加载后为空，退出。")
        return

    # 2. 配置日志 (修改为直接配置根 logger)
    try:
        log_filename = OmegaConf.select(config, 'logging.backtest_log_filename', default='backtest.log')
        # 使用 Path 对象进行路径拼接
        log_dir_relative = OmegaConf.select(config, 'logging.log_dir', default='logs')
        log_dir_path = project_root / log_dir_relative # <--- 使用 Path 对象拼接
        log_dir_path.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir_path / log_filename

        log_level_str = OmegaConf.select(config, 'logging.level', default='INFO').upper()
        file_log_level = logging.DEBUG  # 文件强制 DEBUG
        console_log_level_str = OmegaConf.select(config, 'logging.console_level', default=log_level_str).upper()
        console_log_level = getattr(logging, console_log_level_str, logging.INFO)
        root_logger_config_level = getattr(logging, log_level_str, logging.INFO)

        formatter_str = OmegaConf.select(config, 'logging.formatter', default='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        formatter = logging.Formatter(formatter_str)

        # 配置根日志记录器
        root_logger = logging.getLogger() # 获取根 logger
        root_logger.setLevel(min(root_logger_config_level, file_log_level)) # 设置根logger为两者中更低的级别，确保DEBUG能通过

        # 清除根 logger 可能存在的旧 handlers (重要，避免重复日志)
        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        # 创建文件处理器
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_log_level) # 强制 DEBUG
        root_logger.addHandler(file_handler)

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(console_log_level)
        root_logger.addHandler(console_handler)

        logger = logging.getLogger('BacktestRun') # 获取特定的 logger 实例供当前脚本使用
        logger.info(f"根日志系统已配置，文件输出到: {log_file_path} (级别: DEBUG)，控制台级别: {console_log_level_str}")

    except Exception as log_e:
         # Use basic print if logging setup fails critically
         print(f"CRITICAL: 配置日志系统时出错: {log_e}", file=sys.stderr)
         # Fallback to basic logging if setup fails
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
         logger = logging.getLogger(__name__ + '_Fallback')
         logger.error("Logging setup failed, using basic config.", exc_info=True)

    # --- DEBUG: Check config type before passing to engine ---
    logger.info(f"[调试] 准备传递给 BacktestEngine 的 config 类型: {type(config)}")
    # logger.debug(f"[调试] Config 内容: {config}") # 如果需要看内容，取消注释此行
    # ---------------------------------------------------------

    # --- 新增：获取 strategy_name ---
    strategy_name = OmegaConf.select(config, 'backtest.strategy_name', default=None)
    if not strategy_name:
        logger.error("配置错误：在配置文件的 'backtest' 部分下必须指定 'strategy_name'。")
        return
    logger.info(f"从配置中获取到策略名称: {strategy_name}")
    # --- 结束新增 ---

    # 3. 初始化并运行回测引擎
    try:
        logger.info(f"使用策略 '{strategy_name}' 和配置 {args.config} 初始化回测引擎...")
        # Pass the loaded OmegaConf object AND strategy_name to the engine
        engine = BacktestEngine(config, strategy_name) # <-- 传递 strategy_name
        results = engine.run() # run 方法现在负责数据加载、策略初始化和循环

        if results:
            logger.info("回测成功完成。")
            # 在这里可以添加更复杂的结果处理和报告生成
            # print("回测结果摘要:", results)
        else:
            logger.warning("回测运行未产生有效结果或中途失败。")

    except ImportError as e:
         logger.error(f"初始化或运行回测引擎时发生导入错误: {e}。请检查依赖项和路径。")
    except Exception as e:
        logger.error(f"运行回测时发生未处理的异常: {e}", exc_info=True)

if __name__ == "__main__":
    main()