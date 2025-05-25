#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量运行所有策略的回测脚本。

该脚本会自动扫描 'strategies' 目录下的策略文件，
为每个策略运行一次回测，并尝试将结果重命名以包含策略名称。
"""

import sys
import os
import logging
import importlib
import re
import time
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from omegaconf import OmegaConf, DictConfig, errors as OmegaErrors
import inspect # 用于isclass和getmembers
# from strategies.core.strategy_base import StrategyBase # 用于issubclass检查
from datetime import datetime
import pandas as pd
from datetime import timedelta
import pkg_resources
import json
import csv

# --- 项目路径设置 (假设脚本在项目根目录) ---
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path: # UNCOMMENT
    sys.path.insert(0, str(PROJECT_ROOT)) # UNCOMMENT

# --- 核心模块导入 ---
# 假设脚本在项目根目录，可以直接导入
from core.utils import load_app_config, setup_logging
from backtesting.engine import BacktestEngine, StrategyInitializationError
from strategies.core.strategy_base import StrategyBase # 添加 StrategyBase 的直接导入

# try: # REMOVE
#     from core.utils import load_app_config, setup_logging # REMOVE
#     from backtesting.engine import BacktestEngine # REMOVE
# except ImportError as e: # REMOVE
#     # 尝试从上一级目录的 core 和 backtesting 导入 (如果脚本在子目录中) # REMOVE
#     sys.path.insert(0, str(PROJECT_ROOT.parent)) # REMOVE
#     from core.utils import load_app_config, setup_logging # REMOVE
#     from backtesting.engine import BacktestEngine # REMOVE

# --- 全局变量和常量 ---
STRATEGIES_DIR = PROJECT_ROOT / "strategies"
STRATEGY_FILE_PATTERN = re.compile(r"^(?!__).+?_strategy\.py$") # 匹配 _strategy.py 结尾且不以 __ 开头
BASE_BACKTEST_CONFIG_PATH = "backtesting/config/backtest.yaml"
RESULTS_DIR = PROJECT_ROOT / "backtesting" / "results"
LOG_FILE_NAME = "batch_backtest_main.log" # 日志文件名

# 初始化一个全局 logger，稍后由 setup_batch_logging 配置
logger = logging.getLogger("BatchBacktester")
# 先给一个基本的配置，防止在 setup_batch_logging 之前调用 logger 出现 "No handlers could be found"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def setup_batch_logging(config: Optional[DictConfig]) -> Path:
    """
    配置批量回测的主日志记录器。
    日志文件名将包含时间戳，并且会自动清理旧的日志文件，只保留最新的N个（可通过环境变量LOGS_TO_KEEP设置，默认3个）。
    """
    global logger
    
    # --- 日志文件清理逻辑 ---
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True) # 确保日志目录存在

    # --- 新增：显式删除旧的、不带时间戳的日志文件 ---
    legacy_log_file_path = logs_dir / LOG_FILE_NAME # LOG_FILE_NAME is "batch_backtest_main.log"
    if legacy_log_file_path.exists():
        try:
            legacy_log_file_path.unlink()
            logger.info(f"[Log Cleanup] 已删除旧的无时间戳日志文件: {legacy_log_file_path}")
        except OSError as e:
            logger.warning(f"[Log Cleanup] 删除旧的无时间戳日志文件 {legacy_log_file_path} 失败: {e}")
    # --- 结束新增 ---
    
    # 匹配文件名模式 batch_backtest_main_YYYYMMDD_HHMMSS.log
    log_file_pattern = "batch_backtest_main_*.log" # This pattern is for existing timestamped logs
    existing_log_files = sorted(
        list(logs_dir.glob(log_file_pattern)),
        key=os.path.getmtime, # 按修改时间排序，越近的越靠后
        reverse=True # 最新的在前
    )
    
    # 支持通过环境变量自定义保留日志份数
    try:
        num_logs_to_keep = int(os.environ.get("LOGS_TO_KEEP", 3))
    except Exception:
        num_logs_to_keep = 3
    if len(existing_log_files) >= num_logs_to_keep:
        logs_to_delete = existing_log_files[num_logs_to_keep-1:]
        for log_to_delete in logs_to_delete:
            try:
                log_to_delete.unlink()
                # Use print here as logger might not be fully set up or might write to the file being deleted
                logger.info(f"[Log Cleanup] 已删除旧的日志文件: {log_to_delete}")
            except OSError as e:
                logger.warning(f"[Log Cleanup] 删除旧日志文件 {log_to_delete} 失败: {e}")
    # --- 清理逻辑结束 ---

    log_level_str = "INFO"
    # 生成带时间戳的日志文件名
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_log_file_name_with_ts = f"batch_backtest_main_{timestamp_str}.log" # MODIFIED: Removed RUN_ prefix
    actual_log_file = logs_dir / current_log_file_name_with_ts # This is the file we will use

    log_format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s' # Default format

    if config and "logging" in config:
        log_settings = config.get("logging", {})
        log_level_str = log_settings.get("level", "INFO").upper()
        log_format_str = log_settings.get("format", log_format_str)
        # The filename from config is ignored in favor of the timestamped one for this script.

    # 确保日志目录存在 (actual_log_file.parent is logs_dir, already created)
    # actual_log_file.parent.mkdir(parents=True, exist_ok=True) 

    # 清理旧的 handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
        
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(numeric_level)

    # 文件处理器 - USE actual_log_file
    fh = logging.FileHandler(actual_log_file, mode='w', encoding='utf-8')
    fh.setLevel(numeric_level)

    # 控制台处理器
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(numeric_level)

    formatter = logging.Formatter(log_format_str)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    
    logger.propagate = False
    
    return actual_log_file # MODIFIED: Return the actual path used


def find_strategies(strategies_dir: Path) -> List[Tuple[str, str]]:
    """
    扫描策略目录，找到所有符合命名规范的策略文件及其主策略类。
    返回一个包含 (模块路径字符串, 类名字符串) 的元组列表。
    """
    found_strategies: List[Tuple[str, str]] = []
    if not strategies_dir.is_dir():
        logger.error(f"策略目录 '{strategies_dir}' 不存在或不是一个目录。")
        return found_strategies

    for root, dirs, files in os.walk(strategies_dir):
        # 过滤掉 __pycache__ 和可能存在的 .ipynb_checkpoints 等隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != "__pycache__"]
        
        current_path = Path(root)
        for filename in files:
            match = STRATEGY_FILE_PATTERN.match(filename)
            if match:
                module_name = filename[:-3]  # 移除 .py 后缀
                # 构建相对模块路径，例如 strategies.my_strategy
                relative_module_path_parts = list(current_path.relative_to(PROJECT_ROOT).parts)
                
                # 如果 current_path 就是 strategies_dir (即 PROJECT_ROOT / "strategies")
                # 那么 relative_to(PROJECT_ROOT) 会得到 "strategies"
                # 我们需要确保模块路径是 strategies.module_name
                # 而不是 strategies.strategies.module_name
                
                # 修正：确保模块路径从 "strategies" 开始
                if relative_module_path_parts and relative_module_path_parts[0] == STRATEGIES_DIR.name:
                    module_path_str = ".".join(relative_module_path_parts + [module_name])
                else:
                    # 如果 strategies_dir 本身就是 PROJECT_ROOT/strategies，
                    # 并且 os.walk 的 root 也是 strategies_dir，
                    # 那么 current_path.relative_to(PROJECT_ROOT) 会是 ['strategies']
                    # 如果 root 是 PROJECT_ROOT/strategies/subdir,
                    # 那么 current_path.relative_to(PROJECT_ROOT) 会是 ['strategies', 'subdir']
                    # 所以，通常我们希望从 STRATEGIES_DIR.name (即 "strategies") 开始
                    module_path_str = f"{STRATEGIES_DIR.name}.{'.'.join(list(current_path.relative_to(strategies_dir).parts) + [module_name])}".replace("..", ".") # 处理空parts

                # 动态导入模块并检查类
                try:
                    strategy_module = importlib.import_module(module_path_str)
                    expected_class_name = module_name.replace("_", "").title().replace("Strategy", "") + "Strategy"
                    
                    for name, member in inspect.getmembers(strategy_module):
                        # 进一步检查是否是我们定义的策略类，而不是导入的基类或其他
                        if inspect.isclass(member) and \
                           issubclass(member, StrategyBase) and \
                           member is not StrategyBase and \
                           not getattr(member, '_is_abstract', False) and \
                           member.__module__ == strategy_module.__name__:
                            # 优先匹配与文件名相似的类名，或以 "Strategy" 结尾的类名
                            # 确保我们只添加在当前模块中定义的类，而不是导入的类
                            # （member.__module__ == strategy_module.__name__）
                            if name == expected_class_name or name.endswith("Strategy"):
                                found_strategies.append((module_path_str, name))
                                logger.info(f"发现策略: 模块='{module_path_str}', 类='{name}'")
                                break # 假设每个文件只定义一个主策略类
                    else: # 如果循环正常结束（没有break），说明没找到符合条件的类
                        logger.warning(f"在模块 '{module_path_str}' 中未找到主要的策略类 (继承自 StrategyBase 且在模块内定义)。")
                            
                except ImportError as e:
                    # 特别处理 ModuleNotFoundError，通常意味着路径计算或文件结构问题
                    if isinstance(e, ModuleNotFoundError):
                        logger.error(f"导入模块 '{module_path_str}' 失败: 模块未找到。请检查PYTHONPATH和文件结构。错误: {e}")
                    else:
                        logger.error(f"导入模块 '{module_path_str}' 失败: {e}")
                except Exception as e:
                    logger.error(f"处理模块 '{module_path_str}' 时发生未知错误: {e}", exc_info=True)
    
    if not found_strategies:
        logger.warning(f"在 '{strategies_dir}' 目录下未扫描到任何策略文件。")
    
    logger.info(f"[find_strategies DEBUG] 最终发现的策略列表 (共 {len(found_strategies)} 个): {found_strategies}") # <-- 新增日志
    return found_strategies

def run_single_backtest(strategy_module: str, strategy_class: str, base_config: DictConfig) -> tuple:
    """
    运行单个策略的回测。
    返回(success, reason)。
    """
    success = False
    reason = None
    start_time = time.time()
    
    # 为当前策略创建一个新的配置副本，以避免修改原始配置
    strategy_config_for_run = base_config.copy() # 使用新变量名以示清晰
    
    # 更新配置中的策略名称 (确保 backtest.strategy_name 被正确设置)
    # BacktestEngine 将从这里读取 strategy_name
    OmegaConf.update(strategy_config_for_run, "backtest.strategy_name", strategy_class, merge=True)
    # 将 strategy_module (即模块路径) 添加到配置中，供 BacktestEngine 使用
    OmegaConf.update(strategy_config_for_run, "backtest.engine.strategy_module_path", strategy_module, merge=False)

    logger.info(f"准备运行策略: {strategy_class} (来自模块 {strategy_module})")
    logger.debug(f"传递给单个回测的配置副本 (strategy_config_for_run) backtest.strategy_name 已更新为: {OmegaConf.select(strategy_config_for_run, 'backtest.strategy_name')}, backtest.engine.strategy_module_path 设置为: {strategy_module}")
    
    # 为当前策略的 BacktestEngine logger 添加详细的文件日志处理器
    engine_logger_name = f"BacktestEngine.{strategy_class}"
    engine_specific_logger = logging.getLogger(engine_logger_name)
    
    # 清理该 logger 可能已有的旧处理器，以防重复添加
    for handler in engine_specific_logger.handlers[:]:
        engine_specific_logger.removeHandler(handler)
        handler.close()
        
    engine_specific_logger.setLevel(logging.DEBUG) # 捕获 DEBUG 及以上级别
    
    log_dir_for_engine = PROJECT_ROOT / "logs"
    log_dir_for_engine.mkdir(parents=True, exist_ok=True)
    engine_log_file = log_dir_for_engine / f"{strategy_class}_engine_debug_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
    
    fh_engine = logging.FileHandler(engine_log_file, mode='w', encoding='utf-8')
    fh_engine.setLevel(logging.DEBUG)
    # 使用与主 logger 相似的格式，但可以区分
    formatter_engine = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(lineno)d - %(message)s')
    fh_engine.setFormatter(formatter_engine)
    engine_specific_logger.addHandler(fh_engine)
    engine_specific_logger.propagate = False # 通常不希望引擎日志进入主批量日志，除非专门设计
    
    logger.info(f"已为 {engine_logger_name} 配置详细日志到: {engine_log_file}")

    try:
        # 从更新后的配置中提取策略名称，用于传递给 BacktestEngine
        # strategy_name_for_engine 应该就是 strategy_class
        # merged_config 就是 strategy_config_for_run
        
        engine = BacktestEngine(
            merged_config=strategy_config_for_run, 
            strategy_name_from_config=strategy_class # 直接使用 strategy_class 作为从配置中解析出的策略名
        )
        logger.info(f"回测引擎已为策略 {strategy_class} 初始化。")
        
        # 运行回测，现在 engine.run() 会在内部失败时抛出异常
        engine.run() 
        logger.info(f"策略 {strategy_class} 回测运行方法成功结束。")

        # 如果 engine.run() 没有抛出异常，我们认为它成功了
        logger.info(f"策略 {strategy_class} 回测已成功完成。")
        success = True
        reason = None

    # --- 捕获特定的已知异常 --- 
    except OmegaErrors.ConfigKeyError as e:
        logger.error(f"策略 {strategy_class} 回测失败: 配置项错误 - {e}")
        reason = f"配置项错误: {e}"
    except ImportError as e:
        logger.error(f"策略 {strategy_class} 回测失败: 无法导入策略模块或其依赖 - {e}")
        reason = f"导入失败: {e}"
    except AttributeError as e:
        logger.error(f"策略 {strategy_class} 回测失败: 策略类或方法未找到 - {e}")
        reason = f"类/方法未找到: {e}"
    except TypeError as e:
        logger.error(f"策略 {strategy_class} 回测失败: 策略初始化参数错误 - {e}")
        reason = f"初始化参数错误: {e}"
    
    # --- 捕获来自 BacktestEngine.run 的异常 --- 
    except StrategyInitializationError as e: # 捕获策略初始化期间的特定错误
        logger.error(f"策略 {strategy_class} 回测失败: 策略初始化错误 (由 BacktestEngine 抛出) - {e}")
        reason = f"策略初始化错误: {e}"

    # --- 捕获其他所有未知异常 --- 
    except Exception as e:
        logger.error(f"策略 {strategy_class} 回测时发生未知错误: {e}", exc_info=True) # exc_info=True 会记录堆栈跟踪
        reason = f"未知错误: {e}"
    
    end_time = time.time()
    logger.info(f"策略 {strategy_class} 回测耗时: {end_time - start_time:.2f} 秒。结果: {'成功' if success else '失败'}")
    return success, reason

def main():
    global logger # 明确使用全局 logger
    actual_log_file_path_for_summary = PROJECT_ROOT / 'logs' / LOG_FILE_NAME # Default before setup

    # === 新增：--help参数支持 ===
    import sys
    help_text = '''\n用法: python run_all_backtests.py [--help|-h]\n\n功能：\n  - 批量自动回测所有策略，自动检测依赖和数据文件，输出详细日志和结果汇总。\n  - 支持多策略多品种多周期，自动导出回测结果csv/json。\n  - 自动检测并修复依赖，输出修复命令建议。\n  - 日志文件轮转，支持自定义保留份数（环境变量LOGS_TO_KEEP）。\n\n常见问题：\n  - 数据文件缺失：请根据日志提示补充数据，或运行推荐的数据下载脚本。\n  - 依赖缺失：请根据日志提示运行pip install命令。\n  - 日志乱码：请在Windows终端执行chcp 65001，并确保终端字体支持UTF-8。\n  - 仅回测部分策略：可在脚本中设置DEBUG_SINGLE_STRATEGY变量。\n\n更多帮助请查阅项目文档或联系开发者。\n'''
    if any(arg in sys.argv for arg in ["--help", "-h"]):
        logger.info(help_text)
        return
    # === --help参数支持结束 ===

    # --- (可选) 调试：只运行单个特定策略 ---
    DEBUG_SINGLE_STRATEGY = None # 设置为 None 或 "" 以运行所有策略
    # DEBUG_SINGLE_STRATEGY = "KeyTimeWeightTurningPointStrategy" 
    # --- 结束调试设置 ---

    # --- 加载基础配置 ---
    # load_app_config 期望一个参数：模块特定配置的相对路径。
    # 它内部会自动加载和合并 config/common.yaml。
    # BASE_BACKTEST_CONFIG_PATH ("backtesting/config/backtest.yaml") 作为模块配置。
    base_config: Optional[DictConfig] = None
    try:
        logger.info(f"尝试加载基础回测配置: {BASE_BACKTEST_CONFIG_PATH} (将与 common.yaml 合并)")
        base_config = load_app_config(BASE_BACKTEST_CONFIG_PATH) 
        # --- 调试日志：检查 base_config 加载后的关键参数 ---
        if base_config:
            logger.info("基础配置加载成功。")
            engine_node = OmegaConf.select(base_config, "backtest.engine", default=None)
            if engine_node:
                start_date_check = OmegaConf.select(engine_node, "start_date", default="NOT_FOUND")
                end_date_check = OmegaConf.select(engine_node, "end_date", default="NOT_FOUND")
                symbols_check = OmegaConf.select(engine_node, "symbols", default="NOT_FOUND")
                logger.debug(f"[调试 Main] 基础配置中 backtest.engine.start_date: {start_date_check}")
                logger.debug(f"[调试 Main] 基础配置中 backtest.engine.end_date: {end_date_check}")
                logger.debug(f"[调试 Main] 基础配置中 backtest.engine.symbols: {OmegaConf.to_container(symbols_check) if symbols_check != 'NOT_FOUND' else 'NOT_FOUND'}")
            else:
                logger.error("[调试 Main] 基础配置中未找到 'backtest.engine' 节点！")
        # ----------------------------------------------------
    except FileNotFoundError as e:
        logger.error(f"无法加载基础回测配置文件 {BASE_BACKTEST_CONFIG_PATH} 或其依赖的 common.yaml: {e}")
        return # 关键配置失败，无法继续
    except Exception as e:
        logger.error(f"加载基础配置时发生未知错误: {e}", exc_info=True)
        return # 关键配置失败，无法继续

    if not base_config:
        logger.error("基础配置对象未能成功创建，批量回测中止。")
        return
    
    # --- 设置日志 (现在使用已加载的 base_config) ---
    actual_log_file_path_for_summary = setup_batch_logging(base_config) # MODIFIED: Capture the returned path
    
    logger.info("=== 开始批量回测 ===")
    logger.info(f"扫描策略目录: {STRATEGIES_DIR}")

    discovered_strategies = find_strategies(STRATEGIES_DIR)
    logger.info(f"[main DEBUG] 从 find_strategies 返回的策略列表 (共 {len(discovered_strategies)} 个): {discovered_strategies}") # <-- 新增日志

    # === 新增：每个策略动态解析其symbol/timeframe需求，按需检测数据文件 ===
    for strategy_module, strategy_class in discovered_strategies:
        try:
            mod = importlib.import_module(strategy_module)
            cls = getattr(mod, strategy_class)
            # 优先尝试类属性/方法
            symbols = []
            timeframes = []
            if hasattr(cls, 'get_symbols') and callable(getattr(cls, 'get_symbols')):
                symbols = cls.get_symbols()
            elif hasattr(cls, 'symbols'):
                symbols = getattr(cls, 'symbols')
            if hasattr(cls, 'get_timeframes') and callable(getattr(cls, 'get_timeframes')):
                timeframes = cls.get_timeframes()
            elif hasattr(cls, 'timeframes'):
                timeframes = getattr(cls, 'timeframes')
            # 兼容字符串/None
            if isinstance(symbols, str):
                symbols = [symbols]
            if isinstance(timeframes, str):
                timeframes = [timeframes]
            if not timeframes:
                timeframes = ["M30"]
            if not symbols:
                logger.warning(f"策略 {strategy_class} 未指定symbols，数据文件检测将跳过。")
            else:
                for symbol in symbols:
                    for tf in timeframes:
                        tf_lower = tf.lower()
                        data_file = PROJECT_ROOT / f"data/historical/{symbol}/{symbol}_{tf_lower}.csv"
                        if not data_file.exists():
                            logger.error(f"策略 {strategy_class} 缺失数据文件: {data_file}，建议补充。可运行 'python scripts/download_data.py --symbol {symbol} --timeframe {tf}' 或联系数据管理员。")
        except Exception as e:
            logger.warning(f"策略 {strategy_class} 动态解析symbols/timeframes失败: {e}")
    # === 动态检测结束 ===

    # === 新增：数据文件基础内容校验 ===
    for symbol in symbols:
        for tf in timeframes:
            tf_lower = tf.lower()
            data_file = PROJECT_ROOT / f"data/historical/{symbol}/{symbol}_{tf_lower}.csv"
            if data_file.exists():
                try:
                    df = pd.read_csv(data_file)
                    # 检查空行
                    if df.isnull().all(axis=1).any():
                        logger.warning(f"数据文件 {data_file} 存在空行，建议清理。")
                    # 检查时间连续性（假设有'time'或'datetime'列，且为升序）
                    time_col = None
                    for col in ['datetime', 'time', 'timestamp']:
                        if col in df.columns:
                            time_col = col
                            break
                    if time_col:
                        times = pd.to_datetime(df[time_col], errors='coerce')
                        if times.isnull().any():
                            logger.warning(f"数据文件 {data_file} 存在无法解析的时间戳，建议检查格式。")
                        else:
                            # 计算时间间隔
                            deltas = times.diff().dropna()
                            # M30应为30分钟
                            expected_delta = timedelta(minutes=30)
                            large_gaps = deltas[deltas > expected_delta * 1.5]
                            if not large_gaps.empty:
                                logger.warning(f"数据文件 {data_file} 存在时间间隔异常（如缺失数据），共{len(large_gaps)}处。建议补全或剔除异常段。")
                    else:
                        logger.warning(f"数据文件 {data_file} 未找到时间列（如datetime/time/timestamp），无法校验时间连续性。")
                except Exception as e:
                    logger.warning(f"数据文件 {data_file} 校验时发生异常: {e}")
    # === 数据文件内容校验结束 ===

    # === 新增：依赖检测与requirements.txt自动维护 ===
    REQUIRED_DEPENDENCIES = [
        ("pandas", ">=1.3.0"),
        ("omegaconf", ">=2.0.0"),
        ("numpy", ">=1.20.0"),
    ]
    requirements_path = PROJECT_ROOT / "requirements.txt"
    requirements_lines = []
    if requirements_path.exists():
        with open(requirements_path, "r", encoding="utf-8") as f:
            requirements_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    updated = False
    for pkg, ver in REQUIRED_DEPENDENCIES:
        try:
            mod = importlib.import_module(pkg)
            installed_ver = pkg_resources.get_distribution(pkg).version
            if not pkg_resources.require(f"{pkg}{ver}"):
                logger.warning(f"依赖 {pkg} 版本 {installed_ver} 不满足要求 {ver}，建议运行：pip install '{pkg}{ver}'")
                logger.info(f"修复命令：pip install '{pkg}{ver}'")
            # 自动维护requirements.txt
            req_line = f"{pkg}{ver}"
            if not any(l.startswith(pkg) for l in requirements_lines):
                requirements_lines.append(req_line)
                updated = True
        except Exception as e:
            logger.warning(f"依赖 {pkg} 未安装或检测失败，建议运行：pip install '{pkg}{ver}'。错误: {e}")
            logger.info(f"修复命令：pip install '{pkg}{ver}'")
            req_line = f"{pkg}{ver}"
            if not any(l.startswith(pkg) for l in requirements_lines):
                requirements_lines.append(req_line)
                updated = True
    if updated:
        with open(requirements_path, "w", encoding="utf-8") as f:
            for line in requirements_lines:
                f.write(line + "\n")
        logger.info("requirements.txt 已自动更新。请在虚拟环境中运行 pip install -r requirements.txt 以同步依赖。")
    # === 依赖检测与requirements.txt维护结束 ===

    total_strategies_to_run = 0
    successful_runs = 0
    failed_runs = 0
    failed_details = []

    # 确保结果目录存在
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for strategy_module, strategy_class in discovered_strategies:
        total_strategies_to_run += 1
        logger.info(f"--- 开始回测策略: {strategy_class} ---")
        success, reason = run_single_backtest(strategy_module, strategy_class, base_config)
        if success:
            successful_runs += 1
        else:
            failed_runs += 1
            failed_details.append((strategy_class, reason))
        logger.info(f"--- 结束回测策略: {strategy_class} ---")

    # 5. 打印总结
    logger.info("-----------------------------------------------------------")
    logger.info("===========================================================")
    logger.info("                    批量回测结束 Summary")
    logger.info("===========================================================")
    logger.info(f"总计策略尝试运行: {total_strategies_to_run}")
    logger.info(f"成功运行: {successful_runs}")
    logger.info(f"失败运行: {failed_runs}")
    logger.info(f"详细日志请查看文件: {actual_log_file_path_for_summary}") # MODIFIED: Use the actual path
    logger.info(f"策略回测结果文件位于目录: {RESULTS_DIR}")
    logger.info("===========================================================")

    logger.info("\n--- 批量回测脚本执行完毕 ---")
    if failed_runs == 0 and successful_runs > 0 :
        logger.info("所有策略回测成功完成！")
    elif successful_runs > 0 and failed_runs > 0:
        logger.info(f"{successful_runs} 个策略回测成功，{failed_runs} 个策略回测失败。请检查日志。")
    elif failed_runs > 0 and successful_runs == 0:
        logger.info(f"所有 {failed_runs} 个策略回测均失败。请检查日志。")
    else: # successful_runs == 0 and failed_runs == 0 (理论上在前面 strategies_to_run 为空时已处理)
        logger.info("没有策略被执行。")

    if failed_runs > 0:
        logger.info("失败策略详情:")
        for strategy, reason in failed_details:
            logger.info(f"- {strategy}: {reason}")

    # === 新增：回测结果自动导出 ===
    summary_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_csv = RESULTS_DIR / f"batch_backtest_summary_{summary_time}.csv"
    summary_json = RESULTS_DIR / f"batch_backtest_summary_{summary_time}.json"
    all_results = []
    for strategy_module, strategy_class in discovered_strategies:
        fail = next((fd for fd in failed_details if fd[0] == strategy_class), None)
        result = {
            "strategy": strategy_class,
            "module": strategy_module,
            "success": fail is None,
            "reason": fail[1] if fail else None
        }
        all_results.append(result)
    with open(summary_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["strategy", "module", "success", "reason"])
        writer.writeheader()
        writer.writerows(all_results)
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"回测结果已导出: {summary_csv} 和 {summary_json}")
    # === 导出结束 ===


if __name__ == "__main__":
    # 确保日志目录存在，即使 main() 中的逻辑出错
    try:
        (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # 在日志系统完全建立前，只能 print
        logger.critical(f"CRITICAL:无法创建日志目录 '{(PROJECT_ROOT / 'logs')}' : {e}")
        # 可以选择是否在这里退出，或者让后续的日志配置尝试处理

    # 捕获 main 函数中的顶层异常，确保至少有日志记录
    try:
        main()
    except Exception as e:
        # 尝试使用已经配置的 logger (如果 main 中成功配置了)
        # 如果 logger 配置失败，这个日志可能不会写入文件，但会尝试打印到控制台
        logger.critical("批量回测脚本 main() 函数发生未捕获的顶层异常: %s", e, exc_info=True)
        logger.critical(f"CRITICAL ERROR in main(): {e}")
        # 可以在这里添加更详细的错误恢复或退出逻辑
        sys.exit(1) # 以错误码退出