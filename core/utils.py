import os
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import pytz
from omegaconf import OmegaConf, DictConfig
import time
import subprocess
import platform

# Attempt to import MetaTrader5, handle failure gracefully
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError as e:
    print(f"DEBUG: Failed to import MetaTrader5 in core/utils.py: {e}")
    mt5 = None
    MT5_AVAILABLE = False

# --- 获取项目根目录 (utils.py 现在在 core/ 目录下) ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_app_config(module_config_rel_path: str) -> DictConfig:
    """
    加载共享配置 (config/common.yaml) 和指定模块的特定配置，
    并将它们合并成一个 OmegaConf 对象，确保模块配置覆盖共享配置。

    Args:
        module_config_rel_path (str): 模块配置文件的相对路径 (相对于项目根目录),
                                      例如 "backtesting/config/backtest.yaml"。

    Returns:
        DictConfig: 合并后的 OmegaConf 配置对象。
                    如果文件加载失败会抛出异常。
    """
    common_conf_path = PROJECT_ROOT / 'config' / 'common.yaml'
    module_conf_path = PROJECT_ROOT / module_config_rel_path
    logger = logging.getLogger('ConfigLoader')

    base_conf = OmegaConf.create({}) # Start with empty
    module_conf = OmegaConf.create({}) # Start with empty

    # 1. 加载共享配置 common.yaml (如果存在)
    if common_conf_path.is_file():
        try:
            base_conf = OmegaConf.load(common_conf_path)
            logger.info(f"已加载共享配置: {common_conf_path}")
            # --- 调试：检查 base_conf --- 
            symbols_in_base = OmegaConf.select(base_conf, 'backtest.engine.symbols', default='Base中未找到')
            logger.info(f"[调试] 加载 base_conf 后，base_conf.backtest.engine.symbols 为: {symbols_in_base}")
            # ----------------------------
        except Exception as e:
            logger.error(f"加载共享配置 {common_conf_path} 失败: {e}")
            raise # 共享配置通常是必需的
    else:
        logger.warning(f"未找到共享配置文件: {common_conf_path}，将使用空基础配置。")

    # 2. 加载模块特定配置 module_config_rel_path (如果存在)
    if module_conf_path.is_file():
        try:
            module_conf = OmegaConf.load(module_conf_path)
            logger.info(f"已加载模块配置: {module_conf_path}")
            # --- 添加调试：检查模块配置加载后 --- 
            try:
                 symbols_in_module = OmegaConf.select(module_conf, 'backtest.engine.symbols', default='模块配置中未找到')
                 logger.info(f"[调试] 加载模块配置后，module_conf.backtest.engine.symbols 为: {symbols_in_module}")
            except Exception as module_check_e:
                 logger.error(f"[调试] 检查模块配置时出错: {module_check_e}")
            # -------------------------------------
        except Exception as e:
             logger.error(f"加载模块配置文件 {module_conf_path} 失败: {e}")
             raise
    else:
        logger.error(f"指定的模块配置文件未找到: {module_conf_path}")
        raise FileNotFoundError(f"Module configuration file not found: {module_conf_path}")

    # 3. 合并配置：模块配置 (module_conf) 覆盖 基础配置 (base_conf)
    final_conf = OmegaConf.merge(base_conf, module_conf)
    logger.info(f"已将模块配置合并到共享配置之上 (模块优先)。")
    # --- 调试：检查合并后 --- 
    symbols_after_merge = OmegaConf.select(final_conf, 'backtest.engine.symbols', default='Merge后未找到')
    logger.info(f"[调试] 合并 final_conf 后，final_conf.backtest.engine.symbols 为: {symbols_after_merge}")
    # ------------------------

    # 4. 解析变量插值 (例如 ${paths.data_dir})
    try:
        OmegaConf.resolve(final_conf)
        logger.info("配置变量插值已解析。")
        # --- 调试：检查解析插值后 --- 
        symbols_after_resolve = OmegaConf.select(final_conf, 'backtest.engine.symbols', default='Resolve后未找到')
        logger.info(f"[调试] 解析插值后，final_conf.backtest.engine.symbols 为: {symbols_after_resolve}")
        # ---------------------------
    except Exception as resolve_e:
        logger.error(f"配置变量插值解析失败: {resolve_e}")

    # --- 最终检查 (移到最后) --- 
    # try:
    #     symbols_check = OmegaConf.select(final_conf, 'backtest.engine.symbols', default='检查失败或未找到')
    #     logger.info(f"[调试] load_app_config 函数返回前，最终配置中的 backtest.engine.symbols 为: {symbols_check}")
    # except Exception as check_e:
    #      logger.error(f"[调试] 检查最终配置时出错: {check_e}")
    # -------------------------------------------------

    # 将项目根路径添加到配置中
    final_conf.project_root = str(PROJECT_ROOT)
    logger.info(f"项目根路径已添加到配置中: {final_conf.project_root}")

    return final_conf

def get_absolute_path(config: DictConfig, path_key: str) -> Optional[Path]:
    """
    根据配置键从 OmegaConf 配置对象中获取路径，并计算其绝对路径。

    Args:
        config (DictConfig): 已加载并合并的 OmegaConf 配置对象。
        path_key (str): 要在配置中查找的路径键 (例如 'economic_calendar.paths.raw_history_dir')。

    Returns:
        Optional[Path]: 计算出的绝对路径 Path 对象，如果路径键无效或解析失败则返回 None。
    """
    logger = logging.getLogger('PathResolver')
    try:
        # 从 common 配置获取基础数据目录
        base_data_dir_rel = OmegaConf.select(config, "paths.data_dir", default="data")
        # 获取指定键的相对路径
        relative_path_str = OmegaConf.select(config, path_key)

        if relative_path_str is None:
            logger.error(f"配置键 '{path_key}' 未找到或值为 null。")
            return None

        # PROJECT_ROOT 是在此 utils 文件顶部定义的 Path 对象
        absolute_path = PROJECT_ROOT / base_data_dir_rel / relative_path_str
        return absolute_path.resolve() # 解析为规范化的绝对路径

    except Exception as e:
        logger.error(f"解析配置路径键 '{path_key}' 时出错: {e}", exc_info=True)
        return None

def setup_logging(log_config: DictConfig, log_filename: str, logger_name: str = 'MT5Updater') -> logging.Logger:
    """Sets up the logging system using OmegaConf config."""
    logger = logging.getLogger(logger_name)
    try:
        # --- 显式计算项目根目录 --- 
        # 不再依赖顶层的 PROJECT_ROOT 全局变量
        current_file_path = Path(__file__).resolve()
        project_root_inside_func = current_file_path.parents[1]
        # ---------------------------

        # 从 common.yaml 获取基础 log_dir
        # log_dir = str(PROJECT_ROOT / log_config.get('log_dir', 'logs')) # Old way
        log_dir = str(project_root_inside_func / log_config.get('log_dir', 'logs')) # Use calculated path
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / log_filename

        log_level_str = log_config.get('level', 'INFO')
        level = getattr(logging, log_level_str.upper(), logging.INFO)

        if not logger.handlers or logger.level != level:
             if logger.handlers:
                 for handler in logger.handlers[:]:
                     logger.removeHandler(handler)
                     handler.close()

             logger.setLevel(level)
             # --- 修改日志格式，加入 logger 名称 --- 
             # log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s') # 旧格式
             default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s' # 保留原始格式作为默认
             log_format = log_config.get('format', default_format)
             # 确保 %(name)s 总是存在于格式中，除非用户在配置中故意删除了它
             if '%(name)s' not in log_format:
                  # 在开头加入 logger 名称，如果它不存在
                  log_format = f'%(asctime)s - [%(name)s] - %(levelname)s - %(message)s' 
             # ---------------------------------------
             formatter = logging.Formatter(log_format)

             # File Handler
             try:
                 fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
                 fh.setFormatter(formatter)
                 logger.addHandler(fh)
             except Exception as e:
                  print(f"ERROR: Failed to create file handler for {log_file}: {e}")

             # Stream Handler (Console)
             if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
                 sh = logging.StreamHandler(sys.stdout)
                 sh.setFormatter(formatter)
                 logger.addHandler(sh)

        logger.propagate = False
        return logger
    except Exception as e:
        print(f"ERROR: Failed to set up logging: {e}")
        # Fallback basic config
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logger = logging.getLogger(f'{logger_name}_Fallback')
        logger.error(f"Logging setup failed: {e}", exc_info=True)
        return logger

def parse_timeframes(timeframes_str: List[str], logger: logging.Logger) -> Dict[str, Any]:
    """Converts timeframe strings to MT5 constants."""
    if not MT5_AVAILABLE or mt5 is None:
        logger.error("MetaTrader5 library is not available, cannot parse timeframes.")
        return {}

    mapping = {
        'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1, 'MN1': mt5.TIMEFRAME_MN1
    }
    parsed = {}
    if not timeframes_str: return parsed
    for tf_str in timeframes_str:
        if not isinstance(tf_str, str):
             logger.warning(f"Invalid type for timeframe in config: {tf_str}. Skipping.")
             continue
        tf_upper = tf_str.upper()
        if tf_upper in mapping:
            parsed[tf_upper] = mapping[tf_upper]
        else:
            logger.warning(f"Unsupported timeframe string found in config: '{tf_str}'. Skipping.")
    return parsed

def _is_mt5_process_running(executable_name: str, logger: logging.Logger) -> bool:
    """Checks if the MT5 process with the given executable name is running (Windows)."""
    if platform.system() != "Windows":
        logger.warning("MT5 process check is only implemented for Windows.")
        return True # Assume running on other platforms to avoid blocking

    try:
        # 使用 tasklist 命令查找进程
        command = f'tasklist /FI "IMAGENAME eq {executable_name}"'
        # 使用 check=True 会在命令失败时抛出 CalledProcessError
        # 使用 capture_output=True 捕获输出
        # 使用 text=True 将输出解码为文本
        # 使用 creationflags=subprocess.CREATE_NO_WINDOW 避免弹出控制台窗口
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
        # 检查输出中是否包含可执行文件名
        output = result.stdout.lower()
        if executable_name.lower() in output:
            logger.debug(f"MT5 process ({executable_name}) found running.")
            return True
        else:
            logger.debug(f"MT5 process ({executable_name}) not found running via tasklist output.")
            return False
    except subprocess.CalledProcessError as e:
        # 如果 tasklist 找不到进程，它通常会返回非零退出码，这里会捕获
        logger.debug(f"tasklist command indicates process {executable_name} not running (exit code {e.returncode}).")
        return False
    except FileNotFoundError:
        logger.error("Failed to run 'tasklist'. Ensure it's in the system PATH.")
        return False # Cannot check, assume not running? Or maybe return True? Let's assume false.
    except Exception as e:
        logger.error(f"Error checking MT5 process status for {executable_name}: {e}", exc_info=True)
        return False # Assume not running on error

def initialize_mt5(logger: logging.Logger, mt5_config: DictConfig) -> bool:
    """Initializes the MT5 connection. Attempts to start MT5 if not running."""
    if not MT5_AVAILABLE or mt5 is None:
        logger.error("Skipping MT5 initialization: MetaTrader5 library not available.")
        return False

    logger.info("Initializing MT5 connection...")
    
    # 获取配置中指定的MT5终端路径
    mt5_path = mt5_config.get('terminal_path')
    mt5_executable_name = None # 用于进程检查
    
    # 如果指定的路径不存在，尝试自动查找MT5终端路径
    if mt5_path:
        path_obj = Path(mt5_path)
        if path_obj.exists() and path_obj.is_file():
            mt5_executable_name = path_obj.name # 获取文件名 (e.g., terminal64.exe)
        else:
            logger.warning(f"指定的MT5终端路径不存在: {mt5_path}")
            mt5_path = None
    
    # 自动查找MT5终端路径
    if not mt5_path:
        logger.info("正在尝试自动查找MT5终端路径...")
        possible_paths = [
            # EBC路径
            "C:/Program Files/EBC Financial Group Cayman MT5 Terminal/terminal64.exe",
            "C:/Program Files/EBC Financial Group Cayman MT5 Terminal/terminal.exe",
            # 标准MetaTrader5路径
            "C:/Program Files/MetaTrader 5/terminal64.exe",
            "C:/Program Files/MetaTrader 5/terminal.exe",
            # 其他可能路径
            "C:/Program Files (x86)/MetaTrader 5/terminal.exe",
            "D:/Program Files/MetaTrader 5/terminal64.exe"
        ]
        
        for path in possible_paths:
            path_obj = Path(path)
            if path_obj.exists():
                mt5_path = str(path_obj) # Use string representation
                mt5_executable_name = path_obj.name # 获取文件名
                logger.info(f"找到MT5终端路径: {mt5_path}")
                break
                
        if not mt5_path:
            logger.warning("未找到MT5终端路径，将尝试不指定路径初始化，并且无法自动启动MT5。")
            # 如果没有路径，无法检查进程或启动它，直接进行连接尝试

    # --- 修改：在启动前检查进程 ---
    mt5_is_running = False
    if mt5_executable_name and platform.system() == "Windows":
        logger.info(f"检查 MT5 进程 ({mt5_executable_name}) 是否正在运行...")
        mt5_is_running = _is_mt5_process_running(mt5_executable_name, logger)
        if mt5_is_running:
            logger.info(f"MT5 进程 ({mt5_executable_name}) 已在运行。将直接尝试连接。")
        else:
            logger.info(f"MT5 进程 ({mt5_executable_name}) 未运行。将尝试启动它。")
    elif platform.system() != "Windows":
        logger.warning("非 Windows 系统，无法检查 MT5 进程状态，将直接尝试连接。")
        # 在非 Windows 系统上，我们通常假设无法/不需要启动它，直接连接
        mt5_is_running = True # 假设它 '运行中' 以跳过启动步骤

    # --- 仅在 MT5 未运行时尝试启动 ---
    if not mt5_is_running and mt5_path:
        logger.info(f"尝试启动MT5: {mt5_path}")
        try:
            # 使用 Popen 在后台启动，不阻塞
            subprocess.Popen([mt5_path])
            # 等待一段时间让MT5启动
            startup_wait_time = mt5_config.get('startup_wait_time', 10) # 从配置获取等待时间，默认10秒
            logger.info(f"等待 {startup_wait_time} 秒让MT5启动...")
            time.sleep(startup_wait_time)
        except FileNotFoundError:
            logger.error(f"启动MT5失败: 文件未找到 {mt5_path}")
            return False
        except Exception as e:
            logger.error(f"启动MT5时发生错误: {e}", exc_info=True)
            return False
    # -----------------------------------

    # --- 尝试连接 MT5 ---
    login = mt5_config.get('login')
    # 安全地获取密码，优先从环境变量获取
    password = os.getenv('MT5_PASSWORD') or mt5_config.get('password') or ""
    server = mt5_config.get('server')
    timeout = mt5_config.get('timeout', 60000) # 毫秒

    if not login or not server: # 密码可以是空字符串
        logger.error("MT5 配置缺少 login 或 server 信息。")
        return False

    logger.info(f"尝试使用 Login={login}, Server={server} 连接到 MT5...")
    try:
        initialized = mt5.initialize(
            path=mt5_path, # 即使是连接已运行的实例，也可能需要路径来加载库
            login=int(login),
            password=password,
            server=server,
            timeout=int(timeout)
        )
        if initialized:
            logger.info("MT5 初始化成功!")
            acc_info = mt5.account_info()
            if acc_info:
                 logger.info(f"连接到账户: {acc_info.name}, 登录名: {acc_info.login}, 服务器: {acc_info.server}")
            else:
                 logger.warning("无法获取账户信息，但初始化成功。")
            return True
        else:
            error_code = mt5.last_error()
            logger.error(f"MT5 初始化失败。错误代码: {error_code}")
            # 可以根据 error_code 提供更详细的错误信息
            if error_code[0] == -10004: # 无效密码或账户
                 logger.error("MT5 错误: 授权失败 (无效的账户、密码或服务器)。请检查 common.yaml 中的 execution.mt5 配置以及 MT5_PASSWORD 环境变量。")
            elif error_code[0] == -10006: # 连接超时
                 logger.error("MT5 错误: 连接超时。请检查网络连接和服务器名称。")
            # ... 其他错误代码处理
            return False
    except Exception as e:
        logger.error(f"MT5 初始化过程中发生异常: {e}", exc_info=True)
        return False

def shutdown_mt5(logger: logging.Logger):
    """Shuts down the MT5 connection."""
    if not MT5_AVAILABLE or mt5 is None:
        logger.debug("Skipping MT5 shutdown: MetaTrader5 library not available.")
        return
    
    try:
        mt5.shutdown()
        logger.info("MT5 connection closed.")
    except Exception as e:
        logger.error(f"Error during MT5 shutdown: {e}")

def get_filepath(base_data_dir: str, relative_path_pattern: str, symbol: str, timeframe: str) -> Path:
    """Constructs a filepath based on template and parameters."""
    # 使用字符串模板替换
    relative_path = relative_path_pattern.format(
        symbol=symbol.upper(),
        symbol_lower=symbol.lower(),
        timeframe=timeframe.lower(),
        timeframe_lower=timeframe.lower(),
        timeframe_upper=timeframe.upper(),
        SYMBOL=symbol.upper(),
        TIMEFRAME=timeframe.upper()
    )
    
    # 确保基础目录存在
    full_path = Path(base_data_dir) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    return full_path

def get_utc_timezone() -> pytz.BaseTzInfo:
    """Returns the UTC timezone."""
    return pytz.UTC