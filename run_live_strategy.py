"""
主入口脚本，用于启动实盘策略交易。

负责：
1. 加载配置。
2. 检查交易日和 MT5 进程。
3. 按需启动和管理 RealtimeUpdater 数据服务进程。
4. 初始化数据提供者、执行引擎和策略编排器。
5. 启动策略执行循环。
6. 在退出时确保 RealtimeUpdater 被停止。
"""

import datetime as dt
import subprocess
import sys
import os
import time
import signal
import atexit
from pathlib import Path
import logging

try:
    import psutil # 用于检查进程
except ImportError:
    print("错误：需要安装 'psutil' 库。请运行 'pip install psutil'")
    sys.exit(1)

try:
    from omegaconf import OmegaConf, DictConfig # 用于配置管理
except ImportError:
    print("错误：需要安装 'omegaconf' 库。请运行 'pip install omegaconf'")
    sys.exit(1)

# --- 假设的 core.utils 和 strategies 模块导入 ---
try:
    from core.utils import load_app_config, setup_logging, shutdown_mt5 # shutdown_mt5 可能也需要
    # 假设 load_app_config 会合并 common.yaml 和指定的模块配置
except ImportError:
    print("错误：无法从 core.utils 导入所需函数。请确保 PYTHONPATH 正确设置。")
    # 提供临时的简单实现以便脚本能运行（仅用于演示结构）
    def load_app_config(*args, **kwargs):
        print("警告：使用临时的 load_app_config 存根。")
        # 实际应加载并合并 yaml 文件
        # 这里返回一个基础结构以避免后续代码出错
        return OmegaConf.create({
            'paths': {'data_dir': 'data'},
            'strategies': {'config': {'module_yaml_path': 'strategies/config/module.yaml'}},
            'logging': {'level': 'INFO', 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'},
            'execution': {'mt5': {}}, # 添加空的 mt5 执行配置
            'realtime': {} # 添加空的 realtime 配置
        })
    def setup_logging(log_config, filename, logger_name):
        print(f"警告：使用临时的 setup_logging 存根 for {logger_name}")
        _logger = logging.getLogger(logger_name)
        logging.basicConfig(level=log_config.get('level', 'INFO'), format=log_config.get('format'))
        # 实际应配置 handlers 等
        return _logger
    def shutdown_mt5(*args, **kwargs): pass
    # sys.exit(1) # 在实际使用中，如果无法导入核心工具，应该退出

try:
    from strategies.core.data_providers import DataProvider
    from strategies.live.mt5_engine import MT5ExecutionEngine
    from strategies.core.strategy_orchestrator import StrategyOrchestrator
except ImportError as e:
    print(f"错误：无法从 strategies 模块导入所需类: {e}")
    print("请确保 strategies 模块在 Python 路径中且结构正确。")
    # 在实际使用中应退出
    # sys.exit(1)
    # 提供假的类定义以演示结构
    class DataProvider: pass
    class MT5ExecutionEngine:
        def connect(self): print("模拟连接 MT5...")
        def disconnect(self): print("模拟断开 MT5...")
    class StrategyOrchestrator:
        def __init__(self, config, data_provider, execution_engine): pass
        def start(self, interval_seconds=60): print(f"模拟运行策略，间隔 {interval_seconds}s..."); time.sleep(3600)
        def stop(self): print("模拟停止策略...") # Add stop if needed by cleanup

# --- 配置常量 ---
PROJECT_ROOT = Path(__file__).resolve().parent
# 注意：从配置加载 data_dir，这里提供默认值以防万一
DATA_DIR_DEFAULT = PROJECT_ROOT / "data"
# PID 和 Stop 文件名应与 RealtimeUpdater 中定义的一致
PID_FILENAME = "realtime_updater.pid"
STOP_FLAG_FILENAME = "STOP_REALTIME.flag"
# RealtimeUpdater 启动命令
UPDATER_SCRIPT_MODULE = "market_price_data.scripts.data_updater"
UPDATER_SCRIPT_ARGS = ["realtime"]

# --- 全局变量 ---
config: Optional[DictConfig] = None
logger: Optional[logging.Logger] = None
data_dir: Path = DATA_DIR_DEFAULT
pid_file_path: Optional[Path] = None
stop_flag_path: Optional[Path] = None
updater_started_by_this_script: bool = False
mt5_engine_instance: Optional[MT5ExecutionEngine] = None # Add global for cleanup
strategy_orchestrator_instance: Optional[StrategyOrchestrator] = None # Add global for cleanup

# --- 清理函数 --- (Revised)
def cleanup_updater_and_engine():
    """在脚本退出时停止 RealtimeUpdater (如果由本脚本启动) 并断开 MT5 Engine 连接。"""
    global logger, mt5_engine_instance, strategy_orchestrator_instance

    if logger: logger.info("执行退出清理...")
    else: print("执行退出清理...")

    # 1. 停止 Orchestrator (如果它有 stop 方法并且正在运行)
    #    这可能不是必须的，因为脚本退出会终止其循环，但如果需要优雅处理内部状态可以调用
    if strategy_orchestrator_instance and hasattr(strategy_orchestrator_instance, 'stop'):
        try:
            if logger: logger.info("正在调用 StrategyOrchestrator.stop()...")
            strategy_orchestrator_instance.stop()
        except Exception as e:
            if logger: logger.error(f"调用 Orchestrator.stop() 时出错: {e}", exc_info=True)
            else: print(f"调用 Orchestrator.stop() 时出错: {e}")

    # 2. 停止由本脚本启动的 RealtimeUpdater (逻辑不变)
    cleanup_updater() # 调用之前的 updater 清理逻辑

    # 3. 断开 MT5 Engine 连接
    if mt5_engine_instance:
        if logger: logger.info("正在断开 MT5 Execution Engine 连接...")
        else: print("正在断开 MT5 Execution Engine 连接...")
        try:
            mt5_engine_instance.disconnect()
            if logger: logger.info("MT5 Execution Engine 已断开。")
            else: print("MT5 Execution Engine 已断开。")
        except Exception as e:
            if logger: logger.error(f"断开 MT5 Execution Engine 时出错: {e}", exc_info=True)
            else: print(f"断开 MT5 Execution Engine 时出错: {e}")

    if logger: logger.info("退出清理完成。")
    else: print("退出清理完成。")

# --- 注册清理和信号处理 ---
atexit.register(cleanup_updater_and_engine)

def handle_exit_signal(sig, frame):
    global logger
    msg = f"\n收到信号 {sig}，准备退出..."
    if logger: logger.info(msg)
    else: print(msg)
    sys.exit(0) # atexit 注册的函数会在退出时调用

signal.signal(signal.SIGINT, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)


# --- 主逻辑 --- (Revised Initialization and Run)
def main():
    global config, logger, data_dir, pid_file_path, stop_flag_path
    global updater_started_by_this_script
    global mt5_engine_instance, strategy_orchestrator_instance # Make instances global

    # --- 1. 加载配置 --- (Revised)
    try:
        # 使用正确的配置文件名 strategies.yaml
        config = load_app_config("strategies/config/strategies.yaml") 
        if not config:
            print("错误：配置加载失败。")
            # Use logger if available, otherwise print
            if logger: logger.critical("Configuration loading failed.")
            else: print("CRITICAL: Configuration loading failed.")
            return
        # 设置基础数据目录
        data_dir = Path(OmegaConf.select(config, "paths.data_dir", default=str(DATA_DIR_DEFAULT)))
        pid_file_path = data_dir / PID_FILENAME
        stop_flag_path = data_dir / STOP_FLAG_FILENAME

        # --- 2. 设置日志 ---
        # 使用合并后配置中的日志设置，可以指定一个主日志文件
        main_log_filename = OmegaConf.select(config, "logging.main_log_filename", default="strategy_live.log")
        logger = setup_logging(config.logging, main_log_filename, logger_name='LiveStrategyRunner')
        logger.info("实盘策略启动脚本开始执行...")
        logger.info(f"数据目录: {data_dir}")
        logger.info(f"PID 文件路径: {pid_file_path}")
        logger.info(f"停止标志文件路径: {stop_flag_path}")

    except FileNotFoundError as e: # More specific error handling
        print(f"错误：配置文件未找到: {e}")
        if logger: logger.critical(f"Configuration file not found: {e}", exc_info=True)
        else: logging.exception(f"Configuration file not found: {e}")
        return
    except Exception as e:
        print(f"初始化配置或日志时出错: {e}")
        logging.exception("初始化错误") # 记录详细堆栈
        return

    # --- 3. 检查交易日 ---
    today = dt.date.today()
    if today.weekday() >= 5: # 周六或周日
        logger.warning(f"今天是 {today.strftime('%A')}，非交易日，策略不启动。")
        return
    logger.info(f"今天是 {today.strftime('%A')}，交易日，继续启动...")
    # (TODO: 添加更复杂的节假日检查逻辑)

    # --- 4. 检查 MT5 进程 (不再需要，由 initialize_mt5 处理) ---
    # 此部分可以移除或注释掉，因为 MT5 Engine 的 connect 会处理
    # logger.info("跳过独立的 MT5 进程检查，将由 MT5 Engine 初始化处理。")

    # --- 5. 检查 RealtimeUpdater 状态并按需启动 ---
    updater_running = False
    if pid_file_path.exists():
        logger.debug(f"发现 PID 文件: {pid_file_path}")
        try:
            pid = int(pid_file_path.read_text().strip())
            if psutil.pid_exists(pid):
                # 可以添加更严格的进程名或命令行检查
                proc = psutil.Process(pid)
                # 简单的检查是否是 python 进程
                if "python" in proc.name().lower():
                     logger.info(f"检测到 RealtimeUpdater 正在运行 (PID: {pid})。")
                     updater_running = True
                else:
                     logger.warning(f"PID {pid} 对应的进程 ({proc.name()}) 不是 Python 进程，视为无效 PID。")
                     pid_file_path.unlink()
            else:
                logger.warning(f"发现无效的 PID 文件，进程 {pid} 不存在，已删除文件。")
                pid_file_path.unlink()
        except (ValueError, psutil.Error, OSError) as e:
            logger.error(f"检查 PID 文件时出错: {e}，已删除文件。")
            try: pid_file_path.unlink()
            except OSError: pass
        except Exception as e:
            logger.error(f"检查 PID 文件时发生未知错误: {e}")

    if not updater_running:
        logger.info("RealtimeUpdater 未运行，正在尝试启动...")
        try:
            # 确保停止标志不存在
            if stop_flag_path.exists():
                logger.warning(f"发现残留的停止标志文件 {stop_flag_path}，正在删除...")
                stop_flag_path.unlink()

            # 启动后台进程
            updater_cmd = [sys.executable, "-m", UPDATER_SCRIPT_MODULE] + UPDATER_SCRIPT_ARGS
            logger.info(f"执行启动命令: {' '.join(updater_cmd)} in {PROJECT_ROOT}")
            process = subprocess.Popen(
                updater_cmd,
                cwd=PROJECT_ROOT,
                # stdout=subprocess.PIPE, # 可选：捕获输出
                # stderr=subprocess.PIPE, # 可选：捕获错误
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            logger.info(f"已在后台启动 RealtimeUpdater (PID: {process.pid})。")
            updater_started_by_this_script = True # 标记是由此脚本启动

            # 等待 PID 文件生成 (给 RealtimeUpdater 一点时间)
            logger.info("等待 RealtimeUpdater 初始化并写入 PID 文件...")
            pid_wait_start = time.time()
            while not pid_file_path.exists() and time.time() - pid_wait_start < 20: # 增加等待时间
                 time.sleep(0.5)
                 # (可选) 检查进程是否意外退出
                 # poll_status = process.poll()
                 # if poll_status is not None:
                 #     logger.error(f"RealtimeUpdater 进程在等待 PID 文件期间意外退出，返回码: {poll_status}")
                 #     # 读取 stderr?
                 #     return # 启动失败

            if pid_file_path.exists():
                 logger.info("RealtimeUpdater 的 PID 文件已生成。")
            else:
                 logger.warning("警告：等待超时，RealtimeUpdater 可能启动失败或未写入 PID 文件。请检查其日志。")
                 # 即使 PID 文件没生成，也可能在运行，暂时不退出，但需要注意

        except FileNotFoundError:
             logger.error(f"错误：无法找到 Python 解释器 '{sys.executable}' 或模块 '{UPDATER_SCRIPT_MODULE}'。")
             return
        except Exception as e:
            logger.error(f"启动 RealtimeUpdater 时发生错误: {e}", exc_info=True)
            return # 启动失败则不继续

    # --- 6. 初始化策略组件 ---
    logger.info("初始化策略组件...")
    try:
        # 使用加载的 config 初始化 DataProvider
        data_provider = DataProvider(config)
        logger.info("DataProvider 初始化完成。")

        # 初始化 MT5ExecutionEngine
        # 它需要 config 对象或至少 config.execution_engine 部分
        # 确保配置中包含 execution_engine (即使是空的，因为 MT5Engine 会尝试访问)
        if 'execution_engine' not in config:
             logger.warning("配置中缺少 'execution_engine' 部分，MT5Engine 可能使用默认值或出错。")
             # config.execution_engine = OmegaConf.create({}) # 可以添加一个空的

        mt5_engine_instance = MT5ExecutionEngine(config) # 传递整个合并后的配置
        logger.info("MT5ExecutionEngine 初始化完成。")

        # !!! 关键：连接 MT5 !!!
        logger.info("正在连接 MT5 Execution Engine...")
        mt5_engine_instance.connect() # 调用 connect 方法
        logger.info("MT5 Execution Engine 连接成功。")

        # 初始化 StrategyOrchestrator
        # 它需要 config, data_provider, execution_engine
        strategy_orchestrator_instance = StrategyOrchestrator(
            config=config, # 传递整个配置
            data_provider=data_provider,
            execution_engine=mt5_engine_instance
        )
        logger.info("StrategyOrchestrator 初始化完成。")

    except ConnectionError as conn_e:
        logger.error(f"连接 MT5 时失败: {conn_e}")
        # 连接失败，可能需要停止已启动的 RealtimeUpdater
        cleanup_updater_and_engine() # 调用清理
        return
    except Exception as e:
        logger.error(f"初始化策略组件时出错: {e}", exc_info=True)
        cleanup_updater_and_engine() # 调用清理
        return # 初始化失败则不继续

    # --- 7. 运行策略 ---
    logger.info("开始运行策略...")
    try:
        # 从配置中获取运行间隔 (如果需要)
        run_interval = OmegaConf.select(config, "strategies.orchestrator.run_interval_seconds", default=60)
        logger.info(f"将使用 {run_interval} 秒的间隔运行策略循环。")
        strategy_orchestrator_instance.start(interval_seconds=run_interval)
        # start() 是阻塞的，代码会在这里停留直到 stop() 被调用或异常/信号发生

    except KeyboardInterrupt:
         logger.info("策略运行收到停止信号 (KeyboardInterrupt)。")
    except Exception as strategy_e:
         logger.error(f"策略运行时发生错误: {strategy_e}", exc_info=True)
    finally:
         logger.info("策略运行结束。脚本将退出。")
         # 清理函数将由 atexit 自动调用

if __name__ == "__main__":
    main() 