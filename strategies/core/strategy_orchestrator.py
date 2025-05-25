import importlib
import pkgutil
import inspect
import time
import pandas as pd
from .strategy_base import StrategyBase
# 假设数据提供者和执行引擎从外部初始化并传入
# from .data_providers import DataProvider # 需要整合或定义
# from strategies.live.execution_engine import ExecutionEngine # 需要定义
import logging # 保留导入
from core.utils import setup_logging, load_app_config # 导入需要的工具
from omegaconf import OmegaConf, DictConfig
from typing import Optional, Dict, List, Any
from datetime import datetime
from .risk_manager import RiskManagerBase, get_risk_manager # 导入风险管理器

class StrategyOrchestrator:
    """
    策略调度器。
    负责动态加载、配置和按计划运行所有已启用的策略。
    """
    def __init__(self, config: DictConfig, data_provider: Any, execution_engine: Any):
        """
        初始化调度器。

        Args:
            config (DictConfig): 全局合并后的配置对象。
            data_provider (Any): 已初始化的数据提供者实例。
            execution_engine (Any): 已初始化的执行引擎实例。
        """
        self.config = config
        self.data_provider = data_provider
        self.execution_engine = execution_engine
        self.risk_manager: Optional[RiskManagerBase] = None # 初始化为 None
        self.strategies: List[StrategyBase] = []
        self.running = False

        # 设置日志
        log_filename = OmegaConf.select(config, "logging.orchestrator_log_filename", default="strategy_orchestrator.log")
        # 使用 logger_name='StrategyOrchestrator' 保持一致性
        self.logger = setup_logging(config.logging, log_filename, logger_name='StrategyOrchestrator') 

        self.logger.info("初始化 StrategyOrchestrator...")
        self._initialize_risk_manager()
        self._load_strategies()

    def _setup_logger(self) -> Optional[logging.Logger]:
        """设置调度器日志记录器 (使用 core.utils.setup_logging)。"""
        try:
            # 确保 self.config 包含 logging 部分
            if not self.config or 'logging' not in self.config:
                print("ERROR: Orchestrator config missing 'logging' section.", file=sys.stderr)
                return None
            
            log_filename = OmegaConf.select(self.config, 'logging.orchestrator_log_filename', default='orchestrator_fallback.log')
            
            # 使用 core.utils 中的 setup_logging
            logger = setup_logging(
                log_config=self.config.logging, 
                log_filename=log_filename,
                logger_name=self.__class__.__name__ # 使用类名作为 logger 名
            )
            logger.info("Strategy Orchestrator logging initialized.")
            return logger
        except Exception as e:
            print(f"ERROR: Failed to setup orchestrator logging: {e}", file=sys.stderr)
            # Fallback to basic logging if setup fails
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            logger = logging.getLogger(self.__class__.__name__ + '_Fallback')
            logger.error("Orchestrator logging setup failed, using basic config.", exc_info=True)
            return logger

    def _initialize_risk_manager(self) -> None:
        """初始化风险管理器实例。"""
        self.logger.info("初始化风险管理器...")
        try:
            # 使用工厂函数创建风险管理器
            # 需要将 config, execution_engine, data_provider 传递给它
            self.risk_manager = get_risk_manager(self.config, self.execution_engine, self.data_provider)
            if self.risk_manager:
                self.logger.info(f"风险管理器 {self.risk_manager.__class__.__name__} 初始化成功。")
            else:
                # 这不应该发生，因为 get_risk_manager 有默认回退
                self.logger.error("风险管理器初始化失败，返回了 None。")
        except Exception as rm_init_e:
            self.logger.critical(f"初始化风险管理器时发生严重错误: {rm_init_e}", exc_info=True)
            # 根据需要决定是否应该阻止 Orchestrator 继续运行
            # raise rm_init_e # 或者抛出异常

    def _load_strategies(self) -> None:
        """动态发现并加载所有已启用的策略。"""
        self.logger.info("开始加载策略...")
        enabled_strategies_config = OmegaConf.select(self.config, "orchestrator.enabled_strategies", default={})
        strategy_params_config = OmegaConf.select(self.config, "strategy_params", default={})
        # TODO: 从配置中读取要扫描的包路径
        package_path = "strategies"

        if not enabled_strategies_config:
             self.logger.warning("配置中未定义 'orchestrator.enabled_strategies'，没有启用任何策略。")
             return

        try:
            package = importlib.import_module(package_path)
            prefix = package.__name__ + '.'
            # 遍历 strategies 包及其子包
            for importer, modname, ispkg in pkgutil.walk_packages(package.__path__, prefix):
                try:
                    module = importlib.import_module(modname)
                    # 查找模块中所有继承自 StrategyBase 的类
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, StrategyBase) and obj is not StrategyBase:
                            strategy_name = obj.__name__
                            if enabled_strategies_config.get(strategy_name, False):
                                self.logger.info(f"找到已启用的策略: {strategy_name} in {modname}")
                                # 获取该策略的特定配置
                                strategy_config = strategy_params_config.get(strategy_name, OmegaConf.create({}))
                                if not strategy_config:
                                    self.logger.warning(f"未找到策略 '{strategy_name}' 的特定参数配置 ('strategy_params.{strategy_name}')，将使用空配置。")
                                
                                # 实例化策略
                                if not self.risk_manager:
                                    self.logger.error(f"无法实例化策略 {strategy_name}，因为风险管理器未初始化。")
                                    continue # 跳过此策略

                                try:
                                    # 将 risk_manager 实例传递给策略
                                    instance = obj(strategy_config, self.data_provider, self.execution_engine, self.risk_manager)
                                    self.strategies.append(instance)
                                    self.logger.info(f"策略 {strategy_name} 已成功实例化并加载。")
                                except Exception as init_e:
                                    self.logger.error(f"实例化策略 {strategy_name} 失败: {init_e}", exc_info=True)
                            elif strategy_name in enabled_strategies_config: # Exists but set to False
                                self.logger.info(f"策略 {strategy_name} 已找到但被禁用。")
                except ImportError as import_e:
                    self.logger.error(f"加载模块 {modname} 失败: {import_e}")
                except Exception as module_e:
                     self.logger.error(f"处理模块 {modname} 时发生错误: {module_e}", exc_info=True)

        except ImportError as pkg_e:
            self.logger.error(f"无法导入基础策略包 '{package_path}': {pkg_e}")
        except Exception as load_e:
             self.logger.error(f"加载策略过程中发生未知错误: {load_e}", exc_info=True)

        if not self.strategies:
            self.logger.warning("没有加载任何启用的策略。请检查配置和策略实现。")
        else:
            self.logger.info(f"策略加载完成。共加载 {len(self.strategies)} 个策略: {[s.get_name() for s in self.strategies]}")

    def run_cycle(self) -> None:
        """
        执行一个策略运行周期。
        获取所有相关品种和时间框架的最新数据，并将其传递给每个策略。
        """
        current_time = datetime.utcnow()
        self.logger.debug(f"开始执行策略周期: {current_time.isoformat()}")

        market_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        latest_events: Optional[pd.DataFrame] = None

        # --- 1. 获取数据 --- 
        try:
            # 1.1 获取市场价格数据 (所有相关品种和时间框架)
            symbols = list(OmegaConf.select(self.config, "realtime.symbols", default=[]))
            timeframes = list(OmegaConf.select(self.config, "realtime.timeframes", default=[]))

            if not symbols:
                 self.logger.warning("配置中未指定 'realtime.symbols'，无法获取市场价格数据。")
            elif not timeframes:
                 self.logger.warning("配置中未指定 'realtime.timeframes'，无法获取市场价格数据。")
            else:
                self.logger.debug(f"尝试为 Symbols={symbols} 和 Timeframes={timeframes} 获取合并价格数据...")
                for tf in timeframes:
                    market_data[tf] = {}
                    for sym in symbols:
                        # 调用 get_combined_prices 获取该 symbol/timeframe 的完整数据
                        combined_df = self.data_provider.market_provider.get_combined_prices(sym, tf)
                        if combined_df is not None and not combined_df.empty:
                            market_data[tf][sym] = combined_df
                            self.logger.debug(f"成功获取 {sym} ({tf}) 的合并数据，共 {len(combined_df)} 条。")
                        else:
                            self.logger.warning(f"未能获取 {sym} ({tf}) 的合并价格数据。")
                self.logger.info(f"已获取 {sum(len(tf_data) for tf_data in market_data.values())} 个 (Symbol, Timeframe) 组合的价格数据。")

            # 1.2 获取最新事件 (逻辑保持不变)
            self.logger.debug("尝试获取最新过滤事件数据...")
            latest_events = self.data_provider.get_filtered_events(live=True)
            if latest_events is not None and not latest_events.empty:
                self.logger.debug(f"获取到 {len(latest_events)} 个最新事件。")
            else:
                self.logger.debug("当前周期没有新的事件数据。")
                latest_events = None # Ensure it's None if empty

        except Exception as data_e:
            self.logger.error(f"获取数据时发生错误: {data_e}", exc_info=True)
            return # Don't proceed if data fetching failed

        # --- 2. 运行策略 --- 
        if not self.strategies:
            self.logger.warning("没有加载策略，跳过执行。")
            return

        for strategy in self.strategies:
            strategy_name = strategy.get_name()
            self.logger.debug(f"执行策略: {strategy_name}...")
            try:
                # 传递包含所有时间框架数据的嵌套字典 market_data
                # 注意：需要稍后修改 StrategyBase.process_new_data 的签名
                strategy.process_new_data(current_time, market_data, latest_events)
                self.logger.debug(f"策略 {strategy_name} 执行完成。")
            except Exception as strategy_e:
                self.logger.error(f"执行策略 {strategy_name} 时发生错误: {strategy_e}", exc_info=True)
        
        self.logger.debug(f"策略周期执行完毕: {datetime.utcnow().isoformat()}")

    def start(self) -> None:
        """
        启动策略执行循环。
        """
        interval_seconds = OmegaConf.select(self.config, "orchestrator.run_interval_seconds", default=60)
        if not self.strategies:
            self.logger.error("没有加载任何策略，无法启动执行循环。")
            return

        self.logger.info(f"启动策略执行循环，运行间隔: {interval_seconds} 秒...")
        self.running = True

        while self.running:
            cycle_start_time = time.monotonic()
            try:
                self.run_cycle()
            except Exception as cycle_e:
                 self.logger.critical(f"策略运行周期 run_cycle 发生严重错误: {cycle_e}", exc_info=True)
                 # Consider stopping or adding a cooldown period on critical errors
                 # self.stop()

            cycle_end_time = time.monotonic()
            elapsed = cycle_end_time - cycle_start_time
            sleep_time = interval_seconds - elapsed

            if sleep_time > 0:
                self.logger.debug(f"周期执行耗时 {elapsed:.2f} 秒，休眠 {sleep_time:.2f} 秒...")
                # Use interruptible sleep
                for _ in range(int(sleep_time)):
                    if not self.running:
                        break
                    time.sleep(1)
                if self.running and sleep_time % 1 > 0:
                     time.sleep(sleep_time % 1)
            else:
                self.logger.warning(f"周期执行耗时 {elapsed:.2f} 秒，超过设定的间隔 {interval_seconds} 秒！")

        self.logger.info("策略执行循环已停止。")

    def stop(self) -> None:
        """停止策略执行循环。"""
        if self.running:
            self.logger.info("收到停止信号，将在当前周期结束后停止执行循环。")
            self.running = False
        else:
             self.logger.info("策略执行循环已停止。")

# 示例用法 (通常在服务启动脚本中)
# if __name__ == '__main__':
#     config = load_config() # 加载配置
#     data_provider = DataProvider(config)
#     execution_engine = ExecutionEngine(config)
#     orchestrator = StrategyOrchestrator(config, data_provider, execution_engine)
#     orchestrator.start(interval_seconds=300) # 每 5 分钟运行一次 