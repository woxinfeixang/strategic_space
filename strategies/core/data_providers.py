import pandas as pd
import os
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path # Import Path
from omegaconf import OmegaConf, DictConfig # Import DictConfig
from core.utils import get_filepath, setup_logging # 从core模块导入 setup_logging
import yaml # Import yaml for loading specs
import pytz # 确保导入 pytz
import datetime # Import datetime for timezone comparison

# --- 从 economic_calendar 模块导入 ---
# 假设可以从 economic_calendar.data.loader 导入 load_input_file
# 如果你的项目结构不同，需要调整这里的导入路径
try:
    from economic_calendar.data.loader import load_input_file
except ImportError:
    load_input_file = None
    logging.warning("Could not import 'load_input_file' from 'economic_calendar.data.loader'. EconomicCalendarProvider might not work.")

# ---> 导入新创建的函数
try:
    from economic_calendar.event_filter.enhancements import add_strategy_metadata
except ImportError:
    add_strategy_metadata = None
    logging.warning("Could not import 'add_strategy_metadata' from 'economic_calendar.event_filter.enhancements'. Metadata hook disabled.")

# --- 从 market_price_data 模块导入 ---
# 我们不直接依赖 HistoryUpdater 或 RealtimeUpdater 实例，而是读取它们生成的文件
# 导入路径获取工具
try:
    # Try importing from core.utils first as it might be centralized
    from core.utils import get_filepath as core_get_filepath
    if core_get_filepath:
        get_filepath = core_get_filepath # Prefer core version if available
    else:
        raise ImportError # Force fallback if core version is None
except ImportError:
    try:
        # Fallback to market_price_data.utils if core fails
        from market_price_data.utils import get_filepath as mpd_get_filepath
        get_filepath = mpd_get_filepath
        logging.warning("Using 'get_filepath' from 'market_price_data.utils'. Consider centralizing in 'core.utils'.")
    except ImportError:
        get_filepath = None
        logging.error("Could not import 'get_filepath' from 'core.utils' or 'market_price_data.utils'. MarketDataProvider path generation will fail.")

# ---> Try importing MT5
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
    logging.info("MetaTrader5 library not found. MT5 functionality disabled.")

# --- 配置加载 ---
# Removed hardcoded example config dictionary
# config = { ... }

# --- 日志设置 ---
# TODO: 集成项目的主日志系统
# 由主入口或调用者使用 setup_logging 进行配置，这里仅获取 logger
logger = logging.getLogger(__name__) # Use __name__ for module-level logger

# ----------------------
# 财经日历数据提供者
# ----------------------
class EconomicCalendarProvider:
    """
    为策略模块提供统一的财经日历数据访问接口。
    """
    def __init__(self, config: DictConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__) # Get instance logger

        # Use OmegaConf.select for safer access and defaults
        # Assume base_data_dir is resolved correctly before passing config
        base_data_dir = OmegaConf.select(config, "paths.data_dir", default='data') # Use common paths config
        # --- Economic Calendar Paths ---
        live_dir = OmegaConf.select(config, 'economic_calendar.paths.filtered_live_dir', default='calendar/filtered/live')
        live_file = OmegaConf.select(config, 'economic_calendar.files.filtered_live_csv', default='filtered_realtime.csv')
        hist_dir = OmegaConf.select(config, 'economic_calendar.paths.filtered_history_dir', default='calendar/filtered/history')
        hist_file = OmegaConf.select(config, 'economic_calendar.files.filtered_history_csv', default='filtered_history.csv')

        # Combine base path with relative paths
        self.live_filtered_path = str(Path(base_data_dir) / live_dir / live_file)
        self.history_filtered_path = str(Path(base_data_dir) / hist_dir / hist_file)

        self._add_strategy_metadata_hook = None

        # ---> 尝试注册钩子
        if add_strategy_metadata is not None:
            self.register_metadata_hook(add_strategy_metadata)
        else:
            self.logger.warning("'add_strategy_metadata' function not available, metadata hook disabled.")

        if load_input_file is None:
            self.logger.error("初始化失败：'load_input_file' 函数不可用。")

        self.logger.info("EconomicCalendarProvider initialized.")
        self.logger.info(f" - Live events path: {self.live_filtered_path}")
        self.logger.info(f" - History events path: {self.history_filtered_path}")

    def register_metadata_hook(self, hook_function):
        """注册一个函数，用于在返回数据前添加策略元数据。"""
        self._add_strategy_metadata_hook = hook_function
        self.logger.info(f"Registered metadata hook: {hook_function.__name__}")

    def get_filtered_events(self, live: bool = True, **kwargs) -> Optional[pd.DataFrame]:
        """
        读取预处理和筛选后的事件数据。
        使用 economic_calendar 模块的 load_input_file 函数。

        Args:
            live (bool): True 读取实时筛选数据，False 读取历史筛选数据。
            **kwargs: 传递给 load_input_file 的额外参数 (如果有的话)。

        Returns:
            Optional[pd.DataFrame]: 包含事件数据的 DataFrame，如果文件不存在或加载失败则返回 None。
        """
        path = self.live_filtered_path if live else self.history_filtered_path
        self.logger.debug(f"尝试从以下路径加载已过滤事件: {path}")

        if load_input_file is None:
            self.logger.error("'load_input_file' 不可用。无法加载日历事件。")
            return None

        try:
            # 调用 economic_calendar.data.loader 中的函数加载
            df = load_input_file(path)
            if df is None or df.empty:
                 # Changed from warning to debug as it might be normal
                 self.logger.debug(f"从 {path} 加载的事件为空或不存在。")
                 return None # Return None for empty DataFrame

            # 确保 datetime 列已正确解析
            if 'datetime' not in df.columns:
                 # 尝试从 date 和 time 列组合 (假设存在)
                 if 'date' in df.columns and 'time' in df.columns:
                      try:
                          # 处理 '全天' 或无效时间
                          df['time'] = df['time'].replace({'全天': '00:00'}).fillna('00:00')
                          # 处理可能无效的日期格式
                          df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], errors='coerce')
                          df = df.dropna(subset=['datetime'])
                          if df.empty: # Check if all rows dropped
                              self.logger.warning(f"从 {path} 加载的事件在日期时间解析后为空。")
                              return None
                      except Exception as dt_e:
                          self.logger.error(f"组合 {path} 中的 date 和 time 列时出错: {dt_e}")
                          return None
                 else:
                      self.logger.error(f"加载后在 {path} 中未找到必需的 'datetime' 列。")
                      return None
            elif not pd.api.types.is_datetime64_any_dtype(df['datetime']):
                 try:
                     df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
                     df = df.dropna(subset=['datetime'])
                     if df.empty:
                         self.logger.warning(f"从 {path} 加载的事件在现有 'datetime' 列解析后为空。")
                         return None
                 except Exception as parse_e:
                     self.logger.error(f"解析 {path} 中现有的 'datetime' 列时出错: {parse_e}")
                     return None

            # 确保时区 (修正逻辑：假设 naive 时间是北京时间)
            target_tz = 'UTC' # Target is UTC time
            if df['datetime'].dt.tz is None:
                # If naive, assume it represents Beijing Time (Asia/Shanghai) and localize, then convert to UTC.
                self.logger.debug(f"'datetime' column is naive. Assuming Asia/Shanghai, localizing, then converting to {target_tz}.")
                df['datetime'] = df['datetime'].dt.tz_localize('Asia/Shanghai', ambiguous='infer').dt.tz_convert(target_tz)
            elif str(df['datetime'].dt.tz) != target_tz: # Use str() for robust comparison, e.g. pytz.UTC vs datetime.timezone.utc
                # If already timezone-aware but not UTC, convert
                self.logger.debug(f"将财经日历时区从 {df['datetime'].dt.tz} 转换为 {target_tz}")
                df['datetime'] = df['datetime'].dt.tz_convert(target_tz)
            else:
                # Already UTC time
                self.logger.debug(f"财经日历时间已是 {target_tz}")

            self.logger.info(f"成功从 {path} 加载 {len(df)} 个事件，并确保时区为 {target_tz}。")

            # ---> 调用钩子添加元数据
            if self._add_strategy_metadata_hook:
                try:
                    df = self._add_strategy_metadata_hook(df)
                    self.logger.debug("已应用元数据钩子。")
                except Exception as hook_e:
                    self.logger.error(f"应用元数据钩子时出错: {hook_e}", exc_info=True)

            return df
        except FileNotFoundError:
             self.logger.warning(f"过滤事件文件未找到: {path}")
             return None
        except Exception as e:
            self.logger.error(f"使用 load_input_file 从 {path} 读取过滤事件时出错: {e}", exc_info=True)
            return None

    def get_upcoming_events(self, lookahead_window: str = "24h") -> Optional[pd.DataFrame]:
        """
        获取未来指定时间窗口内的事件。

        Args:
            lookahead_window (str): 时间窗口字符串 (e.g., "24h", "1d").

        Returns:
            Optional[pd.DataFrame]: 未来事件的数据，如果出错则返回 None。
        """
        live_events = self.get_filtered_events(live=True)
        if live_events is None or live_events.empty: # Check for empty df
            self.logger.debug("无法获取未来事件：没有实时事件数据。")
            return None

        now = pd.Timestamp.now(tz='UTC')
        try:
            future_limit = now + pd.Timedelta(lookahead_window)
            # Ensure datetime column exists and is correct type before filtering
            if 'datetime' not in live_events.columns or not pd.api.types.is_datetime64_any_dtype(live_events['datetime']):
                self.logger.error("无法获取未来事件: 'datetime' 列缺失或无效。")
                return None

            upcoming = live_events[(live_events['datetime'] > now) & (live_events['datetime'] <= future_limit)]
            self.logger.debug(f"找到 {len(upcoming)} 个在未来 {lookahead_window} 内的事件。")
            return upcoming.sort_values(by='datetime')
        except Exception as e:
            self.logger.error(f"计算未来事件时出错: {e}", exc_info=True)
            return None

# ----------------------
# 市场价格数据提供者
# ----------------------
class MarketDataProvider:
    """
    为策略模块提供统一的市场价格数据访问接口。
    通过直接读取 HistoryUpdater 和 RealtimeUpdater 生成的 CSV 文件来工作。
    或者连接 MT5 获取实时/历史数据。
    """
    def __init__(self, config: DictConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__) # Get instance logger

        # --- MT5 Connection --- 
        self.mt5_initialized = False
        self.mt5_connected = False
        self._initialize_mt5()

        # Use OmegaConf.select for safer access
        self.base_data_dir = OmegaConf.select(config, "paths.data_dir", default='data') # Use common paths config
        # --- Market Data Paths (修改：直接 select 完整路径) ---
        self.hist_dir_pattern = OmegaConf.select(config, 'market_data.historical.data_directory_pattern', default='historical/{symbol}')
        self.hist_filename_pattern = OmegaConf.select(config, 'market_data.historical.filename_pattern', default='{symbol}_{timeframe_lower}.csv')
        self.rt_dir_pattern = OmegaConf.select(config, 'market_data.realtime.data_directory_pattern', default='realtime/{symbol}')
        self.rt_filename_pattern = OmegaConf.select(config, 'market_data.realtime.filename_pattern', default='{symbol}_{timeframe_lower}_realtime.csv')

        # --- Load Instrument Specs --- 
        self.instrument_specs: Dict[str, Any] = {}
        specs_file_path = Path(config.get('paths',{}).get('config_dir', 'config')) / 'instrument_specs.yaml'
        self._load_instrument_specs(specs_file_path)

        if get_filepath is None:
            self.logger.error("初始化失败：'get_filepath' 函数不可用。路径生成将失败。")

        self.logger.info("MarketDataProvider initialized.")
        self.logger.info(f" - MT5 Connected: {self.mt5_connected}")
        self.logger.info(f" - Base data directory: {self.base_data_dir}")
        self.logger.info(f" - Historical path pattern: {self.hist_dir_pattern}/{self.hist_filename_pattern}")
        self.logger.info(f" - Realtime path pattern: {self.rt_dir_pattern}/{self.rt_filename_pattern}")

    def _initialize_mt5(self):
        """ Initialize MT5 connection based on config. """
        if not mt5:
            return # MT5 library not imported
        mt5_config = self.config.get('mt5', {})
        enabled = mt5_config.get('enabled', False)

        if not enabled:
            self.logger.info("MT5 connection is disabled in config.")
            return
        
        login = mt5_config.get('account')
        password = mt5_config.get('password')
        server = mt5_config.get('server')
        path = mt5_config.get('path') # Optional path to terminal64.exe

        if not all([login, password, server]):
            self.logger.warning("MT5 config incomplete (missing account, password, or server). Cannot initialize.")
            return
        
        try:
            start_params = {"login": login, "password": password, "server": server}
            if path:
                start_params["path"] = path
            
            self.logger.info(f"Initializing MT5 connection to server {server}, account {login}...")
            if not mt5.initialize(**start_params):
                self.logger.error(f"MT5 initialize() failed, error code: {mt5.last_error()}")
                mt5.shutdown()
            else:
                self.mt5_initialized = True
                self.mt5_connected = True # Assume connected if initialized ok
                self.logger.info(f"MT5 initialized successfully. Account Info: {mt5.account_info()}")
        except Exception as e:
            self.logger.error(f"Error initializing MT5: {e}", exc_info=True)
            if self.mt5_initialized: mt5.shutdown() # Ensure shutdown on error
            self.mt5_initialized = False
            self.mt5_connected = False

    def _load_instrument_specs(self, filepath: Path):
        """ Load instrument specifications from a YAML file. """
        if not filepath.exists():
            self.logger.warning(f"Instrument specs file not found: {filepath}. Cannot load specs.")
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.instrument_specs = yaml.safe_load(f)
            if self.instrument_specs:
                 self.logger.info(f"Successfully loaded {len(self.instrument_specs)} instrument specs from {filepath}.")
            else:
                 self.logger.warning(f"Instrument specs file {filepath} is empty or invalid.")
                 self.instrument_specs = {} # Ensure it's a dict
        except Exception as e:
            self.logger.error(f"Error loading instrument specs from {filepath}: {e}", exc_info=True)
            self.instrument_specs = {} # Ensure it's a dict on error

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get contract specifications for a symbol.
        Tries MT5 first if connected, otherwise falls back to loaded config file.
        """
        info = None
        # 1. Try MT5 if connected
        if self.mt5_connected:
            try:
                mt5_info = mt5.symbol_info(symbol)
                if mt5_info:
                    self.logger.debug(f"Fetched symbol info for {symbol} from MT5.")
                    # Convert mt5_info named tuple to our dictionary format
                    info = {
                        'contract_size': mt5_info.trade_contract_size,
                        'tick_size': mt5_info.tick_size,
                        # --- Tick Value Calculation (Needs Refinement) ---
                        # MT5 tick_value is the value of one tick movement in the *profit* currency.
                        # We need to convert it to the *account* currency.
                        'tick_value': None, # Initialize as None, will calculate below
                        'volume_min': mt5_info.volume_min,
                        'volume_step': mt5_info.volume_step,
                        'digits': mt5_info.digits,
                        'spread': mt5_info.spread,
                        'description': mt5_info.description,
                        'currency_profit': mt5_info.currency_profit, # Store profit currency
                        'currency_margin': mt5_info.currency_margin, # Store margin currency (might be useful)
                        'source': 'mt5'
                    }

                    # --- Calculate Tick Value in Account Currency ---
                    try:
                        account_info = mt5.account_info()
                        if not account_info:
                            self.logger.error(f"无法获取账户信息以计算 {symbol} 的 Tick Value。")
                            # info['tick_value'] remains None
                        else:
                            account_currency = account_info.currency
                            profit_currency = mt5_info.currency_profit
                            tick_value_profit_curr = mt5_info.tick_value

                            if tick_value_profit_curr <= 0:
                                self.logger.warning(f"{symbol} 的 MT5 tick_value ({tick_value_profit_curr}) 无效或为零，无法计算。")
                                # info['tick_value'] remains None
                            elif profit_currency == account_currency:
                                # Profit currency is the same as account currency, MT5 value is correct
                                info['tick_value'] = tick_value_profit_curr
                                self.logger.debug(f"Tick value for {symbol} ({profit_currency}) matches account currency ({account_currency}): {info['tick_value']}")
                            else:
                                # Need to convert tick_value_profit_curr from profit_currency to account_currency
                                self.logger.debug(f"需要将 {symbol} 的 Tick Value 从 {profit_currency} 转换为 {account_currency}。")
                                exchange_rate = None
                                rate_symbol_direct = f"{profit_currency}{account_currency}"
                                rate_symbol_inverse = f"{account_currency}{profit_currency}"
                                tick_direct = mt5.symbol_info_tick(rate_symbol_direct)

                                if tick_direct and tick_direct.ask > 0:
                                    exchange_rate = tick_direct.ask # Rate to convert profit_curr TO account_curr
                                    self.logger.debug(f"找到直接汇率 {rate_symbol_direct}: Ask={exchange_rate}")
                                    info['tick_value'] = tick_value_profit_curr * exchange_rate
                                else:
                                    # Try inverse pair
                                    tick_inverse = mt5.symbol_info_tick(rate_symbol_inverse)
                                    if tick_inverse and tick_inverse.bid > 0:
                                        exchange_rate = 1.0 / tick_inverse.bid # Inverse rate
                                        self.logger.debug(f"找到反向汇率 {rate_symbol_inverse}: Bid={tick_inverse.bid}, 使用倒数: {exchange_rate}")
                                        info['tick_value'] = tick_value_profit_curr * exchange_rate
                                    else:
                                        self.logger.warning(f"无法找到 {symbol} Tick Value 转换所需的汇率对 ({rate_symbol_direct} 或 {rate_symbol_inverse})。")
                                        # Cannot accurately calculate, info['tick_value'] remains None
                                        # Optionally, store the unconverted value with a flag?
                                        info['unconverted_tick_value'] = tick_value_profit_curr
                                        info['unconverted_tick_currency'] = profit_currency


                            # Final check and log
                            if info.get('tick_value') is not None:
                                self.logger.info(f"计算得到 {symbol} 的 Tick Value ({account_currency}): {info['tick_value']:.{mt5_info.digits}f}")
                            elif 'unconverted_tick_value' in info:
                                 self.logger.warning(f"未能计算 {symbol} 的 Tick Value ({account_currency})，回退到未转换值: {info['unconverted_tick_value']} {info['unconverted_tick_currency']}")
                            else:
                                 self.logger.error(f"最终未能计算 {symbol} 的有效 Tick Value。")

                    except Exception as calc_e:
                        self.logger.error(f"计算 {symbol} 的 Tick Value 时发生错误: {calc_e}", exc_info=True)
                        # info['tick_value'] remains None if calculation failed

                else:
                    self.logger.warning(f"mt5.symbol_info({symbol}) returned None.")
            except Exception as e:
                self.logger.error(f"Error getting symbol info for {symbol} from MT5: {e}", exc_info=True)

        # 2. Fallback to loaded specs file if MT5 failed or not connected
        if info is None and symbol in self.instrument_specs:
            self.logger.debug(f"Using specs for {symbol} from config file.")
            info = self.instrument_specs[symbol].copy() # Return a copy
            info['source'] = 'config'

        # 3. If still not found
        if info is None:
            self.logger.warning(f"Could not find instrument specifications for symbol: {symbol}")
            return None
            
        # Basic validation
        required_keys = ['contract_size', 'tick_size', 'tick_value', 'volume_min', 'volume_step']
        if not all(key in info and info[key] is not None for key in required_keys):
             self.logger.error(f"Loaded specs for {symbol} from {info.get('source')} are incomplete: {info}")
             return None

        return info

    def _get_hist_filepath(self, symbol: str, timeframe: str) -> Optional[Path]:
        """构造历史数据文件的路径 (使用 get_filepath)。"""
        if not get_filepath:
             self.logger.error("无法获取历史文件路径：get_filepath 函数不可用。")
             return None
        try:
            # Format directory and filename separately
            relative_dir = self.hist_dir_pattern.format(symbol=symbol.upper())
            filename = self.hist_filename_pattern.format(symbol=symbol.upper(), timeframe_lower=timeframe.lower())
            # Combine them into a single relative path for get_filepath
            relative_path = os.path.join(relative_dir, filename)
            # --- Corrected call to get_filepath based on its definition ---
            full_path = get_filepath(str(self.base_data_dir), relative_path, symbol.upper(), timeframe.lower()) # Pass base as string
            # --------------------------------------------------------------
            return full_path
        except Exception as e:
            self.logger.error(f"为 {symbol} {timeframe} 生成历史文件路径时出错: {e}")
            return None

    def _get_rt_filepath(self, symbol: str, timeframe: str) -> Optional[Path]:
         """构造实时数据文件的路径 (使用 get_filepath)。"""
         if not get_filepath:
             self.logger.error("无法获取实时文件路径：get_filepath 函数不可用。")
             return None
         try:
             # Format directory and filename separately
             relative_dir = self.rt_dir_pattern.format(symbol=symbol.upper())
             filename = self.rt_filename_pattern.format(symbol=symbol.upper(), timeframe_lower=timeframe.lower())
             # Combine them into a single relative path for get_filepath
             relative_path = os.path.join(relative_dir, filename)
             # --- Corrected call to get_filepath based on its definition ---
             full_path = get_filepath(str(self.base_data_dir), relative_path, symbol.upper(), timeframe.lower()) # Pass base as string
             # --------------------------------------------------------------
             return full_path
         except Exception as e:
             self.logger.error(f"为 {symbol} {timeframe} 生成实时文件路径时出错: {e}")
             return None

    def load_from_cache(self, symbol: str, timeframe: str, 
                        start_time: Optional[pd.Timestamp] = None, 
                        end_time: Optional[pd.Timestamp] = None) -> Optional[pd.DataFrame]:
        """
        尝试从缓存 (历史数据 CSV 文件) 加载指定品种和时间周期的数据。
        --- 修改: 添加了 start_time 和 end_time 参数以支持读取时过滤 ---

        Args:
            symbol (str): 交易品种代码 (e.g., "EURUSD")。
            timeframe (str): 时间周期 (e.g., "H1", "M15")。
            start_time (Optional[pd.Timestamp]): 开始时间 (时区感知 UTC)，用于过滤。
            end_time (Optional[pd.Timestamp]): 结束时间 (时区感知 UTC)，用于过滤。

        Returns:
            Optional[pd.DataFrame]: OHLCV 数据 (UTC 时间索引)，如果缓存不存在或读取失败则返回 None。
        """
        self.logger.debug(f"[DP.load_from_cache] Args: symbol={symbol}, timeframe={timeframe}, start_time={start_time}, end_time={end_time}")
        filepath = self._get_hist_filepath(symbol, timeframe)
        if filepath is None:
            self.logger.error(f"[DP.load_from_cache] 无法为 {symbol} {timeframe} 获取历史文件路径。")
            return None

        self.logger.debug(f"[DP.load_from_cache] 尝试从以下路径加载缓存 {symbol} {timeframe}: {filepath}")
        if not filepath.exists() or filepath.stat().st_size == 0:
            self.logger.warning(f"[DP.load_from_cache] 历史缓存文件未找到或为空: {filepath}") # Changed to warning
            return None
        self.logger.debug(f"[DP.load_from_cache] 文件存在，大小: {filepath.stat().st_size} bytes.")

        # --- 使用分块读取进行过滤 ---\
        chunk_list = []
        first_chunk_logged = False
        try:
            chunksize = 100000 

            for i, chunk in enumerate(pd.read_csv(
                filepath,
                index_col='time',
                parse_dates=True,
                date_format='%Y-%m-%d %H:%M:%S', 
                dtype={'volume': 'float64'},
                chunksize=chunksize, 
                low_memory=False 
            )):
                # --- 日志精简：移除或注释掉大部分 chunk 处理日志 ---
                # self.logger.debug(f"[DP.load_from_cache] Processing chunk {i} with {len(chunk)} rows.") 
                if not first_chunk_logged and not chunk.empty:
                     self.logger.debug(f"[DP.load_from_cache] 第一个块 (chunk {i}) 原始内容 (前3行):\\n{chunk.head(3)}")
                     self.logger.debug(f"[DP.load_from_cache] 第一个块 (chunk {i}) 原始索引名: {chunk.index.name}, 第一个索引时间: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                     first_chunk_logged = True

                # 1. 确保索引是 DatetimeIndex (保留错误处理和日志)
                if not isinstance(chunk.index, pd.DatetimeIndex):
                     self.logger.warning(f"[DP.load_from_cache] 在 {filepath.name} 的块 {i} 中解析时间索引失败，尝试手动解析。")
                     chunk.index = pd.to_datetime(chunk.index, errors='coerce')
                     chunk = chunk.dropna(axis=0, subset=[chunk.index.name]) 
                     if not isinstance(chunk.index, pd.DatetimeIndex) or chunk.empty:
                          self.logger.error(f"[DP.load_from_cache] 无法解析 {filepath.name} 块 {i} 的时间索引，跳过此块。")
                          continue 
                # self.logger.debug(f"[DP.load_from_cache] Chunk {i} index type after initial parse: {type(chunk.index)}, first timestamp: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                
                # 2. 确保时区是 UTC (保留关键日志)
                original_tz = chunk.index.tz
                if chunk.index.tz is None:
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} index is naive. Localizing to UTC. Original first: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                    try:
                        chunk.index = chunk.index.tz_localize('UTC', ambiguous='infer') 
                        if first_chunk_logged and i == 0 and not chunk.empty: # 只记录第一个块转换后的时间
                             self.logger.debug(f"[DP.load_from_cache] 第一个块 (chunk {i}) 本地化到 UTC 后，第一个索引时间: {chunk.index[0]}")
                    except Exception as tz_err:
                         self.logger.error(f"[DP.load_from_cache] 在块 {i} 中本地化到 UTC 时出错: {tz_err}", exc_info=True)
                         continue # 跳过此块
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} index localized to UTC. New first: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                elif str(original_tz) != 'UTC': # Use str() for robust comparison
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} index is {original_tz}. Converting to UTC. Original first: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                    try:
                        chunk.index = chunk.index.tz_convert('UTC')
                        if first_chunk_logged and i == 0 and not chunk.empty: # 只记录第一个块转换后的时间
                            self.logger.debug(f"[DP.load_from_cache] 第一个块 (chunk {i}) 从 {original_tz} 转换到 UTC 后，第一个索引时间: {chunk.index[0]}")
                    except Exception as tz_err:
                        self.logger.error(f"[DP.load_from_cache] 在块 {i} 中从 {original_tz} 转换到 UTC 时出错: {tz_err}", exc_info=True)
                        continue # 跳过此块
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} index converted to UTC. New first: {chunk.index[0] if len(chunk.index) > 0 else 'N/A'}")
                # else:
                #     self.logger.debug(f"[DP.load_from_cache] Chunk {i} index is already UTC.")
                
                # 3. 应用时间过滤 (保留过滤日志)
                filtered_chunk = chunk
                st_utc, et_utc = None, None # Initialize
                if start_time is not None:
                    st_utc = start_time
                    if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) is None:
                        # self.logger.warning(f"[DP.load_from_cache] 传递给 load_from_cache 的 start_time '{start_time}' 没有时区，假定为 UTC。")
                        st_utc = start_time.tz_localize('UTC')
                    # self.logger.debug(f"[DP.load_from_cache] Filtering chunk {i} with start_time_utc: {st_utc}")
                    filtered_chunk = filtered_chunk[filtered_chunk.index >= st_utc]
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} after start_time filter: {len(filtered_chunk)} rows.")
                
                if end_time is not None:
                    et_utc = end_time
                    if end_time.tzinfo is None or end_time.tzinfo.utcoffset(end_time) is None:
                        # self.logger.warning(f"[DP.load_from_cache] 传递给 load_from_cache 的 end_time '{end_time}' 没有时区，假定为 UTC。")
                        et_utc = end_time.tz_localize('UTC')
                    # self.logger.debug(f"[DP.load_from_cache] Filtering chunk {i} with end_time_utc: {et_utc}")
                    filtered_chunk = filtered_chunk[filtered_chunk.index <= et_utc]
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} after end_time filter: {len(filtered_chunk)} rows.")

                if not filtered_chunk.empty:
                    chunk_list.append(filtered_chunk)
                # else:
                    # self.logger.debug(f"[DP.load_from_cache] Chunk {i} is empty after filtering.")
                
                # 优化：如果块的最后一个时间戳已经超过 end_time，可以停止读取 (保留)
                if end_time is not None and not chunk.empty and chunk.index[-1] > (et_utc if et_utc else end_time.tz_localize('UTC')): 
                    # self.logger.debug(f"[DP.load_from_cache] 块 {i} 的结束时间 {chunk.index[-1]} 已超过 end_time，停止读取 {filepath.name}")
                    break
            
            # --- 保留最终结果的日志 ---
            if not chunk_list:
                 self.logger.warning(f"[DP.load_from_cache] 从 {filepath} 分块读取后，未找到符合时间范围 ({start_time} to {end_time}) 的数据。") 
                 return None

            df = pd.concat(chunk_list)
            # self.logger.debug(f"[DP.load_from_cache] 合并后 {len(df)} 条记录。")

            df.columns = [col.lower() for col in df.columns]
            
            if not df.empty:
                self.logger.info(f"[DP.load_from_cache] 成功从缓存文件 {filepath} 加载并过滤得到 {len(df)} 条记录。数据范围: {df.index.min()} to {df.index.max()} (请求范围: {start_time} to {end_time})。")
            else:
                # 这个警告现在更可能被触发
                self.logger.warning(f"[DP.load_from_cache] 从 {filepath} 加载并过滤后最终 DataFrame 为空 (请求范围: {start_time} to {end_time})。") 
            return df

        except Exception as e:
            self.logger.error(f"[DP.load_from_cache] 从缓存文件 {filepath} 分块读取或过滤数据时发生未预期的错误: {e}", exc_info=True)
            return None

    def load_realtime_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        尝试从实时数据 CSV 文件加载指定品种和时间周期的数据。

        Args:
            symbol (str): 交易品种代码。
            timeframe (str): 时间周期。

        Returns:
            Optional[pd.DataFrame]: OHLCV 数据 (UTC 时间索引)，如果文件不存在或读取失败则返回 None。
        """
        filepath = self._get_rt_filepath(symbol, timeframe)
        if filepath is None:
            self.logger.error(f"无法为 {symbol} {timeframe} 获取实时文件路径。")
            return None

        self.logger.debug(f"尝试从以下路径加载实时数据 {symbol} {timeframe}: {filepath}")
        if filepath.exists() and filepath.stat().st_size > 0:
            try:
                # Use consistent reading parameters with load_from_cache
                df = pd.read_csv(
                     filepath,
                     index_col='time',
                     parse_dates=True,
                     date_format='%Y-%m-%d %H:%M:%S', # Specify format
                     dtype={'volume': 'float64'}
                 )

                if not isinstance(df.index, pd.DatetimeIndex):
                     self.logger.error(f"在 {filepath} 中解析时间索引失败。")
                     df.index = pd.to_datetime(df.index, errors='coerce')
                     df = df.dropna(axis=0, subset=[df.index.name])
                     if not isinstance(df.index, pd.DatetimeIndex):
                          self.logger.error(f"手动解析时间索引也失败了 {filepath}。")
                          return None

                # --- Convert to UTC Time ---
                if df.index.tz is None:
                    self.logger.debug(f"本地化 naive 时间索引为 UTC for {filepath.name}")
                    df.index = df.index.tz_localize('UTC')
                elif df.index.tz.zone != 'UTC':
                    self.logger.debug(f"将时区从 {df.index.tz} 转换为 UTC for {filepath.name}")
                    df.index = df.index.tz_convert('UTC')
                else:
                    self.logger.debug(f"时间索引已是 UTC for {filepath.name}")
                # --- End Conversion ---

                df.columns = [col.lower() for col in df.columns]

                self.logger.debug(f"成功从实时文件 {filepath} 加载并确保为 UTC 时间 {len(df)} 条记录。")
                return df
            except Exception as e:
                self.logger.error(f"从实时文件 {filepath} 读取或解析数据时出错: {e}", exc_info=True)
                return None
        elif not filepath.exists():
             self.logger.debug(f"实时数据文件未找到: {filepath}")
             return None
        else:
             self.logger.debug(f"实时数据文件为空: {filepath}")
             return None

    def get_combined_prices(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        获取指定品种和时间周期的合并后的历史和实时价格数据。
        实时数据会覆盖历史数据中重复的时间点。
        返回的数据索引为 UTC 时间。

        Args:
            symbol (str): 交易品种代码。
            timeframe (str): 时间周期。

        Returns:
            Optional[pd.DataFrame]: 合并、去重、排序后的 OHLCV 数据 (UTC 时间索引)。
        """
        self.logger.debug(f"获取 {symbol} {timeframe} 的合并价格数据...")
        hist_df = self.load_from_cache(symbol, timeframe) # 已转换为 UTC 时间
        rt_df = self.load_realtime_data(symbol, timeframe)   # 已转换为 UTC 时间

        if hist_df is None and rt_df is None:
            self.logger.warning(f"未能加载 {symbol} {timeframe} 的历史或实时数据。")
            return None
        elif hist_df is not None and rt_df is None:
            self.logger.debug(f"仅找到 {symbol} {timeframe} 的历史数据。")
            return hist_df.sort_index() # Index is already UTC time
        elif hist_df is None and rt_df is not None:
             self.logger.debug(f"仅找到 {symbol} {timeframe} 的实时数据。")
             return rt_df.sort_index() # Index is already UTC time
        else: # Both exist
            try:
                 # Ensure both have the same timezone (should be UTC)
                 if hist_df.index.tz != rt_df.index.tz:
                     self.logger.warning(f"合并时发现历史 ({hist_df.index.tz}) 和实时 ({rt_df.index.tz}) 时区不匹配 for {symbol} {timeframe}. 强制转换为 UTC.")
                     # This shouldn't happen if load_* methods work correctly, but as a safeguard:
                     hist_df.index = hist_df.index.tz_convert('UTC')
                     rt_df.index = rt_df.index.tz_convert('UTC')

                 combined = pd.concat([hist_df, rt_df])
                 # Remove duplicates based on index (time), keeping the last (realtime)
                 combined = combined[~combined.index.duplicated(keep='last')]
                 combined = combined.sort_index()
                 self.logger.debug(f"成功合并 {symbol} {timeframe} 的历史 ({len(hist_df)}) 和实时 ({len(rt_df)}) 数据，结果: {len(combined)} 条 (UTC 时间索引)。")
                 return combined
            except Exception as e:
                 self.logger.error(f"合并 {symbol} {timeframe} 的历史和实时数据时出错: {e}", exc_info=True)
                 return None # Return None on merge error

    def get_historical_prices(self, symbol: str, start_time: pd.Timestamp, end_time: pd.Timestamp, timeframe: str) -> Optional[pd.DataFrame]:
        """
        获取指定时间范围内的历史价格数据 (UTC 时间索引)。
        会合并历史和实时缓存以获取最完整的数据。
        --- 修改: 将 start_time 和 end_time 传递给 load_from_cache ---

        Args:
            symbol (str): 交易品种。
            start_time (pd.Timestamp): 开始时间 (时区感知)。
            end_time (pd.Timestamp): 结束时间 (时区感知)。
            timeframe (str): 时间周期。

        Returns:
            Optional[pd.DataFrame]: 指定范围内的 OHLCV 数据 (UTC 时间索引)。
        """
        self.logger.debug(f"[DP.get_historical_prices] Args: symbol={symbol}, timeframe={timeframe}, start_time={start_time}, end_time={end_time}")

        # 确保输入的时间是 UTC 时区感知的
        start_time_utc = start_time
        if start_time.tzinfo is None:
            self.logger.warning(f"[DP.get_historical_prices] 接收到的 start_time '{start_time}' 没有时区，假定为 UTC。")
            start_time_utc = start_time.tz_localize('UTC')
        elif start_time.tzinfo != datetime.timezone.utc:
            self.logger.debug(f"[DP.get_historical_prices] start_time 时区为 {start_time.tzinfo}, 将转换为 UTC。")
            start_time_utc = start_time.tz_convert('UTC')
        
        end_time_utc = end_time
        if end_time.tzinfo is None:
            self.logger.warning(f"[DP.get_historical_prices] 接收到的 end_time '{end_time}' 没有时区，假定为 UTC。")
            end_time_utc = end_time.tz_localize('UTC')
        elif end_time.tzinfo != datetime.timezone.utc:
            self.logger.debug(f"[DP.get_historical_prices] end_time 时区为 {end_time.tzinfo}, 将转换为 UTC。")
            end_time_utc = end_time.tz_convert('UTC')
        
        self.logger.debug(f"[DP.get_historical_prices] UTC range: start_time_utc={start_time_utc}, end_time_utc={end_time_utc}")

        # 1. 尝试从 MT5 获取 (如果连接)
        data_df: Optional[pd.DataFrame] = None
        if self.mt5_connected:
            self.logger.info(f"[DP.get_historical_prices] MT5 已连接。尝试从 MT5 获取 {symbol} {timeframe} 数据。")
            try:
                # MT5-specific data fetching logic needs to be here or called from here
                # Assuming mt5_get_historical_data is a method that handles this.
                # For demonstration, let's assume it's part of this method for now.
                mt5_timeframe = self._map_timeframe_to_mt5(timeframe)
                if not mt5_timeframe:
                    self.logger.error(f"无法将时间周期 {timeframe} 映射到 MT5周期。")
                    # Fallback to cache will happen if data_df remains None
                else:
                    ticks = mt5.copy_rates_range(symbol, mt5_timeframe, start_time_utc, end_time_utc)
                    if ticks is None or len(ticks) == 0:
                        self.logger.warning(f"mt5.copy_rates_range for {symbol} {timeframe} 返回空数据或None。错误: {mt5.last_error()}")
                        # data_df remains None, will fallback to cache
                    else:
                        data_df = pd.DataFrame(ticks)
                        # Convert 'time' (Unix epoch seconds) to UTC datetime objects
                        data_df['time'] = pd.to_datetime(data_df['time'], unit='s', utc=True)
                        self.logger.info(f"从MT5获取的 {symbol} {timeframe} 原始时间已转换为UTC (来自epoch): {data_df['time'].iloc[0] if not data_df.empty else 'N/A'}")

                        # The 'time' column is now correct UTC.
                        # The previous logic for broker_timezone conversion could lead to errors if broker_tz was not UTC,
                        # as it would convert correct UTC to local, then strip tz, then incorrectly re-label as UTC.
                        # For now, we will use the direct UTC conversion.
                        # If platform-specific time is needed for display/logging, it should be a separate column or handled differently.

                        # Rename columns to standard names (open, high, low, close, volume, timestamp)
                        # Ensure all expected columns are present, filling with NaN if necessary
                        expected_ohlcv_cols = ['open', 'high', 'low', 'close', 'tick_volume'] # MT5 names
                        standard_cols_map = {
                            'time': 'timestamp',
                            'tick_volume': 'volume' 
                            # open, high, low, close usually match
                        }
                        # Select and rename existing columns
                        data_df = data_df[[col for col in data_df.columns if col in standard_cols_map or col in expected_ohlcv_cols]].rename(columns=standard_cols_map)
                        
                        # Ensure standard OHLCV columns exist, even if they were not in standard_cols_map or expected_ohlcv_cols
                        # This is more of a safeguard for consistent structure.
                        for std_col in ['open', 'high', 'low', 'close', 'volume']:
                            if std_col not in data_df.columns and std_col not in standard_cols_map.values(): # Check if not already mapped
                                if std_col in ticks.dtype.names: # If it was in original ticks but not mapped
                                     data_df[std_col] = pd.Series(ticks[std_col], index=data_df.index)
                                # else: # If truly missing, it will not be added here by default unless specific logic is needed
                                #     data_df[std_col] = pd.NA 

                        if 'timestamp' in data_df.columns:
                            data_df = data_df.set_index('timestamp')
                        else:
                            self.logger.error(f"MT5数据处理后缺少'timestamp'列 for {symbol} {timeframe}.")
                            data_df = None # Signal error

                # This is where data_df would be populated if MT5 call was successful
                # The method mt5_get_historical_data was a placeholder in the original code structure.
                # I've integrated the core MT5 fetching logic directly above for clarity.

                if data_df is not None and not data_df.empty:
                    self.logger.info(f"[DP.get_historical_prices] 从 MT5 获取到 {len(data_df)} 条 {symbol} {timeframe} 数据 (已确保UTC)。")
                    # MT5 数据应该是 UTC，并已处理好
                    return data_df
            except Exception as mt5_e:
                self.logger.error(f"[DP.get_historical_prices] 从 MT5 获取 {symbol} {timeframe} 数据时出错: {mt5_e}。将尝试从缓存加载。", exc_info=True)
                data_df = None # Ensure it's None to fallback
        else:
            self.logger.info(f"[DP.get_historical_prices] MT5 未连接。将从缓存加载 {symbol} {timeframe} 数据。")

        # 2. 如果 MT5 失败或未连接，从缓存加载
        # (data_df is None or data_df.empty) implies we need to load from cache
        if data_df is None or data_df.empty: # Check for empty df as well
            self.logger.debug(f"[DP.get_historical_prices] 调用 load_from_cache for {symbol} {timeframe} with start={start_time_utc}, end={end_time_utc}")
            data_df = self.load_from_cache(symbol, timeframe, start_time_utc, end_time_utc)
            if data_df is not None and not data_df.empty:
                 self.logger.info(f"[DP.get_historical_prices] 从缓存成功加载 {len(data_df)} 条 {symbol} {timeframe} 数据。")
            else:
                 self.logger.warning(f"[DP.get_historical_prices] 从缓存也未能加载 {symbol} {timeframe} 数据 (或为空)。")
                 return None # Explicitly return None if cache is also empty/None

        # 此处 data_df 要么是来自 MT5 的有效数据，要么是来自缓存的有效数据，要么是 None
        if data_df is None or data_df.empty:
            self.logger.error(f"[DP.get_historical_prices] 最终未能获取 {symbol} {timeframe} 在 {start_time_utc} 到 {end_time_utc} 范围内的数据。")
            return None
        
        # 最后确保数据在请求的时间范围内 (MT5 可能返回稍多数据，缓存已在内部过滤)
        # 并且索引是 UTC 时间 (load_from_cache 和 mt5_get_historical_data 应已保证)
        # final_df = data_df[(data_df.index >= start_time_utc) & (data_df.index <= end_time_utc)] # Redundant if cache filter works
        final_df = data_df # Trust internal filtering of load_from_cache and MT5 precise fetching
        
        if final_df.empty:
            self.logger.warning(f"[DP.get_historical_prices] 应用最终时间范围过滤后，{symbol} {timeframe} 数据为空。")
            return None

        self.logger.info(f"[DP.get_historical_prices] 最终返回 {len(final_df)} 条 {symbol} {timeframe} 数据。")
        return final_df

    def get_latest_prices(self, symbols: List[str], timeframe: str) -> Optional[Dict[str, pd.Series]]:
        """
        获取指定品种列表和 *指定时间周期* 的最新可用价格数据 (该时间周期合并数据的最后一行)。
        返回的数据 Series 的 name (时间戳) 是 UTC 时间。

        Args:
            symbols (List[str]): 需要获取最新价格的品种列表。
            timeframe (str): *必须* 指定需要哪个时间周期的最新数据 (e.g., 'M1', 'H1')。

        Returns:
            Optional[Dict[str, pd.Series]]: 字典，键为品种名称，值为指定时间周期最新的价格信息 Series (name 为 UTC 时间戳)。
                                             如果某个品种无法获取该周期数据，则字典中不包含该键。
                                             如果所有品种都无法获取，则返回 None。
                                             如果 timeframe 未提供，返回 None 并记录错误。
        """
        latest_data = {}
        # timeframe 现在是必需参数
        if not timeframe:
            self.logger.error("'get_latest_prices' 必须提供 'timeframe' 参数。")
            return None

        if not symbols:
             self.logger.warning("调用 'get_latest_prices' 时未提供品种列表。")
             return None

        self.logger.debug(f"尝试获取 {len(symbols)} 个品种在 timeframe '{timeframe}' 的最新价格...")

        for symbol in symbols:
            # 获取指定 timeframe 的合并数据 (Index is UTC Time)
            combined_data = self.get_combined_prices(symbol, timeframe)
            if combined_data is not None and not combined_data.empty:
                latest_row = combined_data.iloc[-1]
                latest_data[symbol] = latest_row
                self.logger.debug(f"找到 {symbol} ({timeframe}) 的最新价格数据，时间戳 (UTC): {latest_row.name}")
            else:
                 self.logger.warning(f"未能找到 {symbol} ({timeframe}) 的合并价格数据以获取最新价格。")

        return latest_data if latest_data else None

    def resample_data(self, data: pd.DataFrame, target_timeframe: str ='15Min') -> Optional[pd.DataFrame]:
        """将传入的 OHLCV DataFrame 重采样到目标时间周期。输入数据的索引应为 UTC 时间。"""
        if data is None or data.empty:
            self.logger.debug("用于重采样的数据为空。")
            return None
        if not isinstance(data.index, pd.DatetimeIndex):
            self.logger.error("数据索引不是 DatetimeIndex，无法进行重采样。")
            return None # Or raise error?

        # Ensure index is UTC Time (UTC) before resampling
        target_tz = 'UTC'
        if data.index.tz is None:
            self.logger.warning("Resample input data index is timezone-naive. Assuming it represents UTC time and localizing.")
            data.index = data.index.tz_localize(target_tz)
        elif data.index.tz.zone != target_tz:
            self.logger.warning(f"Resample input data index timezone is {data.index.tz}. Converting to {target_tz}.")
            data.index = data.index.tz_convert(target_tz)

        try:
            # 定义聚合规则
            agg_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            }
            # 如果存在 volume 列，也进行聚合
            if 'volume' in data.columns:
                 agg_dict['volume'] = 'sum'

            self.logger.debug(f"开始将数据重采样到 {target_timeframe} (基于 UTC 索引)...")
            # Resampling preserves the original timezone
            resampled_data = data.resample(target_timeframe).agg(agg_dict)
            # 删除完全由 NaN 构成的行 (resample 可能引入)
            resampled_data = resampled_data.dropna(how='all')
            self.logger.info(f"数据已成功重采样到 {target_timeframe} (UTC 索引)，生成 {len(resampled_data)} 条记录。")
            return resampled_data
        except ValueError as ve:
            # Handle specific error for unknown resampling frequency
            self.logger.error(f"重采样到 '{target_timeframe}' 时出错：无效的时间周期字符串？ {ve}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"将数据重采样到 {target_timeframe} 时发生未知错误: {e}", exc_info=True)
            return None

# ----------------------
# 统一数据提供者门面
# ----------------------
class DataProvider:
    """
    统一的数据提供者接口门面。
    策略代码应通过此类访问数据。
    """
    def __init__(self, config: DictConfig):
        """初始化所有底层数据提供者。"""
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__) # Get instance logger
        self.economic_provider = EconomicCalendarProvider(config)
        self.market_provider = MarketDataProvider(config)
        self.logger.info("DataProvider facade initialized.")

    def get_filtered_events(self, live: bool = True, **kwargs) -> Optional[pd.DataFrame]:
        """获取已过滤的财经日历事件。"""
        return self.economic_provider.get_filtered_events(live, **kwargs)

    def get_upcoming_events(self, lookahead_window: str = "24h") -> Optional[pd.DataFrame]:
        """获取未来的财经日历事件。"""
        return self.economic_provider.get_upcoming_events(lookahead_window)

    def get_historical_prices(self, symbol: str, start_time: pd.Timestamp, end_time: pd.Timestamp, timeframe: str) -> Optional[pd.DataFrame]:
        """获取历史市场价格数据 (UTC 时间索引)。"""
        return self.market_provider.get_historical_prices(symbol, start_time, end_time, timeframe)

    def get_latest_prices(self, symbols: List[str], timeframe: str) -> Optional[Dict[str, pd.Series]]:
        """获取最新的市场价格数据 (Series name 为 UTC 时间戳)。"""
        return self.market_provider.get_latest_prices(symbols, timeframe)

    def resample_data(self, data: pd.DataFrame, timeframe: str ='15Min') -> Optional[pd.DataFrame]:
        """重采样市场数据 (输入和输出均为 UTC 时间索引)。"""
        # Delegate directly to market_provider as it holds the resampling logic
        return self.market_provider.resample_data(data, timeframe)