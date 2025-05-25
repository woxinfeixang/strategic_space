"""
Handles the download, update, and storage of historical K-line data 
from MetaTrader 5, implementing robust error handling, chunked fetching, 
and atomic file updates.
"""

import os
import logging
import sys
from datetime import datetime, timedelta, timezone
import time
import pandas as pd
import pytz # For robust timezone handling
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Import necessary utilities from core and OmegaConf
from omegaconf import DictConfig, OmegaConf
# Assuming utils.py is in core/ relative to project root
# Ensure PROJECT_ROOT is defined or core is in sys.path correctly
try:
    from core.utils import (
        load_app_config,
        setup_logging,
        parse_timeframes,
        initialize_mt5,
        shutdown_mt5,
        get_filepath,
        get_utc_timezone,
        MT5_AVAILABLE
    )
    if MT5_AVAILABLE:
        from core.utils import mt5 # Import the mt5 object if available
    else:
        mt5 = None
except ImportError as e:
    # Provide a more informative error if core.utils cannot be found
    sys.stderr.write(f"ERROR: Failed to import core utilities: {e}\n")
    sys.stderr.write("Ensure the 'core' directory is in the Python path or installed correctly.\n")
    # Define placeholders if import fails to allow basic script parsing
    MT5_AVAILABLE = False
    mt5 = None
    def setup_logging(*args, **kwargs): return logging.getLogger('FallbackLogger')
    def parse_timeframes(*args, **kwargs): return {}
    def initialize_mt5(*args, **kwargs): return False
    def shutdown_mt5(*args, **kwargs): pass
    def get_filepath(*args, **kwargs): return Path()
    def get_utc_timezone(*args, **kwargs): return timezone.utc

class HistoryUpdater:
    """
    Manages the process of fetching and updating historical market data from MT5.
    Handles configuration, MT5 connection, data fetching (chunked), 
    file storage (CSV), and basic integrity checks.
    """
    def __init__(self, config_rel_path: str = "market_price_data/config/updater.yaml"):
        """
        Initializes the HistoryUpdater with a pre-loaded configuration object.

        Args:
            config_rel_path (str): The relative path to the configuration file.
        """
        self.logger = logging.getLogger('HistoryUpdater_Init') # 临时 logger
        self.config: Optional[DictConfig] = None
        self.mt5_library_available = MT5_AVAILABLE
        self.updater_enabled = False
        self.symbols: List[str] = []
        self.timeframes_str: List[str] = []
        self.timeframes_mt5: Dict[str, Any] = {}
        self.data_dir_pattern: str = ""
        self.filename_pattern: str = ""
        self.base_data_dir: Path = Path()
        self.timezone: pytz.BaseTzInfo = get_utc_timezone() # Use pytz for robust timezone handling

        try:
            # 1. 加载配置
            self.config = load_app_config(config_rel_path)
            if not self.config:
                self.logger.error("配置加载失败，HistoryUpdater 初始化中止。")
                return

            # 2. 设置日志
            log_filename = OmegaConf.select(self.config, "logging.history_log_filename", default="market_data_history.log")
            self.logger = setup_logging(self.config.logging, log_filename, logger_name='HistoryUpdater')
            self.logger.info("HistoryUpdater 初始化开始...")
            self.logger.info(f"MT5 库可用状态: {self.mt5_library_available}")

            # 3. 检查更新器是否启用
            self.updater_enabled = OmegaConf.select(self.config, "historical.enabled", default=False)
            self.logger.info(f"历史数据更新器启用状态: {self.updater_enabled}")

            if not self.updater_enabled:
                self.logger.warning("历史数据更新器未在配置中启用，将不会执行更新。")
                return

            # 4. 加载具体配置
            self.symbols = OmegaConf.select(self.config, "historical.symbols", default=[])
            self.timeframes_str = OmegaConf.select(self.config, "historical.timeframes", default=[])
            self.data_dir_pattern = OmegaConf.select(self.config, "historical.data_directory_pattern", default="historical/{symbol}")
            self.filename_pattern = OmegaConf.select(self.config, "historical.filename_pattern", default="{symbol}_{timeframe_lower}.csv")
            self.base_data_dir = Path(OmegaConf.select(self.config, "paths.data_dir", default="data"))
            # 注意: get_filepath 可能需要项目根目录，utils.py 需要相应调整或 HistoryUpdater 知道根目录

            if not self.symbols or not self.timeframes_str:
                self.logger.warning("配置中未指定有效的 symbols 或 timeframes。")
                self.updater_enabled = False # 禁用，因为没有目标
                return

            # 5. 解析时间周期 (如果 MT5 可用)
            if self.mt5_library_available:
                self.timeframes_mt5 = parse_timeframes(self.timeframes_str, self.logger)
                if not self.timeframes_mt5:
                    self.logger.error("无法将配置中的时间周期解析为有效的 MT5 常量。")
                    self.updater_enabled = False # 无法获取数据
            else:
                 self.logger.warning("MT5 库不可用，无法解析时间周期或连接 MT5。")
                 self.updater_enabled = False

            self.logger.info(f"配置加载完成。目标品种: {len(self.symbols)}, 目标周期: {self.timeframes_str}")

            # --- 加载额外的配置项 ---
            self.batch_size_days: int = 30
            self.delay_between_requests_ms: int = 500
            self.retry_attempts: int = 3
            self.retry_delay_seconds: int = 60
            self.verify_integrity: bool = True

            if self.config:
                try:
                    self.batch_size_days = OmegaConf.select(self.config, "historical.batch_size_days", default=30)
                    self.delay_between_requests_ms = OmegaConf.select(self.config, "historical.delay_between_requests_ms", default=500)
                    self.retry_attempts = OmegaConf.select(self.config, "historical.retry_attempts", default=3)
                    self.retry_delay_seconds = OmegaConf.select(self.config, "historical.retry_delay_seconds", default=60)
                    self.verify_integrity = OmegaConf.select(self.config, "historical.verify_integrity", default=True)
                    self.logger.info(f"分块/重试配置: batch_size={self.batch_size_days}d, delay={self.delay_between_requests_ms}ms, retries={self.retry_attempts}, retry_delay={self.retry_delay_seconds}s")
                except Exception as e:
                    self.logger.warning(f"加载分块/重试配置时出错: {e}. 将使用默认值。")
            # ------------------------

        except Exception as e:
            self.logger.error(f"HistoryUpdater 初始化过程中发生错误: {e}", exc_info=True)
            self.config = None # 标记初始化失败
            self.updater_enabled = False

    def run_update_cycle(self):
        """
        Runs a complete historical data update cycle for all configured symbols and timeframes.
        Handles MT5 initialization and shutdown.
        """
        if not self.updater_enabled:
            self.logger.warning("历史数据更新器未启用或初始化失败，跳过更新周期。")
            return

        if not self.mt5_library_available:
            self.logger.error("MT5 库不可用，无法执行更新。")
            return

        if not self.config or not self.config.execution or not self.config.execution.mt5:
             self.logger.error("MT5 执行配置 (execution.mt5) 未在合并后的配置中找到。")
             return

        self.logger.info("开始历史数据更新周期...")
        mt5_initialized = False
        try:
            # 初始化 MT5 连接
            mt5_initialized = initialize_mt5(self.logger, self.config.execution.mt5)

            if mt5_initialized:
                self.logger.info("MT5 连接成功。")
                # --- 修改：调用 update_symbol_timeframe ---
                total_updated_count = 0
                total_failed_items = []
                for symbol_raw in self.symbols:
                    symbol_upper = symbol_raw.upper()
                    self.logger.info(f"--- 开始处理品种: {symbol_upper} ---")
                    for tf_str, tf_mt5 in self.timeframes_mt5.items():
                         tf_lower = tf_str.lower()
                         self.logger.info(f"-- 开始处理时间周期: {tf_str} --")
                         try:
                             # 调用核心更新函数
                             success = self.update_symbol_timeframe(symbol_upper, tf_str, tf_lower, tf_mt5)
                             if success:
                                 total_updated_count += 1
                                 self.logger.info(f"成功更新 {symbol_upper} {tf_str}")
                             else:
                                 total_failed_items.append(f"{symbol_upper}:{tf_str}")
                                 self.logger.warning(f"更新 {symbol_upper} {tf_str} 失败或无需更新。")
                         except Exception as item_e:
                              self.logger.error(f"处理 {symbol_upper} {tf_str} 时发生意外错误: {item_e}", exc_info=True)
                              total_failed_items.append(f"{symbol_upper}:{tf_str}(Exception)")
                         self.logger.info(f"-- 时间周期处理结束: {tf_str} --")
                    self.logger.info(f"--- 品种处理结束: {symbol_upper} ---")
                
                # 记录总结信息
                self.logger.info("所有品种和时间周期处理完毕。")
                self.logger.info(f"成功更新项数: {total_updated_count}")
                if total_failed_items:
                     self.logger.warning(f"失败或跳过的项 ({len(total_failed_items)}): {', '.join(total_failed_items)}")
                else:
                     self.logger.info("所有处理项均成功完成（或无需更新）。")
                # --------------------------------------------
            else:
                self.logger.error("无法初始化 MT5 连接，更新周期中止。")
        except Exception as e:
            self.logger.error(f"更新周期中发生意外错误: {e}", exc_info=True)
        finally:
            if mt5_initialized:
                shutdown_mt5(self.logger)
            self.logger.info("历史数据更新周期结束。")

    def _get_mt5_config_section(self) -> Optional[DictConfig]:
        """Safely gets the execution.mt5 config section."""
        if not self.config:
            return None
        return OmegaConf.select(self.config, 'execution.mt5')

    # --- Placeholder methods for core logic ---

    def update_symbol_timeframe(self, symbol: str, timeframe_name: str, timeframe_lower: str, timeframe_mt5: Any) -> bool:
        """
        Handles the complete update process for a single symbol and timeframe.
        Determines start time, fetches data in chunks, updates file, verifies.

        Args:
            symbol (str): Symbol name (UPPERCASE).
            timeframe_name (str): Timeframe name (e.g., 'M1', 'H1', UPPERCASE).
            timeframe_lower (str): Timeframe name lowercase (e.g., 'm1', 'h1').
            timeframe_mt5 (Any): MT5 timeframe constant.

        Returns:
            bool: True if update was successful, False otherwise.
        """
        self.logger.debug(f"Starting update for {symbol} {timeframe_name}")
        
        # 1. Get File Path (ensuring correct case)
        try:
             filepath = self._get_data_filepath(symbol, timeframe_lower)
             self.logger.info(f"Target data file: {filepath}")
        except Exception as path_e:
             self.logger.error(f"Failed to get filepath for {symbol} {timeframe_name}: {path_e}", exc_info=True)
             return False

        # 2. Determine Start Time for Fetching
        start_dt_utc = self._get_fetch_start_time(filepath, timeframe_name)
        if start_dt_utc is None:
             self.logger.error(f"Could not determine fetch start time for {symbol} {timeframe_name}. Skipping.")
             return False
        
        now_utc = datetime.now(self.timezone)
        # Don't fetch if the start time is very recent (e.g., within the last minute of the current time)
        # This avoids unnecessary fetches if the data is already up-to-date.
        if start_dt_utc >= now_utc - timedelta(minutes=1): 
             self.logger.info(f"Data for {symbol} {timeframe_name} appears up-to-date (calculated start time {start_dt_utc} is very recent). Skipping fetch.")
             # Optionally run verification even if no fetch needed
             if self.verify_integrity and filepath.exists():
                  try:
                      self._verify_data_integrity(filepath)
                  except Exception as verify_e:
                       self.logger.warning(f"Integrity verification failed for up-to-date file {filepath.name}: {verify_e}", exc_info=True)
             return True # Consider it success if up-to-date

        self.logger.info(f"Fetching data for {symbol} {timeframe_name} from {start_dt_utc} up to {now_utc}")
        
        # 3. Fetch Data in Chunks
        try:
            # --- Call the chunked fetch method ---
            all_new_data = self._fetch_historical_data_chunked(symbol, timeframe_mt5, start_dt_utc, now_utc)
            # ------------------------------------
        except Exception as fetch_e:
             self.logger.error(f"Critical error during chunked fetch for {symbol} {timeframe_name}: {fetch_e}", exc_info=True)
             return False # Fetching failed critically

        # 4. Process Fetch Results
        if all_new_data is None:
            self.logger.warning(f"Fetching data failed for {symbol} {timeframe_name} after retries (returned None). Skipping file update.")
            return False # Fetching failed
        if all_new_data.empty:
            self.logger.info(f"No new data returned from MT5 for {symbol} {timeframe_name} in range {start_dt_utc} to {now_utc}. File update not needed.")
            # Optionally run verification on existing file
            if self.verify_integrity and filepath.exists():
                  try:
                       self._verify_data_integrity(filepath)
                  except Exception as verify_e:
                       self.logger.warning(f"Integrity verification failed for existing file {filepath.name} (no new data): {verify_e}", exc_info=True)
            return True # Success, just no new data

        self.logger.info(f"Fetched a total of {len(all_new_data)} new bars for {symbol} {timeframe_name}.")

        # 5. Update Local File Atomically
        try:
            self._update_historical_file(filepath, all_new_data)
        except Exception as update_e:
            self.logger.error(f"Failed to update file {filepath}: {update_e}", exc_info=True)
            return False # File update failed

        # 6. Verify Data Integrity (Optional)
        if self.verify_integrity:
             try:
                 self._verify_data_integrity(filepath)
             except Exception as verify_e:
                  # Log warning but don't mark the update as failed just for verification error
                  self.logger.warning(f"Integrity verification failed after updating file {filepath.name}: {verify_e}", exc_info=True)
            
        self.logger.info(f"Successfully updated data for {symbol} {timeframe_name}.")
        return True

    def _get_data_filepath(self, symbol_upper: str, timeframe_lower: str) -> Path:
        """
        Constructs the absolute data filepath using configured patterns and base directory.
        Ensures the parent directory exists.

        Args:
            symbol_upper (str): Symbol name, already converted to UPPERCASE.
            timeframe_lower (str): Timeframe name, already converted to lowercase.

        Returns:
            Path: The absolute Path object for the data file.

        Raises:
            ValueError: If configured patterns are missing required placeholders.
            Exception: For other path construction or directory creation errors.
        """
        self.logger.debug(f"Constructing filepath for {symbol_upper} {timeframe_lower}...")
        
        # Validate patterns contain expected placeholders
        # Use lower() for case-insensitive check of placeholders
        if '{symbol}' not in self.data_dir_pattern.lower():
             error_msg = f"Configuration error: 'historical.data_directory_pattern' is missing the '{{symbol}}' placeholder. Current pattern: '{self.data_dir_pattern}'"
             self.logger.error(error_msg)
             raise ValueError(error_msg)
             
        # filename_pattern requires both {symbol} and {timeframe_lower}
        if '{symbol}' not in self.filename_pattern.lower():
             error_msg = f"Configuration error: 'historical.filename_pattern' is missing the '{{symbol}}' placeholder. Current pattern: '{self.filename_pattern}'"
             self.logger.error(error_msg)
             raise ValueError(error_msg)
        if '{timeframe_lower}' not in self.filename_pattern.lower():
             error_msg = f"Configuration error: 'historical.filename_pattern' is missing the '{{timeframe_lower}}' placeholder. Current pattern: '{self.filename_pattern}'"
             self.logger.error(error_msg)
             raise ValueError(error_msg)
             
        try:
            # Use .format() with explicit keywords for clarity and robustness.
            # Ensure the case matches the variable names passed in (symbol_upper, timeframe_lower).
            relative_dir_str = self.data_dir_pattern.format(symbol=symbol_upper)
            filename_str = self.filename_pattern.format(symbol=symbol_upper, timeframe_lower=timeframe_lower)
            
            # Combine base directory, relative directory, and filename using Path objects for robustness
            # self.base_data_dir should already be a Path object from __init__
            absolute_path = (self.base_data_dir / relative_dir_str / filename_str).resolve()
            
            # Ensure the parent directory exists *before* returning the path
            # This prevents errors later when trying to write the file
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Calculated absolute filepath: {absolute_path}")
            
            return absolute_path
            
        except KeyError as e:
            # Catch potential errors if .format() fails due to unexpected placeholders
            error_msg = f"Error formatting path patterns for {symbol_upper} {timeframe_lower}. Missing key: {e}. Patterns: dir='{self.data_dir_pattern}', file='{self.filename_pattern}'"
            self.logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)
        except OSError as e:
            # Catch errors during directory creation (e.g., permissions)
            error_msg = f"Error creating parent directory for {symbol_upper} {timeframe_lower}: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise # Re-raise OS errors as they are likely critical
        except Exception as e:
            # Catch any other unexpected errors during path construction
            error_msg = f"Unexpected error constructing filepath for {symbol_upper} {timeframe_lower}: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise # Re-raise other critical errors

    def _get_fetch_start_time(self, filepath: Path, timeframe_name: str) -> Optional[datetime]:
        """
        Determines the UTC start datetime for fetching new data.
        If the file exists, it reads the last timestamp and returns the next second.
        If the file doesn't exist, it calculates a default start time based on config.

        Args:
            filepath (Path): The absolute path to the data file.
            timeframe_name (str): The timeframe name (e.g., 'M1', 'H1', UPPERCASE).

        Returns:
            Optional[datetime]: The timezone-aware UTC datetime to start fetching from,
                                or None if a critical error occurs preventing determination.
        """
        self.logger.debug(f"Determining fetch start time for {filepath.name} ({timeframe_name})...")
        
        if filepath.exists() and filepath.stat().st_size > 0:
            self.logger.debug(f"File exists: {filepath}. Attempting to read last timestamp.")
            try:
                # --- Efficiently read the last line --- 
                # Technique: Seek to near the end, read a chunk, find the last newline.
                # This avoids reading the entire file.
                buffer_size = 1024  # Read a reasonable chunk size
                with open(filepath, 'rb') as f:
                    # Go to the end of the file minus a buffer
                    try:
                        f.seek(-buffer_size, os.SEEK_END)
                    except OSError: # Handle file smaller than buffer
                        f.seek(0)
                    last_lines = f.readlines()
                
                if not last_lines:
                    self.logger.warning(f"File {filepath.name} exists but couldn't read last lines. Using default start time.")
                    return self._get_default_start_time(timeframe_name)
                    
                # Get the very last non-empty line
                last_line_bytes = last_lines[-1].strip()
                if not last_line_bytes:
                     # If last line is empty, try second to last
                     if len(last_lines) > 1:
                          last_line_bytes = last_lines[-2].strip()
                     else:
                          self.logger.warning(f"Could not find a non-empty last line in {filepath.name}. Using default start time.")
                          return self._get_default_start_time(timeframe_name)
                          
                last_line = last_line_bytes.decode('utf-8', errors='ignore')
                self.logger.debug(f"Last line read: {last_line}")
                
                # --- Parse the timestamp (assuming CSV with header, time is first col) ---
                parts = last_line.split(',')
                if not parts:
                    self.logger.warning(f"Could not split last line into parts: {last_line}. Using default start time.")
                    return self._get_default_start_time(timeframe_name)
                
                # Check if it looks like the header line (e.g., contains 'time')
                if 'time' in parts[0].lower(): # Check first part for header keyword
                     self.logger.warning(f"Last line looks like header in {filepath.name}. File might be empty or contain only header. Using default start time.")
                     return self._get_default_start_time(timeframe_name)
                     
                try:
                    # --- Robust Timestamp Parsing ---
                    last_dt_utc = None
                    try:
                        # Attempt 1: Parse as Unix timestamp integer (preferred)
                        last_timestamp_sec = int(parts[0])
                        last_dt_utc = datetime.fromtimestamp(last_timestamp_sec, tz=self.timezone)
                        self.logger.debug(f"Parsed last timestamp as integer: {last_timestamp_sec} -> {last_dt_utc}")
                    except ValueError:
                        # Attempt 2: Parse as datetime string (fallback)
                        self.logger.warning(f"Could not parse '{parts[0]}' as integer timestamp. Attempting to parse as datetime string.")
                        try:
                            # Try pandas first, handles various formats
                            last_dt_naive = pd.to_datetime(parts[0]) 
                            # Assume the string represents UTC time or localize it
                            if last_dt_naive.tzinfo is None:
                                last_dt_utc = self.timezone.localize(last_dt_naive)
                            else:
                                last_dt_utc = last_dt_naive.tz_convert(self.timezone)
                            self.logger.info(f"Successfully parsed last timestamp as datetime string: {parts[0]} -> {last_dt_utc}")
                        except Exception as strptime_e:
                            self.logger.error(f"Failed to parse timestamp from last line '{last_line}' in {filepath.name} as integer or string: {strptime_e}. Using default start time.")
                            return self._get_default_start_time(timeframe_name)

                    if last_dt_utc:
                        # Start fetching from the second *after* the last recorded time
                        next_dt_utc = last_dt_utc + timedelta(seconds=1)
                        self.logger.info(f"Last timestamp found: {last_dt_utc}. Fetching from: {next_dt_utc}")
                        return next_dt_utc
                    else:
                         # Should not happen if parsing succeeded, but as a safeguard
                         self.logger.error(f"Timestamp parsing logic failed unexpectedly for '{parts[0]}'. Using default start time.")
                         return self._get_default_start_time(timeframe_name)
                         
                except (IndexError) as parse_e: # Keep IndexError separate
                    self.logger.error(f"Failed to access timestamp part from last line '{last_line}' in {filepath.name}: {parse_e}. Using default start time.")
                    return self._get_default_start_time(timeframe_name)
                    
            except Exception as read_e:
                self.logger.error(f"Error reading last timestamp from {filepath.name}: {read_e}", exc_info=True)
                self.logger.warning("Falling back to default start time due to read error.")
                return self._get_default_start_time(timeframe_name)
        else:
            if not filepath.exists():
                 self.logger.info(f"File not found: {filepath.name}. Using default start time.")
            elif filepath.stat().st_size == 0:
                 self.logger.info(f"File exists but is empty: {filepath.name}. Using default start time.")
            else:
                 # This case shouldn't be reached due to the check above, but just in case
                 self.logger.warning(f"File state unclear for {filepath.name}. Using default start time.")
                 
            return self._get_default_start_time(timeframe_name)

    def _get_default_start_time(self, timeframe_name: str) -> datetime:
        """Calculates the default UTC start datetime based on configured offsets."""
        self.logger.debug(f"Calculating default start time for timeframe {timeframe_name}...")
        now_utc = datetime.now(self.timezone)
        start_date_config = OmegaConf.select(self.config, "historical.start_date")
        default_offsets = OmegaConf.select(self.config, "historical.default_start_offsets", default={})

        # 1. Check for fixed start_date in config
        if start_date_config:
            try:
                start_dt_naive = datetime.strptime(start_date_config, "%Y-%m-%d")
                start_dt_utc = self.timezone.localize(start_dt_naive)
                # Use the CORRECT variable name here in the log message
                self.logger.info(f"Using fixed start date from config 'historical.start_date': {start_date_config} -> {start_dt_utc}")
                return start_dt_utc
            except ValueError as e:
                self.logger.warning(f"Failed to parse fixed start date '{start_date_config}': {e}. Falling back to offsets.")
            except Exception as e:
                 # Use the CORRECT variable name here too
                 self.logger.error(f"Error processing fixed start date '{start_date_config}': {e}. Falling back to offsets.", exc_info=True)

        # 2. Fallback to default offsets if fixed date not present or invalid
        offset_str = default_offsets.get(timeframe_name.upper(), "1y") # Default to 1 year if specific offset not found
        self.logger.debug(f"Using offset '{offset_str}' for timeframe {timeframe_name}")
        
        try:
            num_str = offset_str[:-1]
            unit = offset_str[-1].lower()
            num = int(num_str)
            
            if unit == 'd':
                delta = timedelta(days=num)
            elif unit == 'w':
                delta = timedelta(weeks=num)
            elif unit == 'm':
                # Approximate months as 30 days for simplicity
                delta = timedelta(days=num * 30) 
            elif unit == 'y':
                # Approximate years as 365 days
                delta = timedelta(days=num * 365)
            else:
                self.logger.warning(f"Unrecognized offset unit '{unit}' in '{offset_str}'. Using default 1 year offset.")
                delta = timedelta(days=365)
                
        except (ValueError, IndexError) as e:
            self.logger.warning(f"Failed to parse offset string '{offset_str}': {e}. Using default 1 year offset.")
            delta = timedelta(days=365)

        default_start_utc = now_utc - delta
        self.logger.info(f"Calculated default start time for {timeframe_name} using offset '{offset_str}': {default_start_utc}")
        return default_start_utc

    def _fetch_historical_data_chunked(self, symbol: str, timeframe_mt5: Any, start_dt_utc: datetime, end_dt_utc: datetime) -> Optional[pd.DataFrame]:
        """
        Fetches historical data from MT5 in chunks to avoid request limits and handle potential errors.

        Args:
            symbol (str): Symbol name (UPPERCASE).
            timeframe_mt5 (Any): MT5 timeframe constant.
            start_dt_utc (datetime): Start datetime (timezone-aware UTC).
            end_dt_utc (datetime): End datetime (timezone-aware UTC).

        Returns:
            Optional[pd.DataFrame]: Combined DataFrame of all successfully fetched chunks, 
                                     sorted by time with duplicates removed. Returns None if a 
                                     critical failure occurs during fetching that prevents completion.
                                     Returns an empty DataFrame if no data is found in the range.
        """
        if not self.mt5_library_available or mt5 is None:
            self.logger.error("Cannot fetch data: MT5 library not available.")
            return None
            
        self.logger.info(f"Starting chunked fetch for {symbol} TF={timeframe_mt5} from {start_dt_utc} to {end_dt_utc}...")
        all_rates_list = [] # Use a list to collect chunk data (tuples)
        current_start_dt = start_dt_utc
        total_bars_fetched = 0

        while current_start_dt < end_dt_utc:
            # Calculate end of current chunk
            # Ensure batch_size_days is at least 1
            chunk_days = max(1, self.batch_size_days) 
            chunk_end_dt = current_start_dt + timedelta(days=chunk_days)
            # Don't fetch beyond the overall end date
            chunk_end_dt = min(chunk_end_dt, end_dt_utc)

            self.logger.debug(f"Fetching chunk: {symbol} from {current_start_dt} to {chunk_end_dt}")

            # --- Call MT5 API with retries ---
            rates_tuple = self._fetch_single_chunk_with_retries(symbol, timeframe_mt5, current_start_dt, chunk_end_dt)
            
            if rates_tuple is None:
                self.logger.error(f"Failed to fetch chunk for {symbol} from {current_start_dt} after retries. Aborting fetch for this symbol/timeframe.")
                return None # Indicate critical failure for this fetch operation

            if rates_tuple is not None and len(rates_tuple) > 0: # Check if MT5 returned data
                # --- NEW: Explicitly convert to list of standard tuples if it's a numpy array ---
                processed_rates = []
                # We need to import numpy for isinstance check
                import numpy as np 
                if isinstance(rates_tuple, np.ndarray): # Check if it's a NumPy array
                    # Convert structured array to list of tuples
                    processed_rates = [tuple(row) for row in rates_tuple] 
                    self.logger.debug(f"Converted NumPy array chunk ({len(processed_rates)} records) to list of tuples.")
                else: 
                    # Assume it's already an iterable of tuples or similar records
                    # Use list() for safer conversion than map if rates_tuple structure is uncertain
                    try:
                       processed_rates = [tuple(item) for item in rates_tuple]
                       self.logger.debug(f"Processed non-NumPy chunk ({len(processed_rates)} records) to list of tuples.")
                    except TypeError as te:
                         self.logger.error(f"Could not convert chunk data to list of tuples for {symbol}: {te}", exc_info=True)
                         return None # Treat as critical failure if conversion fails
                # -----------------------------------------------------------------------------

                all_rates_list.extend(processed_rates) # Extend with the processed list
                total_bars_fetched += len(processed_rates)
                
                # --- Determine the next start time (using processed_rates or original rates_tuple?) ---
                # It's safer to use the original rates_tuple here if possible, 
                # as indexing might be different on the processed list vs structured array.
                # Let's assume rates_tuple[-1][0] works on the MT5 return structure directly.
                try:
                    last_time_in_chunk_sec = rates_tuple[-1][0]
                    last_dt_in_chunk = datetime.fromtimestamp(last_time_in_chunk_sec, tz=self.timezone)
                    current_start_dt = last_dt_in_chunk + timedelta(seconds=1) 
                    self.logger.debug(f"Chunk fetched successfully. {len(processed_rates)} bars processed. Last time: {last_dt_in_chunk}. Next start: {current_start_dt}")
                except (IndexError, TypeError, ValueError) as e:
                     self.logger.error(f"Could not determine next start time from last bar of chunk for {symbol}: {e}. Falling back to advancing by chunk size.", exc_info=True)
                     current_start_dt = chunk_end_dt 
            else:
                 # No data returned for this chunk, move to the next period
                 self.logger.debug(f"No data returned for chunk {symbol} from {current_start_dt} to {chunk_end_dt}. Moving to next chunk interval.")
                 current_start_dt = chunk_end_dt # Move start to end of this empty chunk

            # Optional delay between chunks to avoid hammering the server
            if self.delay_between_requests_ms > 0 and current_start_dt < end_dt_utc:
                 time.sleep(self.delay_between_requests_ms / 1000.0)

        # --- Post-processing after all chunks --- (DataFrame creation part)
        if not all_rates_list:
            self.logger.info(f"Finished chunked fetch for {symbol}. No data found in the entire range.")
            return pd.DataFrame() # Return empty DataFrame

        self.logger.info(f"Finished chunked fetch for {symbol}. Total bars fetched across all chunks: {total_bars_fetched}.")
        
        try:
            # Now create the DataFrame from the list of standard tuples
            expected_columns = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            all_rates_df = pd.DataFrame(all_rates_list, columns=expected_columns)
            
            # Convert time column
            all_rates_df['time'] = pd.to_datetime(all_rates_df['time'], unit='s', utc=True)

            # Remove duplicates 
            initial_rows = len(all_rates_df)
            all_rates_df = all_rates_df.drop_duplicates(subset=['time'], keep='first') 
            duplicates_removed = initial_rows - len(all_rates_df)
            if duplicates_removed > 0:
                 self.logger.warning(f"Removed {duplicates_removed} duplicate bars based on timestamp for {symbol}.")
                 
            # Sort by time
            all_rates_df = all_rates_df.sort_values(by='time', ascending=True, ignore_index=True)
            
            self.logger.info(f"Successfully processed {len(all_rates_df)} unique bars for {symbol}.")
            return all_rates_df
            
        except Exception as e:
            self.logger.error(f"Error processing fetched data into DataFrame for {symbol}: {e}", exc_info=True)
            return None # Indicate critical failure during processing
        # --- End of DataFrame creation part ---

    def _fetch_single_chunk_with_retries(self, symbol: str, timeframe_mt5: Any, start_dt: datetime, end_dt: datetime) -> Optional[List[Tuple]]:
        """
        Fetches a single chunk of data from MT5 using copy_rates_range with retry logic.

        Args:
            symbol (str): Symbol name (UPPERCASE).
            timeframe_mt5 (Any): MT5 timeframe constant.
            start_dt (datetime): Start datetime (timezone-aware UTC).
            end_dt (datetime): End datetime (timezone-aware UTC).

        Returns:
            Optional[List[Tuple]]: A list of rate tuples if successful (can be empty), 
                                   or None if all retry attempts fail.
        """
        if not self.mt5_library_available or mt5 is None:
            self.logger.error("Cannot fetch chunk: MT5 library not available.")
            return None
            
        attempt = 0
        while attempt < self.retry_attempts:
            attempt += 1
            if attempt > 1:
                # Use simple linear delay for now, could add exponential backoff
                sleep_time = self.retry_delay_seconds
                self.logger.warning(f"Retrying fetch for {symbol} ({start_dt} to {end_dt}), attempt {attempt}/{self.retry_attempts}, waiting {sleep_time}s...")
                time.sleep(sleep_time)

            try:
                 # --- Check MT5 Connection ---
                 # It's often better to assume the connection established by run_update_cycle is stable,
                 # but a quick check can sometimes help diagnose issues faster.
                 # term_info = mt5.terminal_info()
                 # if not term_info or not term_info.connected:
                 #      self.logger.error(f"MT5 connection lost before fetching chunk (Attempt {attempt}). Aborting retries for this chunk.")
                 #      # Don't try to reconnect here, let the main loop handle connection issues if needed.
                 #      return None
                 # --------------------------

                 # Core MT5 API call
                 self.logger.debug(f"Calling copy_rates_range for {symbol}, tf={timeframe_mt5}, start={start_dt}, end={end_dt} (Attempt {attempt})")
                 rates = mt5.copy_rates_range(symbol, timeframe_mt5, start_dt, end_dt)

                 if rates is not None:
                     # Success: MT5 returned a result (list of tuples, possibly empty)
                     self.logger.debug(f"copy_rates_range returned {len(rates)} bars for {symbol} ({start_dt} to {end_dt}).")
                     return list(rates) # Ensure it's a list
                 else:
                     # Failure: MT5 API call returned None
                     error_code = mt5.last_error()
                     self.logger.error(f"mt5.copy_rates_range failed for {symbol} ({start_dt} to {end_dt}) on attempt {attempt}. Error: {error_code}")
                     # Specific handling for certain potentially recoverable errors?
                     # e.g., if error_code suggests a temporary issue vs. invalid symbol
                     # Continue to the next retry attempt

            except Exception as e:
                # Catch unexpected exceptions during the API call or processing
                self.logger.error(f"Exception during MT5 fetch chunk for {symbol} ({start_dt} to {end_dt}) on attempt {attempt}: {e}", exc_info=True)
                # Continue to the next retry attempt

        # If all retry attempts fail
        self.logger.error(f"Failed to fetch data chunk for {symbol} ({start_dt} to {end_dt}) after {self.retry_attempts} attempts.")
        return None


    def _update_historical_file(self, filepath: Path, new_data: pd.DataFrame):
        """
        Updates the historical data CSV file atomically by writing to a temporary file
        and then replacing the original file.
        Merges new data with existing data if the file already exists.

        Args:
            filepath (Path): The absolute path to the target CSV file.
            new_data (pd.DataFrame): DataFrame containing the new K-line data to add.
                                     Assumed to have columns like 'time', 'open', etc.,
                                     with 'time' as timezone-aware UTC datetime objects.

        Raises:
            Exception: If any critical error occurs during file reading, writing, or replacement.
        """
        if new_data.empty:
            self.logger.info(f"No new data provided for {filepath.name}, skipping file update.")
            return

        self.logger.info(f"Starting atomic update for file: {filepath.name}")
        temp_filepath = filepath.with_suffix(f'{filepath.suffix}.tmp') # e.g., EURUSD_m1.csv.tmp
        final_df = pd.DataFrame()

        try:
            # 1. Read existing data if file exists and is not empty
            existing_df = pd.DataFrame()
            if filepath.exists() and filepath.stat().st_size > 0:
                self.logger.debug(f"Reading existing data from {filepath.name}...")
                try:
                    # --- Robust Reading Logic --- 
                    # 1. Read 'time' column as object initially
                    existing_df = pd.read_csv(
                        filepath,
                        dtype={'time': object} # Read as string/object first
                        # Removed parse_dates and date_parser
                    )
                    
                    if not existing_df.empty and 'time' in existing_df.columns:
                        time_col = existing_df['time']
                        parsed_time = pd.NaT # Initialize as Not a Time

                        # 2. Attempt to parse as '%Y-%m-%d %H:%M:%S' string first
                        try:
                            parsed_time_str = pd.to_datetime(time_col, format='%Y-%m-%d %H:%M:%S', utc=True, errors='coerce')
                            # Check if parsing was successful (less NaNs than original implies some success)
                            if parsed_time_str.notna().any(): 
                                parsed_time = parsed_time_str
                                self.logger.debug(f"Successfully parsed time column in {filepath.name} using string format.")
                            else:
                                 self.logger.warning(f"String format parsing resulted in all NaNs for {filepath.name}. Will try integer format.")
                        except Exception as str_parse_e:
                             self.logger.warning(f"Error attempting to parse time as string format in {filepath.name}: {str_parse_e}. Trying integer format.")
                             
                        # 3. If string parsing failed or resulted in NaT, attempt integer parsing
                        if pd.isna(parsed_time).all(): # Check if all values are still NaT
                            try:
                                # Ensure the column is numeric-like before unit='s'
                                # Handle potential non-numeric strings gracefully
                                numeric_time_col = pd.to_numeric(time_col, errors='coerce')
                                parsed_time_int = pd.to_datetime(numeric_time_col, unit='s', utc=True, errors='coerce')
                                if parsed_time_int.notna().any():
                                    parsed_time = parsed_time_int
                                    self.logger.debug(f"Successfully parsed time column in {filepath.name} using integer (Unix timestamp) format.")
                                else:
                                     self.logger.error(f"Failed to parse time column in {filepath.name} using both string and integer formats.")
                                     existing_df = pd.DataFrame() # Treat as unreadable
                            except Exception as int_parse_e:
                                 self.logger.error(f"Error attempting to parse time as integer format in {filepath.name}: {int_parse_e}. Treating file as unreadable.")
                                 existing_df = pd.DataFrame() # Treat as unreadable

                        # Assign the successfully parsed column and drop errors
                        if not existing_df.empty:
                             existing_df['time'] = parsed_time
                             rows_before_dropna = len(existing_df)
                             existing_df = existing_df.dropna(subset=['time'])
                             rows_dropped = rows_before_dropna - len(existing_df)
                             if rows_dropped > 0:
                                 self.logger.warning(f"Dropped {rows_dropped} rows from {filepath.name} due to time parsing errors.")
                    else:
                         # Handle empty DataFrame or missing time column after read
                         self.logger.warning(f"Existing file {filepath.name} is empty or missing 'time' column after read. Treating as empty.")
                         existing_df = pd.DataFrame()
                    # --- End of Robust Reading Logic ---

                    # Validate essential columns exist (after potential parsing)
                    if not existing_df.empty and not all(col in existing_df.columns for col in ['time', 'open', 'close']):
                         self.logger.warning(f"Existing file {filepath.name} is missing essential columns after parsing. Treating as empty.")
                         existing_df = pd.DataFrame()
                    elif not existing_df.empty:
                         self.logger.info(f"Read and parsed {len(existing_df)} records from existing file {filepath.name}.")
                         # Ensure 'time' column is timezone-aware UTC (should be from parsing)
                         if not pd.api.types.is_datetime64_any_dtype(existing_df['time']):
                             self.logger.error(f"Internal Error: Time column in {filepath.name} is not datetime after parsing! Setting df empty.")
                             existing_df = pd.DataFrame()
                         elif existing_df['time'].dt.tz is None:
                              self.logger.warning(f"Time column in {filepath.name} parsed as naive. Localizing to UTC.")
                              existing_df['time'] = existing_df['time'].dt.tz_localize(self.timezone)
                         else:
                             existing_df['time'] = existing_df['time'].dt.tz_convert(self.timezone)

                except pd.errors.EmptyDataError:
                    self.logger.warning(f"Existing file {filepath.name} is empty. Will create new file.")
                    existing_df = pd.DataFrame()
                except Exception as read_e:
                    self.logger.error(f"Error reading existing file {filepath.name}: {read_e}. Will attempt to overwrite with new data.", exc_info=True)
                    # Decide whether to bail out or try overwriting. Overwriting is risky if read failed badly.
                    # For robustness, let's proceed assuming we overwrite with new_data only if read fails.
                    existing_df = pd.DataFrame() # Treat as empty on read failure
            else:
                self.logger.info(f"File {filepath.name} does not exist or is empty. Creating new file.")

            # 2. Prepare the final DataFrame (merge, sort, drop duplicates)
            if not existing_df.empty:
                # Ensure new_data's time column is also timezone-aware UTC before concat
                if not pd.api.types.is_datetime64_any_dtype(new_data['time']) or new_data['time'].dt.tz is None:
                     self.logger.error("New data time column is not timezone-aware UTC! Correcting.") # Should not happen if fetch is correct
                     new_data['time'] = pd.to_datetime(new_data['time'], unit='s', utc=True)
                else:
                    new_data['time'] = new_data['time'].dt.tz_convert(self.timezone)
                    
                # Concatenate old and new data
                final_df = pd.concat([existing_df, new_data], ignore_index=True)
                self.logger.debug(f"Concatenated data: {len(final_df)} records.")
                
                # Drop duplicates based on time, keeping the latest (usually the new one if overlap)
                initial_rows = len(final_df)
                final_df = final_df.drop_duplicates(subset=['time'], keep='last')
                duplicates_removed = initial_rows - len(final_df)
                if duplicates_removed > 0:
                    self.logger.warning(f"Removed {duplicates_removed} duplicate records based on timestamp during merge for {filepath.name}.")
                
                # Sort by time
                final_df = final_df.sort_values(by='time', ascending=True, ignore_index=True)
                self.logger.debug("Merged, deduplicated, and sorted data.")
            else:
                # If no existing data, the final data is just the new data
                # Ensure new_data time column is correct type before assigning
                if not pd.api.types.is_datetime64_any_dtype(new_data['time']) or new_data['time'].dt.tz is None:
                     self.logger.error("New data time column is not timezone-aware UTC! Correcting.")
                     new_data['time'] = pd.to_datetime(new_data['time'], unit='s', utc=True)
                else:
                    new_data['time'] = new_data['time'].dt.tz_convert(self.timezone)
                final_df = new_data.sort_values(by='time', ascending=True, ignore_index=True)
                self.logger.debug("Using only new data as final data.")

            # 3. Prepare for writing: Convert time back to the desired format
            if not final_df.empty:
                # --- Ensure UTC before formatting ---
                # Regardless of previous checks, forcefully ensure the time column is UTC
                # This handles cases where concat might have produced naive time
                try:
                    if final_df['time'].dt.tz is None:
                        self.logger.debug(f"Force localizing naive time to UTC before strftime for {filepath.name}")
                        final_df['time'] = final_df['time'].dt.tz_localize('UTC')
                    else:
                        self.logger.debug(f"Force converting time to UTC before strftime for {filepath.name}")
                        final_df['time'] = final_df['time'].dt.tz_convert('UTC')
                except Exception as force_utc_e:
                    self.logger.error(f"Failed to forcefully ensure UTC time before formatting: {force_utc_e}. Aborting write for {filepath.name}", exc_info=True)
                    return

                # Format the datetime objects into the desired string format
                try:
                    final_df['time'] = final_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    self.logger.debug(f"Converted time column to string format 'YYYY-MM-DD HH:MM:SS' for {filepath.name}.")
                except Exception as fmt_e:
                    self.logger.error(f"Failed to format time column to string: {fmt_e}. Aborting write for {filepath.name}", exc_info=True)
                    return # Prevent writing bad data
            else:
                 self.logger.warning(f"Final DataFrame is empty for {filepath.name} after processing. No file will be written.")
                 return # Nothing to write

            # 4. Write to temporary file
            self.logger.debug(f"Writing {len(final_df)} records to temporary file: {temp_filepath.name}...")
            # Ensure float format keeps precision if needed, though not directly related to time format
            final_df.to_csv(temp_filepath, index=False, header=True, encoding='utf-8', float_format='%.5f') 
            self.logger.debug("Write to temporary file successful.")

            # 5. Atomically replace original file with temporary file
            self.logger.debug(f"Atomically replacing {filepath.name} with {temp_filepath.name}...")
            os.replace(temp_filepath, filepath)
            self.logger.info(f"Successfully updated file: {filepath.name}")

        except Exception as e:
            self.logger.error(f"Failed during atomic file update for {filepath.name}: {e}", exc_info=True)
            # Clean up temp file if it exists after an error
            if temp_filepath.exists():
                try:
                    temp_filepath.unlink()
                    self.logger.info(f"Removed temporary file {temp_filepath.name} after error.")
                except OSError as unlink_e:
                    self.logger.error(f"Failed to remove temporary file {temp_filepath.name} after error: {unlink_e}")
            raise # Re-raise the exception to signal failure


    def _verify_data_integrity(self, filepath: Path):
        """
        Performs basic data integrity checks on the CSV file:
        - Checks for duplicate timestamps.
        - Checks for significant time gaps between consecutive bars.

        Args:
            filepath (Path): The absolute path to the CSV file to verify.
        """
        if not self.verify_integrity:
             self.logger.debug(f"Integrity verification is disabled in config. Skipping for {filepath.name}.")
             return
             
        if not filepath.exists() or filepath.stat().st_size == 0:
            self.logger.debug(f"File does not exist or is empty: {filepath.name}. Skipping integrity verification.")
            return

        self.logger.info(f"Starting integrity verification for: {filepath.name}...")
        try:
            # Modified read_csv: Specify date format explicitly
            df = pd.read_csv(
                filepath,
                parse_dates=['time'], # Instruct pandas to parse the time column
                # Add format specifier to eliminate warning and ensure consistency
                date_format='%Y-%m-%d %H:%M:%S' 
            )

            if df.empty or 'time' not in df.columns or not pd.api.types.is_datetime64_any_dtype(df['time']): # Check if parsing failed or column missing/wrong type
                 self.logger.warning(f"File {filepath.name} is empty or time column missing/invalid after parsing. Skipping integrity check.")
                 return True # Treat as OK for now, maybe just an empty file

            # Check for duplicates based on the 'time' column
            duplicates = df[df.duplicated(subset=['time'], keep=False)]
            if not duplicates.empty:
                self.logger.warning(f"Data integrity issue in {filepath.name}: Found {len(duplicates)} duplicate timestamp entries.")
                self.logger.debug(f"Duplicate timestamps found:\\n{duplicates.to_string()}")
                # Depending on policy, you might want to return False or attempt cleaning
                # For now, just log it
                # return False 

            # Check if data is sorted by time
            if not df['time'].is_monotonic_increasing:
                self.logger.warning(f"Data integrity issue in {filepath.name}: Data is not sorted chronologically by time.")
                # Find where sorting fails
                diffs = df['time'].diff()
                first_unsorted = diffs[diffs < pd.Timedelta(0)].first_valid_index()
                if first_unsorted is not None and first_unsorted > 0:
                     self.logger.debug(f"First unsorted data point occurs around index {first_unsorted}:\\n{df.iloc[first_unsorted-1:first_unsorted+2]}")
                # return False

            self.logger.info(f"Integrity verification finished for: {filepath.name}. No critical issues detected.")
            return True

        except FileNotFoundError:
            self.logger.warning(f"Integrity check failed: File {filepath.name} not found (perhaps deleted?).")
            return False # File missing is an issue
        except pd.errors.EmptyDataError:
             self.logger.info(f"Integrity check: File {filepath.name} is empty. Skipping checks.")
             return True # Empty file is considered OK
        except Exception as e:
            self.logger.error(f"Error during integrity verification for {filepath.name}: {e}", exc_info=True)
            return False # Any other error means integrity check failed

    def _get_interval_seconds(self, timeframe_str: str) -> Optional[int]:
        """Helper to get the expected interval in seconds for a given timeframe string."""
        tf = timeframe_str.upper()
        if tf == 'M1': return 60
        if tf == 'M5': return 300
        if tf == 'M15': return 900
        if tf == 'M30': return 1800
        if tf == 'H1': return 3600
        if tf == 'H4': return 14400
        if tf == 'D1': return 86400
        # Add W1 and MN1 if needed, though gaps are expected
        # if tf == 'W1': return 604800
        # if tf == 'MN1': return 2592000 # Approx
        self.logger.warning(f"Could not determine interval seconds for unknown timeframe: {timeframe_str}")
        return None

# --- Additional Helper Methods (e.g., parsing offset strings) ---
# def _parse_offset(self, offset_str: str) -> timedelta:
#     # ... (Implementation similar to old _parse_offset) ...
#     pass

# --- Main execution block (optional, for testing) ---
if __name__ == '__main__':
     print("Running history.py directly for testing...")
     # Basic setup for testing
     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
     test_logger = logging.getLogger('HistoryTest')

     # Load config (replace with actual path loading if needed)
     try:
         # Need load_app_config from utils for this test block
         from core.utils import load_app_config
         test_config = load_app_config('market_price_data/config/updater.yaml')
         test_logger.info("Test config loaded.")
     except Exception as e:
         test_logger.error(f"Failed to load test config: {e}", exc_info=True)
         sys.exit(1)

     # Create updater instance
     updater = HistoryUpdater()

     # Check if enabled and run
     if updater.config and updater.updater_enabled:
         test_logger.info("Starting test update cycle...")
         updater.run_update_cycle()
         test_logger.info("Test update cycle finished.")
     else:
         test_logger.warning("Updater is disabled in test config or failed to initialize.") 