import logging
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd
from omegaconf import DictConfig, OmegaConf
from datetime import datetime, timedelta
import os # Import os for getpid()
import datetime as dt # Import datetime for trading day check
import subprocess
import sys

# 尝试从 core 模块导入共享工具
try:
    from core.utils import (
        load_app_config,
        setup_logging,
        initialize_mt5,
        shutdown_mt5,
        parse_timeframes,
        get_filepath, # 假设 get_filepath 用于构建路径
        MT5_AVAILABLE,
        get_utc_timezone
    )
    if MT5_AVAILABLE:
        from core.utils import mt5 # Import the mt5 object if available
    else:
        mt5 = None
except ImportError:
    # 在无法导入 core.utils 的情况下提供备用日志记录
    logging.basicConfig(level=logging.ERROR)
    logging.error("无法导入 core.utils。请确保 core 模块在 Python 路径中且包含所需函数。", exc_info=True)
    # 设置一个标志或引发更严重的错误，因为模块功能会受限
    MT5_AVAILABLE = False
    mt5 = None
    # 提供一些函数的存根或默认实现，以允许类至少能被定义
    def load_app_config(*args, **kwargs): return None
    def setup_logging(*args, **kwargs): return logging.getLogger('RealtimeUpdater_Fallback')
    def initialize_mt5(*args, **kwargs): return False
    def shutdown_mt5(*args, **kwargs): pass
    def parse_timeframes(*args, **kwargs): return {}
    def get_filepath(*args, **kwargs): return Path()
    def get_utc_timezone(): import pytz; return pytz.utc

# Define PID file and stop flag file relative to base_data_dir
PID_FILENAME = "realtime_updater.pid"
STOP_FLAG_FILENAME = "STOP_REALTIME.flag"

class RealtimeUpdater:
    """
    负责持续监控和更新来自 MetaTrader 5 的实时 K 线数据。
    为每个 品种-时间周期 组合启动一个单独的监控线程。
    """
    def __init__(self, config_rel_path: str = "market_price_data/config/updater.yaml"):
        """
        初始化 RealtimeUpdater。

        Args:
            config_rel_path (str): 模块特定配置文件的相对路径。
        """
        self.logger = logging.getLogger('RealtimeUpdater_Init') # 临时 logger
        self.config: Optional[DictConfig] = None
        self.mt5_library_available: bool = MT5_AVAILABLE
        self.updater_enabled: bool = False
        self.symbols: List[str] = []
        self.timeframes_str: List[str] = []
        self.timeframes_mt5: Dict[str, Any] = {}
        self.data_dir_pattern: str = ""
        self.filename_pattern: str = ""
        self.base_data_dir: Path = Path()
        self.poll_intervals: Dict[str, int] = {}
        self.default_poll_interval_seconds: int = 60
        self.fetch_bars_count: int = 100

        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self.mt5_initialized: bool = False # Track MT5 connection state
        self.pid_file_path: Optional[Path] = None
        self.stop_flag_path: Optional[Path] = None

        try:
            # 1. 加载配置
            self.config = load_app_config(config_rel_path)
            if not self.config:
                self.logger.error("配置加载失败，RealtimeUpdater 初始化中止。")
                return

            # 2. 设置日志
            log_filename = OmegaConf.select(self.config, "logging.realtime_log_filename", default="market_data_realtime.log")
            self.logger = setup_logging(self.config.logging, log_filename, logger_name='RealtimeUpdater')
            self.logger.info("RealtimeUpdater 初始化开始...")
            self.logger.info(f"MT5 库可用状态: {self.mt5_library_available}")

            # 3. 检查更新器是否启用
            self.updater_enabled = OmegaConf.select(self.config, "realtime.enabled", default=False)
            self.logger.info(f"实时数据更新器启用状态: {self.updater_enabled}")

            if not self.updater_enabled:
                self.logger.warning("实时数据更新器未在配置中启用。")
                return

            # 4. 加载具体配置
            self.symbols = OmegaConf.select(self.config, "realtime.symbols", default=[])
            self.timeframes_str = OmegaConf.select(self.config, "realtime.timeframes", default=[])
            self.data_dir_pattern = OmegaConf.select(self.config, "realtime.data_directory_pattern", default="realtime/{symbol}")
            self.filename_pattern = OmegaConf.select(self.config, "realtime.filename_pattern", default="{symbol}_{timeframe_lower}_realtime.csv")
            self.base_data_dir = Path(OmegaConf.select(self.config, "paths.data_dir", default="data"))
            self.poll_intervals = OmegaConf.to_container(
                OmegaConf.select(self.config, "realtime.poll_intervals", default={}),
                resolve=True
            )
            self.default_poll_interval_seconds = OmegaConf.select(self.config, "realtime.default_poll_interval_seconds", default=60)
            self.fetch_bars_count = OmegaConf.select(self.config, "realtime.fetch_bars_count", default=100)

            if not self.symbols or not self.timeframes_str:
                self.logger.warning("配置中未指定有效的 realtime symbols 或 timeframes。")
                self.updater_enabled = False
                return

            # 5. 解析时间周期 (如果 MT5 可用)
            if self.mt5_library_available:
                self.timeframes_mt5 = parse_timeframes(self.timeframes_str, self.logger)
                if not self.timeframes_mt5:
                    self.logger.error("无法将配置中的时间周期解析为有效的 MT5 常量。")
                    self.updater_enabled = False
            else:
                 self.logger.warning("MT5 库不可用，无法解析时间周期或连接 MT5。")
                 self.updater_enabled = False

            self.logger.info(f"实时配置加载完成。目标品种: {len(self.symbols)}, 目标周期: {self.timeframes_str}")
            self.logger.info(f"周期轮询间隔配置: {self.poll_intervals}")
            self.logger.info(f"默认轮询间隔: {self.default_poll_interval_seconds}s")

            # Define full paths for PID and stop flag files
            self.pid_file_path = self.base_data_dir / PID_FILENAME
            self.stop_flag_path = self.base_data_dir / STOP_FLAG_FILENAME

        except Exception as e:
            self.logger.error(f"RealtimeUpdater 初始化过程中发生错误: {e}", exc_info=True)
            self.config = None
            self.updater_enabled = False

    def _is_trading_day(self) -> bool:
        """检查当前日期是否为交易日（简单示例：周一至周五）。"""
        today = dt.date.today()
        # 周一到周五 (weekday() 返回 0-6)
        if today.weekday() >= 5: # 周六或周日
            self.logger.info(f"今天是 {today.strftime('%A')}，非交易日。")
            return False
        # 在此可以添加更复杂的节假日检查逻辑
        self.logger.debug(f"今天是 {today.strftime('%A')}，交易日。")
        return True

    def _write_pid_file(self):
        """写入当前进程 ID 到 PID 文件。"""
        if not self.pid_file_path:
            self.logger.error("PID 文件路径未设置，无法写入 PID 文件。")
            return
        try:
            pid = os.getpid()
            self.pid_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            with open(self.pid_file_path, 'w') as f:
                f.write(str(pid))
            self.logger.info(f"已将 PID {pid} 写入文件: {self.pid_file_path}")
        except Exception as e:
            self.logger.error(f"写入 PID 文件 {self.pid_file_path} 时出错: {e}", exc_info=True)

    def _delete_pid_file(self):
        """删除 PID 文件。"""
        if not self.pid_file_path:
            self.logger.warning("PID 文件路径未设置，无法删除 PID 文件。")
            return
        try:
            if self.pid_file_path.exists():
                self.pid_file_path.unlink()
                self.logger.info(f"已删除 PID 文件: {self.pid_file_path}")
            else:
                 self.logger.debug("PID 文件不存在，无需删除。")
        except Exception as e:
            self.logger.error(f"删除 PID 文件 {self.pid_file_path} 时出错: {e}", exc_info=True)

    def start_updater(self):
        """
        检查交易日，初始化 MT5，写入 PID 文件并启动监控线程。
        """
        # 0. 交易日检查
        if not self._is_trading_day():
            self.logger.warning("非交易日，实时更新器不启动。")
            return

        # 1. 检查是否已启用或已运行
        if not self.updater_enabled:
            self.logger.warning("实时数据更新器未启用或初始化失败，无法启动。")
            return

        if not self.mt5_library_available:
            self.logger.error("MT5 库不可用，无法启动实时更新。")
            return

        if self.mt5_initialized: # Prevent starting multiple times
            self.logger.warning("实时更新器似乎已在运行 (MT5已初始化)。")
            return

        if not self.config or not self.config.execution or not self.config.execution.mt5:
             self.logger.error("MT5 执行配置 (execution.mt5) 未在合并后的配置中找到。")
             return

        self.logger.info("启动实时数据更新器...")
        self._stop_event.clear() # Reset stop event

        # 2. 初始化 MT5 连接
        self.mt5_initialized = initialize_mt5(self.logger, self.config.execution.mt5)
        if not self.mt5_initialized:
            self.logger.error("无法初始化 MT5 连接，实时更新器启动失败。")
            return

        # 3. 写入 PID 文件
        self._write_pid_file()

        # 4. 启动监控线程
        self.logger.info("MT5 连接成功，开始启动监控线程...")
        self._threads = [] # Clear previous threads if any

        for symbol_raw in self.symbols:
            symbol_upper = symbol_raw.upper()
            for tf_str, tf_mt5 in self.timeframes_mt5.items():
                thread = threading.Thread(
                    target=self._monitor_symbol_timeframe,
                    args=(symbol_upper, tf_str, tf_mt5),
                    daemon=True # 设置为守护线程，主程序退出时它们也会退出
                )
                thread.start()
                self._threads.append(thread)
                self.logger.info(f"已启动监控线程: {symbol_upper} - {tf_str}")

        self.logger.info(f"所有 {len(self._threads)} 个监控线程已启动。")

    def stop_updater(self):
        """
        停止所有监控线程，关闭 MT5 连接，并删除 PID 文件。
        """
        if not self.updater_enabled:
            return # Nothing to stop if not enabled

        if not self.mt5_initialized and not self._threads:
             self.logger.info("实时更新器未运行，无需停止。")
             return

        self.logger.info("正在停止实时数据更新器...")
        self._stop_event.set() # Signal threads to stop

        # 等待所有线程结束
        self.logger.info(f"等待 {len(self._threads)} 个监控线程退出...")
        active_threads = []
        for thread in self._threads:
            if thread.is_alive():
                 thread.join(timeout=10) # 设置超时以防线程卡死
                 if thread.is_alive():
                     self.logger.warning(f"线程 {thread.name} 未能在超时时间内退出。")
                 else:
                     active_threads.append(thread.name) # Track successfully joined threads
            # else: thread already finished
        
        self.logger.info(f"成功停止的线程: {len(active_threads)} / {len(self._threads)}")
        self._threads = [] # Clear thread list

        # 关闭 MT5 连接
        if self.mt5_initialized:
            shutdown_mt5(self.logger)
            self.mt5_initialized = False

        # 删除 PID 文件
        self._delete_pid_file()

        self.logger.info("实时数据更新器已停止。")

    def _monitor_symbol_timeframe(self, symbol: str, timeframe_str: str, timeframe_mt5: Any):
        """
        监控单个 symbol-timeframe 组合的后台任务。
        """
        thread_name = f"{symbol}-{timeframe_str}"
        self.logger.info(f"线程 [{thread_name}] 开始监控...")
        
        # 获取此时间周期的轮询间隔
        poll_interval = self.poll_intervals.get(timeframe_str.upper(), self.default_poll_interval_seconds)
        self.logger.info(f"线程 [{thread_name}] 使用轮询间隔: {poll_interval} 秒")
        
        timeframe_lower = timeframe_str.lower()

        try:
            # 1. 组合目录和文件模式
            #    确保使用 posix 风格的路径分隔符 '/' 进行组合，即使在 Windows 上，
            #    因为 get_filepath 内部会处理 Path 对象。
            #    使用 os.path.join 可能在 Windows 上产生反斜杠，这里需要明确。
            #    更健壮的方式是让 get_filepath 接受目录模式和文件模式分开传递，但现在先按现有函数签名修改调用处。
            full_relative_pattern = f"{self.data_dir_pattern}/{self.filename_pattern}"

            # 2. 调用 get_filepath，使用正确的参数名和组合后的模式
            filepath = get_filepath(
                base_data_dir=str(self.base_data_dir), # 使用正确的参数名 base_data_dir
                relative_path_pattern=full_relative_pattern, # 传递组合后的完整模式
                symbol=symbol,
                timeframe=timeframe_lower # 传递小写时间周期给 format
            )
            # --- 结束修正 ---

            self.logger.info(f"线程 [{thread_name}] 将数据写入: {filepath}")
            
            # Ensure parent directory exists (get_filepath should handle this, but double check)
            filepath.parent.mkdir(parents=True, exist_ok=True) 

        except Exception as path_e:
             self.logger.error(f"线程 [{thread_name}] 获取文件路径时出错: {path_e}", exc_info=True)
             return # Exit thread if path cannot be determined

        # --- Monitoring Loop ---
        last_log_time = time.monotonic()
        log_interval = 300 # Log activity every 5 minutes

        while not self._stop_event.is_set():
            try:
                start_fetch_time = time.monotonic()
                
                # Periodically log thread activity
                current_time = time.monotonic()
                if current_time - last_log_time >= log_interval:
                     self.logger.debug(f"线程 [{thread_name}] 仍在运行...")
                     last_log_time = current_time

                # Check MT5 connection (optional, adds overhead)
                # if not self.mt5_initialized or not mt5.terminal_info().connected:
                #     self.logger.warning(f"线程 [{thread_name}] 检测到 MT5 连接丢失。尝试重新连接...")
                #     # Attempt reconnection logic here? Or rely on main thread?
                #     # For now, just skip this fetch cycle
                #     self._stop_event.wait(poll_interval) # Wait before next check
                #     continue

                # 获取最新 K 线
                now_utc = datetime.now(get_utc_timezone())
                # MT5 copy_rates_from_pos 获取从指定位置开始的 K 线
                # 我们想要最新的 self.fetch_bars_count 条
                rates = mt5.copy_rates_from_pos(symbol, timeframe_mt5, 0, self.fetch_bars_count)

                if rates is None:
                    error_code = mt5.last_error()
                    self.logger.error(f"线程 [{thread_name}] 调用 copy_rates_from_pos 失败。错误: {error_code}")
                elif len(rates) == 0:
                    self.logger.debug(f"线程 [{thread_name}] 未获取到新的实时 K 线。")
                else:
                    # 成功获取数据
                    self.logger.debug(f"线程 [{thread_name}] 成功获取 {len(rates)} 条实时 K 线。")
                    
                    # --- 处理和写入数据 ---
                    try:
                        # 直接将 MT5 返回的 rates (通常是 numpy 结构化数组或元组列表) 转换为 DataFrame
                        # 与 history.py 保持一致，先转为元组列表
                        processed_rates = []
                        import numpy as np
                        if isinstance(rates, np.ndarray):
                            processed_rates = [tuple(row) for row in rates]
                        else:
                            try:
                                processed_rates = [tuple(item) for item in rates]
                            except TypeError:
                                 self.logger.error(f"线程 [{thread_name}] 无法将 MT5 返回的数据转换为元组列表。", exc_info=True)
                                 processed_rates = [] # Skip writing

                        if processed_rates:
                            expected_columns = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
                            new_data_df = pd.DataFrame(processed_rates, columns=expected_columns)
                            
                            # 将时间戳转换为 'YYYY-MM-DD HH:MM:SS' 字符串格式写入
                            new_data_df['time'] = pd.to_datetime(new_data_df['time'], unit='s', utc=True).dt.strftime('%Y-%m-%d %H:%M:%S')

                            # 写入 CSV (覆盖模式，因为这是实时文件的最新快照)
                            temp_filepath = filepath.with_suffix(f'{filepath.suffix}.tmp_{thread_name}')
                            new_data_df.to_csv(temp_filepath, index=False, header=True, encoding='utf-8', float_format='%.5f')
                            os.replace(temp_filepath, filepath)
                            self.logger.info(f"线程 [{thread_name}] 已更新实时数据文件: {filepath.name} ({len(new_data_df)} 条)")
                    
                    except Exception as write_e:
                         self.logger.error(f"线程 [{thread_name}] 处理或写入实时数据时出错: {write_e}", exc_info=True)
                         # Clean up temp file if error occurred during replace
                         if 'temp_filepath' in locals() and temp_filepath.exists():
                             try:
                                  temp_filepath.unlink()
                             except OSError: pass # Ignore unlink error

                fetch_duration = time.monotonic() - start_fetch_time
                # Wait for the remaining interval time
                wait_time = max(0, poll_interval - fetch_duration)
                self._stop_event.wait(wait_time) # Wait for stop signal or timeout

            except Exception as loop_e:
                self.logger.error(f"线程 [{thread_name}] 监控循环中发生意外错误: {loop_e}", exc_info=True)
                # Avoid busy-looping on error, wait before retrying
                self._stop_event.wait(poll_interval) # Wait for the standard interval

        self.logger.info(f"线程 [{thread_name}] 收到停止信号，正在退出...")


if __name__ == '__main__':
    # 简单的测试代码
    print("正在直接运行 realtime.py 进行测试...")
    updater = RealtimeUpdater()
    if updater.config and updater.updater_enabled:
        updater.start_updater()
        print("实时更新器已启动。按 Ctrl+C 停止测试...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n收到 Ctrl+C，正在停止...")
            updater.stop_updater()
            print("测试停止。")
    else:
        print("RealtimeUpdater 未启用或配置加载失败。")

    # 添加主执行块
    print("直接运行 realtime.py 用于启动或停止...")
    # Setup basic logging for the main block itself if setup_logging hasn't run yet
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger('RealtimeMain')

    # Create updater instance (will load config and setup proper logging)
    updater = RealtimeUpdater()

    if not updater.updater_enabled:
         main_logger.warning("实时更新器未在配置中启用或初始化失败，退出。")
         sys.exit(1)
         
    # --- Check for STOP flag ---
    # stop_flag_path is set during __init__
    if updater.stop_flag_path and updater.stop_flag_path.exists():
         main_logger.info(f"找到停止标志文件: {updater.stop_flag_path}")
         main_logger.info("正在尝试停止现有进程 (如果通过 PID 文件可以找到)...")
         # Note: This script itself doesn't stop other processes directly.
         # It relies on the running process checking the flag.
         # We can try to signal it by simply deleting the flag now (or let the running process do it)
         try:
              updater.stop_flag_path.unlink()
              main_logger.info("已删除停止标志文件。运行中的进程应在下次检查时停止。")
         except OSError as e:
              main_logger.error(f"删除停止标志文件时出错: {e}")
         # Optionally, try reading PID and sending a signal (more complex and platform-dependent)
         sys.exit(0) # Exit after handling stop flag
         
    # --- Check if already running via PID ---
    pid_file_exists = False
    existing_pid = None
    if updater.pid_file_path and updater.pid_file_path.exists():
        pid_file_exists = True
        try:
             with open(updater.pid_file_path, 'r') as f:
                  existing_pid = int(f.read().strip())
             # Check if the process with that PID actually exists
             # This is platform dependent
             is_process_running = False
             if os.name == 'posix':
                  try:
                      os.kill(existing_pid, 0) # Check if process exists
                      is_process_running = True
                  except OSError:
                      is_process_running = False # Process does not exist
             elif os.name == 'nt': # Windows
                  # Use tasklist command (less reliable than psutil but built-in)
                 cmd = f'tasklist /FI "PID eq {existing_pid}" /NH'
                 try:
                      output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                      if str(existing_pid) in output:
                           is_process_running = True
                 except subprocess.CalledProcessError:
                      is_process_running = False # Command failed or process not found
                 except Exception as win_e:
                      main_logger.warning(f"检查 Windows 进程时出错: {win_e}")
                      # Assume not running if check fails
                      is_process_running = False 

             if is_process_running:
                   main_logger.warning(f"PID 文件 {updater.pid_file_path} 存在，并且进程 {existing_pid} 似乎仍在运行。")
                   main_logger.warning("如果需要重新启动，请先停止现有进程 (例如创建 STOP_REALTIME.flag 文件或手动结束进程)，然后删除 PID 文件。")
                   sys.exit(1) # Exit, do not start a new instance
             else:
                  main_logger.warning(f"PID 文件 {updater.pid_file_path} 存在，但进程 {existing_pid} 未找到。可能是上次未正常关闭。正在删除旧的 PID 文件...")
                  try:
                      updater.pid_file_path.unlink()
                  except OSError as e:
                      main_logger.error(f"删除旧 PID 文件时出错: {e}")
                      sys.exit(1) # Exit if cannot clean up PID file

        except (ValueError, OSError) as e:
             main_logger.warning(f"读取或处理现有 PID 文件 {updater.pid_file_path} 时出错: {e}。将尝试继续。")
             # Attempt to delete potentially corrupt PID file
             if pid_file_exists:
                  try:
                      updater.pid_file_path.unlink()
                  except OSError: pass # Ignore error if deletion fails here

    # --- Start the updater ---
    try:
        updater.start_updater()
        # Keep the main thread alive while background threads run
        # Check for stop event periodically in the main thread too
        if updater.mt5_initialized and updater._threads: # Check if threads actually started
             main_logger.info("主进程进入等待状态。监控线程正在后台运行...")
             main_logger.info(f"要停止，请在 {updater.base_data_dir} 目录下创建 {STOP_FLAG_FILENAME} 文件。")
             while not updater._stop_event.is_set():
                  # Check for the stop flag file periodically in the main thread as well
                  if updater.stop_flag_path and updater.stop_flag_path.exists():
                       main_logger.info("主线程检测到停止标志文件，开始停止...")
                       updater.stop_updater()
                       try: # Attempt to delete the flag file after stopping
                            updater.stop_flag_path.unlink()
                            main_logger.info("已删除停止标志文件。")
                       except OSError as e:
                            main_logger.error(f"停止后删除标志文件失败: {e}")
                       break # Exit the loop
                        
                  time.sleep(5) # Check every 5 seconds
             main_logger.info("主进程退出。")
        else:
             main_logger.warning("未能成功启动监控线程或 MT5 连接失败。请检查日志。")

    except KeyboardInterrupt:
         main_logger.info("收到 KeyboardInterrupt (Ctrl+C)。正在停止更新器...")
         updater.stop_updater()
         main_logger.info("更新器已停止。")
    except Exception as main_e:
         main_logger.error(f"主执行块中发生意外错误: {main_e}", exc_info=True)
         # Attempt graceful shutdown on unexpected error
         updater.stop_updater()
    finally:
         # Ensure PID file is deleted on exit, unless stop was triggered by flag (where stop_updater handles it)
         if updater.pid_file_path and updater.pid_file_path.exists() and not (updater.stop_flag_path and not updater.stop_flag_path.exists()): # Don't delete if stop_updater already did
              updater._delete_pid_file() 