#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
回测引擎核心逻辑
"""

import pandas as pd
import logging
import pytz
from datetime import datetime, timedelta, timezone
import time
import sys
import os
import importlib
import pkgutil
import inspect
from typing import Optional, Dict, Any, List
import quantstats as qs
from pathlib import Path
from omegaconf import DictConfig, OmegaConf, ListConfig, errors as OmegaErrors # Add OmegaErrors
import yaml # Add yaml import
import json
from decimal import Decimal

# 导入正确的 DataProvider 和 Strategy 基类/实现
try:
    # 使用 strategies.core 中的 DataProvider
    from strategies.core.data_providers import DataProvider, MarketDataProvider
except ImportError:
    # 尝试从上一级目录导入 (如果 engine.py 在 backtesting 子目录中)
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    try:
        from strategies.core.data_providers import DataProvider, MarketDataProvider
    except ImportError:
        logging.error("无法导入 DataProvider 或 MarketDataProvider，请确保 strategies.core.data_providers.py 路径正确。")
        DataProvider = None
        MarketDataProvider = None

try:
    # 使用正确的导入路径
    from economic_calendar.event_filter import filter_events_from_db # <--- 恢复这个
except ImportError:
    # 保留尝试添加路径的逻辑，以防万一
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    try:
        from economic_calendar.event_filter import filter_events_from_db # <--- 恢复这个
    except ImportError:
        logging.error("无法导入 filter_events_from_db，请确保 economic_calendar/event_filter 包路径正确且其 __init__.py 可用。")
        filter_events_from_db = None # <--- 如果导入失败，则为 None

# 导入具体的策略类，而不是基类
# from strategies.event_driven_space_strategy import EventDrivenSpaceStrategy # 注释掉原来的导入
from strategies.key_time_weight_turning_point_strategy import KeyTimeWeightTurningPointStrategy # <--- 恢复这个

# 导入模拟 Broker (现在使用 SandboxExecutionEngine 代替)
# from .broker import SimulatedBroker
from strategies.live.sandbox import SandboxExecutionEngine # <--- 取消注释这一行
from strategies.risk_management.risk_manager import RiskManager # ADDED
from strategies.core.strategy_base import StrategyBase # <--- 恢复这个
# SandboxExecutionEngine = Any # <--- 移除这一行对 Any 的赋值
# RiskManagerBase = Any # <--- 移除这个

logger = logging.getLogger(__name__)

# 自定义异常
class StrategyInitializationError(Exception):
    """Custom exception for errors during strategy initialization."""
    pass

class BacktestEngine:
    """
    封装回测流程的核心引擎。
    """
    def __init__(self,
                 merged_config: DictConfig,
                 strategy_name_from_config: str):
        """
        使用合并后的配置对象和策略名称初始化回测引擎。

        Args:
            merged_config (DictConfig): 已加载并合并的 OmegaConf 配置对象。
                                         通常由 run_backtest.py 中的 load_app_config 生成。
            strategy_name_from_config (str): 要运行的策略的类名。
                                              通常从配置的 'backtest.strategy_name' 获取。
        """
        self.config = merged_config # ADD THIS LINE to ensure self.config is set
        self.app_config = merged_config # Store the already merged config
        self.logger = logging.getLogger(f"BacktestEngine.{strategy_name_from_config}") # Logger name includes strategy
        self.backtest_id = f"{strategy_name_from_config}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}" # ADDED
        self.logger.info(f"Initializing BacktestEngine for strategy: {strategy_name_from_config}")
        self.logger.debug(f"Received merged_config keys: {list(self.app_config.keys())}")

        # --- 获取项目根路径 ---
        project_root_from_conf = OmegaConf.select(self.app_config, "project_root", default=None)
        if project_root_from_conf:
            self.project_root = Path(project_root_from_conf)
            self.logger.info(f"项目根路径已从配置中设置为: {self.project_root}")
        else:
            self.logger.error("CRITICAL: 'project_root' 未在应用配置中找到。这可能导致路径问题。请检查 core.utils.load_app_config 的实现。")
            self.project_root = Path(".").resolve()
            self.logger.warning(f"由于配置中缺少 'project_root'，已将项目根路径后备设置为: {self.project_root}")

        # --- 从 merged_config 中提取核心回测参数 ---
        # 路径基于 backtesting/config/backtest.yaml 的结构，因为它是模块特定配置

        # 从 backtest.engine 节点获取引擎参数
        self.engine_params = OmegaConf.select(self.app_config, "backtest.engine", default=OmegaConf.create())
        self.backtest_params = OmegaConf.select(self.app_config, "backtest.parameters", default=OmegaConf.create())
        self.data_params = OmegaConf.select(self.app_config, "backtest.data", default=OmegaConf.create()) # <-- 确保这一行被添加

        self.start_date_str = OmegaConf.select(self.engine_params, 'start_date')
        self.end_date_str = OmegaConf.select(self.engine_params, 'end_date')
        # 从财经事件中动态获取交易品种
        if hasattr(self, 'event_stream') and self.event_stream:
            self.symbols = list({event.symbol for event in self.event_stream if hasattr(event, 'symbol')})
            self.logger.info(f"从财经事件中动态获取到 {len(self.symbols)} 个交易品种: {self.symbols}")
        else:
            # 后备方案：从配置中获取
            self.symbols = OmegaConf.select(self.engine_params, 'symbols', default=OmegaConf.create([]))
            if isinstance(self.symbols, ListConfig):
                self.symbols = list(self.symbols)
            elif not isinstance(self.symbols, list):
                self.logger.warning(f"配置中的 'backtest.engine.symbols' 不是列表类型 (实际类型: {type(self.symbols)}), 将使用空列表。")
                self.symbols = []

        self.data_granularity = OmegaConf.select(self.engine_params, 'data_granularity', default="M1")
        self.primary_timeframe = OmegaConf.select(self.engine_params, 'primary_timeframe', default="M30") # 策略主要运作的时间框架
        self.data_padding_days = OmegaConf.select(self.engine_params, 'data_padding_days', default=30)

        # 从 backtest 节点获取其他回测参数
        self.initial_capital = self.backtest_params.get('initial_capital', 100000)
        # commission_bps 暂时不在此处提取，通常由 broker/execution_engine 处理其特定配置

        self.strategy_name = strategy_name_from_config # 直接使用传入的策略名

        # 从 backtest.strategy_params.{strategy_name} 获取策略特定参数的覆盖值
        # 注意：这里的 strategy_params_override 只是从 backtest.yaml 来的，默认合并将在 _initialize_strategy 中进行
        strategy_params_node = OmegaConf.select(self.app_config, f'backtest.strategy_params.{self.strategy_name}', default=OmegaConf.create({}))
        self.strategy_params_override = strategy_params_node

        # --- 引擎所需时间框架 (将被策略覆盖) ---
        self.engine_requested_timeframes = [OmegaConf.select(self.engine_params, 'primary_timeframe', default="M30")]

        # --- 关键参数校验 ---
        missing_params = []
        if self.start_date_str is None: missing_params.append("backtest.engine.start_date")
        if self.end_date_str is None: missing_params.append("backtest.engine.end_date")
        # symbols 可以为空，如果后续有自动推断逻辑
        # if not self.symbols: missing_params.append("backtest.engine.symbols (must be a non-empty list or auto-detection enabled)")
        if not self.strategy_name: missing_params.append("strategy_name (was not passed to engine)") # 理论上 strategy_name_from_config 不会是None

        if missing_params:
            msg = f"Critical backtest parameters missing in configuration: {', '.join(missing_params)}"
            self.logger.critical(msg)
            raise ValueError(msg)

        self.logger.info(f"Engine Params: StartDate='{self.start_date_str}', EndDate='{self.end_date_str}', Symbols={self.symbols}, DataGranularity='{self.data_granularity}', PrimaryTimeframe='{self.primary_timeframe}'")
        self.logger.info(f"Backtest Params: InitialCapital={self.initial_capital}, Strategy='{self.strategy_name}'")
        if self.strategy_params_override:
            self.logger.info(f"Strategy specific params override from config: {OmegaConf.to_container(self.strategy_params_override)}")


        # --- 保留其他成员变量的初始化 ---
        self.data_provider: Optional[DataProvider] = None
        self.strategy: Optional[StrategyBase] = None
        self.broker: Optional[SandboxExecutionEngine] = None
        self.risk_manager: Optional[RiskManager] = None
        self.event_stream = [] # 通常由 DataProvider 或 _load_data 填充事件
        self.results = {} # 存储回测结果
        self.trades = [] # 存储模拟交易记录
        self.equity_curve = pd.DataFrame(columns=['Equity']) # 存储资金曲线
        self.symbols_to_backtest = [] # 存储实际回测的品种 (可能在 _load_data 中根据 self.symbols 或自动检测填充)
        self.strategy_required_timeframes: List[str] = [] # 将由 _initialize_strategy 填充

        # initial_cash 已在上面通过 self.initial_capital 获取
        # self.initial_cash = OmegaConf.select(self.app_config, 'backtest.cash', default=100000)

        # 检查核心依赖是否成功导入 (这部分逻辑可以保留或移到更早的全局检查中)
        if not all([DataProvider, filter_events_from_db]): # filter_events_from_db 是一个函数
             self.logger.error("回测引擎核心依赖项未能完全导入 (DataProvider, filter_events_from_db)，无法初始化。")
             raise ImportError("BacktestEngine 核心依赖项加载失败。")
        if MarketDataProvider is None: # MarketDataProvider 是一个类
             self.logger.warning("MarketDataProvider 未找到，依赖它的功能可能受限。")

    def load_historical_data(self):
        """加载历史数据"""
        return self._load_data()

    def validate_data_quality(self, data: pd.DataFrame) -> bool:
        """执行数据质量检查"""
        if isinstance(data, dict):
            data = pd.concat(data.values(), axis=1)
        if data.empty:
            self.logger.error("数据质量验证失败: DataFrame为空")
            return False

        # 检查空值
        null_counts = data.isnull().sum()
        if null_counts.any():
            self.logger.error(f"数据包含空值:\\n{null_counts}")
            return False

        # 检查重复数据
        duplicates = data.duplicated().sum()
        if duplicates > 0:
            self.logger.error(f"发现{duplicates}条重复数据")
            return False

        # 检查时间序列连续性
        time_diff = data.index.to_series().diff().dropna()
        if (time_diff.value_counts().shape[0] > 1):
            self.logger.warning("时间间隔不一致，可能存在数据缺口")

        self.logger.info("数据质量检查通过")
        return True
        # --------------------------------------------

        # 检查核心依赖是否成功导入
        if not all([DataProvider, filter_events_from_db]):
             logger.error("回测引擎核心依赖项未能完全导入 (DataProvider, filter_events_from_db)，无法初始化。")
             raise ImportError("BacktestEngine 核心依赖项加载失败。")
        if MarketDataProvider is None:
             logger.warning("MarketDataProvider 未找到，依赖它的功能可能受限。")

    def _check_data_quality(self, df: pd.DataFrame, symbol: str, timeframe: str) -> bool:
        """
        检查K线数据的基本质量，包含更严格的数据完整性检查。

        Args:
            df (pd.DataFrame): 要检查的K线数据。
            symbol (str): 交易品种。
            timeframe (str): 时间框架。

        Returns:
            bool: 如果数据质量可接受则返回 True，否则返回 False。
        """
        if df is None or df.empty:
            self.logger.error(f"数据质量检查失败 for {symbol} {timeframe}: DataFrame is None or empty.")
            return False

        # 1. 检查空值 (简单示例：不允许 OHLC 有空值)
        required_cols = ['open', 'high', 'low', 'close']
        if df[required_cols].isnull().any().any():
            self.logger.error(f"数据质量检查失败 for {symbol} {timeframe}: OHLC 包含空值。空值统计:\\n{df[required_cols].isnull().sum()}")
            return False
            
        # 1.1 检查OHLC价格合理性
        invalid_ohlc = (
            (df['high'] < df['low']) |
            (df['open'] > df['high']) |
            (df['open'] < df['low']) |
            (df['close'] > df['high']) |
            (df['close'] < df['low'])
        )
        if invalid_ohlc.any():
            invalid_count = invalid_ohlc.sum()
            self.logger.error(f"数据质量检查失败 for {symbol} {timeframe}: 发现{invalid_count}条无效OHLC记录(high<low或价格超出范围)。")
            return False

        # 2. 检查时间序列连续性
        if not df.index.is_monotonic_increasing:
            self.logger.error(f"数据质量检查失败 for {symbol} {timeframe}: 时间戳非单调递增。")
            return False
            
        # 检查时间间隔是否符合预期
        time_diffs = df.index.to_series().diff().dropna()
        if not time_diffs.empty:
            expected_interval = pd.Timedelta(minutes=int(timeframe[1:])) if timeframe.startswith('M') else pd.Timedelta(hours=1)
            invalid_intervals = time_diffs[time_diffs > expected_interval * 100] # MODIFIED: from 1.5 to 100
            if not invalid_intervals.empty:
                gap_count = len(invalid_intervals)
                max_gap = invalid_intervals.max().total_seconds() / 60
                self.logger.error(f"数据质量检查失败 for {symbol} {timeframe}: 发现{gap_count}处时间间隔异常(最大间隔{max_gap:.1f}分钟)。")
                return False

        # 3. 检查数据量是否过少 (可选)
        min_records = self.data_params.get('min_records_for_quality_check', 50) # 从配置获取，默认50
        if len(df) < min_records:
            self.logger.warning(f"数据质量检查警告 for {symbol} {timeframe}: 数据量 ({len(df)}) 过少，少于最小要求 {min_records}。")
            # return False # 如果数据量过少则认为质量不合格

        # 4. 检查时间间隔是否一致 (可选)
        # 这部分可以更复杂，例如检查主要的时间间隔是否符合预期 (e.g., M30 应该是30分钟)
        # 这里仅作一个非常粗略的示例，检查相邻时间戳的差异是否过于离谱
        # time_diffs = df.index.to_series().diff().dropna()
        # if not time_diffs.empty:
        #     # median_diff = time_diffs.median()
        #     # max_acceptable_diff = median_diff * 5 # 举例：允许最大差异是中位数的5倍
        #     # if time_diffs.max() > max_acceptable_diff:
        #     #     self.logger.warning(f"数据质量检查警告 for {symbol} {timeframe}: 检测到大的时间间隔跳跃。")
        #     # 更简单：检查是否有异常大的时间差，例如超过1天 (对于日内数据)
        #     if (time_diffs > pd.Timedelta(days=1)).any() and timeframe.startswith('M'): # 仅对分钟级别检查
        #         self.logger.warning(f"数据质量检查警告 for {symbol} {timeframe}: 时间间隔不一致，可能存在数据缺口。")

        # 所有检查通过
        # self.logger.info(f"数据质量检查通过 for {symbol} {timeframe}") # 这行日志太频繁，移到调用处
        return True

    def _load_data(self):
        """
        加载回测所需的所有历史数据。
        """
        self.logger.info("开始加载历史数据...")
        if not self.data_provider:
            self.logger.error("无法加载数据: 数据提供器未初始化。")
            return False

        # 记录回测时间范围
        self.logger.info(f"回测时间范围: {self.start_date_utc} 至 {self.end_date_utc}")
        
        for symbol in self.symbols:
            # 增强日志: 记录尝试加载的货币对
            self.logger.info(f"正在加载 {symbol} 的历史数据...")
            
            # 增强日志: 记录数据提供器的类型和来源路径
            if hasattr(self.data_provider, 'data_path'):
                self.logger.info(f"数据来源路径: {self.data_provider.data_path}")
            
            for timeframe in self.engine_requested_timeframes:
                # 增强日志: 记录正在加载的时间框架
                self.logger.info(f"正在加载 {symbol} 的 {timeframe} 时间框架数据...")
                
                # 构建或获取数据文件路径（新增日志）
                if hasattr(self.data_provider, '_get_hist_filepath'):
                    try:
                        file_path = self.data_provider._get_hist_filepath(symbol, timeframe)
                        self.logger.info(f"数据文件路径: {file_path}")
                    except Exception as e:
                        self.logger.warning(f"无法获取数据文件路径: {e}")
                
                try:
                    # 加载历史数据
                    historical_data = self.data_provider.get_historical_prices(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_date=self.start_date_utc - timedelta(days=self.config.get('data_provider', {}).get('data_padding_days', 0)),
                        end_date=self.end_date_utc
                    )
                    
                    # 增强日志: 检查和记录返回的数据情况
                    if historical_data is None:
                        self.logger.error(f"加载 {symbol} 的 {timeframe} 数据失败: 数据提供器返回 None。")
                        return False
                    
                    if historical_data.empty:
                        self.logger.error(f"加载 {symbol} 的 {timeframe} 数据失败: 返回的数据集为空。")
                        return False
                    
                    # 增强日志: 记录加载到的数据范围
                    data_start = historical_data.index.min()
                    data_end = historical_data.index.max()
                    data_rows = len(historical_data)
                    self.logger.info(f"成功加载 {symbol} 的 {timeframe} 数据: {data_rows} 行, 时间范围 {data_start} 至 {data_end}")
                    
                    # 检查数据是否覆盖了请求的时间范围
                    if data_start > self.start_date_utc:
                        self.logger.warning(f"注意: {symbol} 的 {timeframe} 数据起始时间 ({data_start}) 晚于请求的开始时间 ({self.start_date_utc}).")
                    if data_end < self.end_date_utc:
                        self.logger.warning(f"注意: {symbol} 的 {timeframe} 数据结束时间 ({data_end}) 早于请求的结束时间 ({self.end_date_utc}).")
                    
                    # 验证数据质量
                    if not self.validate_data_quality(historical_data):
                        self.logger.error(f"{symbol} 的 {timeframe} 数据质量验证失败，可能影响回测结果。")
                    
                    # 记录数据缓存
                    self.historical_data_cache[(symbol, timeframe)] = historical_data
                    self.logger.debug(f"已将 {symbol} 的 {timeframe} 数据添加到缓存。")
                    
                    # 验证关键字段是否存在
                    required_columns = ['open', 'high', 'low', 'close', 'volume']
                    missing_columns = [col for col in required_columns if col not in historical_data.columns]
                    if missing_columns:
                        self.logger.error(f"{symbol} 的 {timeframe} 数据缺少必要字段: {missing_columns}")
                        return False
                    
                    # 验证close字段的完整性
                    if historical_data['close'].isnull().any():
                        self.logger.warning(f"{symbol} 的 {timeframe} 数据中 'close' 字段存在空值，将使用前向填充处理。")
                        historical_data['close'].fillna(method='ffill', inplace=True)
                    
                    # 验证high、low、open、close字段的完整性
                    for col in ['high', 'low', 'open', 'close']:
                        if historical_data[col].isnull().any():
                            self.logger.warning(f"{symbol} 的 {timeframe} 数据中 '{col}' 字段存在空值，将使用前向填充处理。")
                            historical_data[col].fillna(method='ffill', inplace=True)
                    
                    # 更新缓存中的数据
                    self.historical_data_cache[(symbol, timeframe)] = historical_data
                    
                except Exception as e:
                    self.logger.error(f"加载 {symbol} 的 {timeframe} 数据时发生错误: {e}", exc_info=True)
                    return False

        self.logger.info("历史数据加载完成。")
        return True

    def _find_strategy_module(self, strategy_class_name: str) -> Optional[str]:
        """
        将策略类名映射到模块名（文件名）
        直接使用简单固定规则：所有策略类名转换为小写并使用下划线分隔
        """
        try:
            # 简单规则：移除尾部的Strategy，转换为全小写加下划线
            if strategy_class_name.endswith('Strategy'):
                base_name = strategy_class_name[:-8]  # 移除"Strategy"后缀

                # 将驼峰命名转换为下划线命名
                import re
                s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', base_name) # Corrected: r'\1_\2' to r'\1_\2' (no, should be r'\1_\2')
                module_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower() # Corrected: r'\1_\2' to r'\1_\2'

                # 添加_strategy后缀
                module_name = f"{module_name}_strategy"

                logger.info(f"策略文件名映射: {strategy_class_name} -> {module_name}")

                # 验证模块是否存在
                try:
                    module_path = f"strategies.{module_name}"
                    module = importlib.import_module(module_path)
                    return module_name
                except ImportError:
                    logger.error(f"找不到模块: {module_path}")
                    return None

            logger.error(f"策略类名 {strategy_class_name} 不是有效格式（应以Strategy结尾）")
            return None
        except Exception as e:
            logger.error(f"映射策略模块名时出错: {e}")
            return None

    def _load_strategy_specific_yaml_config(self, strategy_name: str) -> DictConfig:
        """
        尝试加载策略专属的 YAML 配置文件。
        配置文件应位于 <project_root>/strategies/config/<strategy_name>.yaml

        Args:
            strategy_name (str): 策略的类名。

        Returns:
            DictConfig: 加载的配置 (如果文件存在且有效)，否则为空的 DictConfig。
        """
        if not hasattr(self, 'project_root') or not self.project_root or str(self.project_root) == ".":
            self.logger.error(f"项目根路径 (self.project_root='{getattr(self, 'project_root', 'Not Set')}') 无效或未正确设置，无法加载策略专属YAML配置。")
            return OmegaConf.create({})

        project_root_path = Path(self.project_root)
        strategy_config_filename = f"{strategy_name}.yaml"
        strategy_config_path = project_root_path / "strategies" / "config" / strategy_config_filename

        if strategy_config_path.is_file():
            try:
                specific_conf = OmegaConf.load(strategy_config_path)
                self.logger.info(f"已成功加载策略专属配置文件: {strategy_config_path}")

                if specific_conf is None:
                    self.logger.info(f"策略专属配置文件 {strategy_config_path} 为空，返回空配置。")
                    return OmegaConf.create({})

                if not isinstance(specific_conf, DictConfig):
                    self.logger.warning(f"策略专属配置文件 {strategy_config_path} 未能直接解析为 DictConfig (实际类型: {type(specific_conf)})。")
                    if isinstance(specific_conf, dict):
                        self.logger.info(f"将 {strategy_config_path} 的 dict 内容包装为 DictConfig。")
                        return OmegaConf.create(specific_conf)
                    else:
                        self.logger.error(f"无法将 {strategy_config_path} 的内容 (类型: {type(specific_conf)}) 转换为 DictConfig。返回空配置。")
                        return OmegaConf.create({})
                return specific_conf
            except OmegaErrors.OmegaConfBaseException as e:
                self.logger.error(f"加载策略专属配置文件 {strategy_config_path} 时发生 OmegaConf 错误: {e}")
            except yaml.YAMLError as e:
                self.logger.error(f"解析策略专属配置文件 {strategy_config_path} 时发生 YAML 错误: {e}")
            except Exception as e:
                self.logger.error(f"加载或解析策略专属配置文件 {strategy_config_path} 时发生未知错误: {e}")
            else:
                self.logger.info(f"未找到策略专属配置文件: {strategy_config_path}，将使用空配置。")

        return OmegaConf.create({})

    def _initialize_strategy(self) -> bool: # Signature will change effectively as it won't return bool on error
        self.logger.info("Initializing strategy...")
        
        strategy_name_to_load = self.strategy_name # This is the class name
        self.logger.info(f"Attempting to initialize strategy class: {strategy_name_to_load}")

        # 1. Get module_name directly from the passed config (set by run_all_backtests.py)
        module_name = OmegaConf.select(self.app_config, "backtest.engine.strategy_module_path", default=None)

        if not module_name:
            self.logger.error(f"Critical: Strategy module path ('backtest.engine.strategy_module_path') was not found in the configuration for strategy class '{strategy_name_to_load}'. This should be set by the calling script (e.g., run_all_backtests.py).")
            raise StrategyInitializationError(f"Strategy module path for '{strategy_name_to_load}' is not configured under 'backtest.engine.strategy_module_path'.")
        
        self.logger.info(f"Using explicitly configured strategy module path: '{module_name}' for strategy class '{strategy_name_to_load}'.")

        try:
            strategy_module = importlib.import_module(module_name)
            self.logger.info(f"Successfully imported strategy module: '{module_name}'")
        except ImportError as e:
            self.logger.error(f"Failed to import strategy module '{module_name}': {e}")
            raise StrategyInitializationError(f"Failed to import strategy module '{module_name}': {e}") from e

        try:
            StrategyClassToLoad = getattr(strategy_module, strategy_name_to_load)
        except AttributeError:
            self.logger.error(f"Strategy class '{strategy_name_to_load}' not found in module '{module_name}'.")
            # return False # OLD
            raise StrategyInitializationError(f"Strategy class '{strategy_name_to_load}' not found in module '{module_name}'.") # NEW

        # --- 参数合并逻辑 (已简化和修正) ---
        # 1. 获取该策略在 strategy_params 下的专属配置 (如果有)
        strategy_specific_params_node = OmegaConf.select(self.config, f"strategy_params.{strategy_name_to_load}", default=None)
        final_strategy_params = strategy_specific_params_node if strategy_specific_params_node else OmegaConf.create()

        self.logger.info(f"Strategy '{strategy_name_to_load}' specific params from config: {OmegaConf.to_container(final_strategy_params)}")
        
        # self.app_config IS self.config, so the merged view is already what we need for the strategy object.
        # The strategy's __init__ will use self.params (derived from app_config.strategy_params.CurrentStrategyName) for its specific params.
        # And it will use self.config (the full app_config) for any other global settings it might need.

        try:
            self.logger.info(f"Instantiating strategy: {strategy_name_to_load}")
            self.logger.debug(f"Strategy '{strategy_name_to_load}' will be initialized with strategy_id='{self.strategy_name}', full app_config, data_provider, execution_engine, risk_manager.")
            
            self.strategy = StrategyClassToLoad(
                strategy_id=self.strategy_name, # Use the unique ID for this backtest run
                app_config=self.config,         # Pass the entire merged configuration
                data_provider=self.data_provider,
                execution_engine=self.broker, # self.broker is the SandboxExecutionEngine
                risk_manager=self.risk_manager,
                live_mode=False # Backtesting is never live_mode=True
            )
            self.logger.info(f"Strategy '{self.strategy_name}' (class: {strategy_name_to_load}) initialized successfully.")
            # 获取策略所需的时间框架
            if hasattr(self.strategy, 'get_required_timeframes') and callable(self.strategy.get_required_timeframes):
                self.strategy_required_timeframes = self.strategy.get_required_timeframes()
                self.logger.info(f"Strategy '{self.strategy_name}' requires timeframes: {self.strategy_required_timeframes}")
            else:
                self.logger.warning(f"Strategy '{self.strategy_name}' does not have 'get_required_timeframes' method. Defaulting to engine's primary_timeframe: {self.engine_requested_timeframes}")
                self.strategy_required_timeframes = self.engine_requested_timeframes # Fallback
        except TypeError as e:
            self.logger.error(f"Error initializing strategy '{strategy_name_to_load}' due to TypeError: {e}. Check constructor signature and parameters.")
            # return False # OLD
            raise StrategyInitializationError(f"Error initializing strategy '{strategy_name_to_load}' due to TypeError: {e}. Ensure constructor signature (strategy_id, app_config, data_provider, execution_engine, risk_manager, live_mode) is correct.") # NEW
        except Exception as e:
            self.logger.error(f"Failed to initialize strategy '{strategy_name_to_load}': {e}", exc_info=True)
            # return False # OLD
            raise StrategyInitializationError(f"An unexpected error occurred while initializing strategy '{strategy_name_to_load}': {e}") # NEW
        # If we reach here, it means success
        return # Effectively returns None, but the absence of an exception implies success for the caller that uses try/except

    def _initialize_components(self) -> bool: # Effectively, this will raise on error, or return True (or None implicitly) on success
        self.logger.info("Initializing backtest components...")
        # Initialize DataProvider
        # ... (DataProvider initialization as before)
        # Initialize Broker (SandboxExecutionEngine)
        # ... (Broker initialization as before)
        # Initialize RiskManager
        # ... (RiskManager initialization as before)
        # Initialize Strategy
        # if not self._initialize_strategy(): # OLD
        #     self.logger.error("Strategy initialization failed during component setup.") # OLD
        #     return False # OLD
        self._initialize_strategy() # NEW: Let exceptions propagate

        self.logger.info("All backtest components initialized successfully.")
        return True # Or simply return, as exceptions handle failure

    def _initialize_broker(self):
        """
        (内部方法) 初始化模拟经纪商 (使用 SandboxExecutionEngine)。
        """
        logger.info("初始化策略...")
        strategy_name_to_load = self.strategy_name
        if not strategy_name_to_load:
            logger.error("无法初始化策略：策略名称未在引擎中设置。")
            return False

        if not self.data_provider: # ADDED: Ensure data_provider is initialized
            logger.error("无法初始化策略：数据提供者 (data_provider) 未初始化。")
            return False
        if not self.broker:
            logger.error("无法初始化策略：模拟经纪商 (broker) 未初始化。")
            return False
        if not self.risk_manager:
            logger.error("无法初始化策略：风险管理器 (risk_manager) 未初始化。")
            return False

        try:
            # 动态导入并实例化指定的策略类
            module_name = self._find_strategy_module(strategy_name_to_load)
            if not module_name:
                # _find_strategy_module 内部已经记录了错误
                return False

            module_path = f"strategies.{module_name}"

            module = importlib.import_module(module_path)
            StrategyClassToLoad = None
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and name == strategy_name_to_load and issubclass(obj, StrategyBase):
                    StrategyClassToLoad = obj
                    break

            if StrategyClassToLoad is None:
                logger.error(f"已成功导入模块 {module_path}，但在其中未找到名为 '{strategy_name_to_load}' 且继承自 StrategyBase 的类。")
                return False

            # --- 新的参数合并逻辑 (优先级：类默认 -> 策略YAML -> backtest.yaml覆盖) ---
            default_params = OmegaConf.create({})
            if hasattr(StrategyClassToLoad, 'get_default_params') and callable(getattr(StrategyClassToLoad, 'get_default_params')):
                try:
                    class_defaults = StrategyClassToLoad.get_default_params()
                    if class_defaults is not None and not isinstance(class_defaults, dict):
                        self.logger.warning(f"策略 '{strategy_name_to_load}'.get_default_params() 返回了非字典类型 ({type(class_defaults)})，将忽略。")
                        class_defaults = {}
                    default_params = OmegaConf.create(class_defaults or {})
                    self.logger.info(f"获取到策略 '{strategy_name_to_load}' 的类定义默认参数: {OmegaConf.to_container(default_params) if default_params else '{}'}")
                except Exception as e:
                    self.logger.warning(f"调用策略 '{strategy_name_to_load}'.get_default_params() 时出错: {e}。将使用空默认参数。")
                else:
                    self.logger.info(f"策略 '{strategy_name_to_load}' 未定义 get_default_params 方法。尝试旧的 strategies.config 方式获取默认参数。")
                try:
                    from strategies.config import DEFAULT_CONFIG as strategies_default_configs
                    if strategy_name_to_load in strategies_default_configs:
                        raw_defaults = strategies_default_configs.get(strategy_name_to_load)
                        if 'strategy_params' in raw_defaults:
                            default_params = OmegaConf.create(raw_defaults['strategy_params'])
                        else:
                            default_params = OmegaConf.create(raw_defaults)
                        self.logger.info(f"成功从 strategies.config 为 '{strategy_name_to_load}' 加载旧式默认参数。")
                except ImportError:
                    self.logger.info("无法从 strategies.config 导入 DEFAULT_CONFIG (旧式默认参数)。")
                except KeyError:
                    self.logger.info(f"在 strategies.config.DEFAULT_CONFIG 中未找到策略 '{strategy_name_to_load}' 的旧式默认参数。")
                except Exception as e:
                    self.logger.warning(f"从 strategies.config 加载旧式默认参数时发生错误: {e}")

            strategy_specific_yaml_conf = self._load_strategy_specific_yaml_config(strategy_name_to_load)
            # Corrected check for empty/None config object for strategy_specific_yaml_conf
            if not strategy_specific_yaml_conf or not dict(strategy_specific_yaml_conf):
                strategy_specific_yaml_conf = OmegaConf.create({})
            if dict(strategy_specific_yaml_conf): # Check if it's not empty after potential recreation
                self.logger.info(f"从 {strategy_name_to_load}.yaml 加载的策略特定参数: {OmegaConf.to_container(strategy_specific_yaml_conf)}")
            else:
                self.logger.info(f"未从 {strategy_name_to_load}.yaml 加载到特定参数，或文件为空/无效。")

            config_override_params = self.strategy_params_override
            # Corrected check for empty/None config object for config_override_params
            if not config_override_params or not dict(config_override_params):
                config_override_params = OmegaConf.create({})
            if dict(config_override_params): # Check if it's not empty after potential recreation
                self.logger.info(f"从 backtest.yaml (backtest.strategy_params.{strategy_name_to_load}) 加载的策略覆盖参数: {OmegaConf.to_container(config_override_params)}")

            final_strategy_params = OmegaConf.merge(
                default_params,
                strategy_specific_yaml_conf,
                config_override_params
            )
            self.logger.info(f"策略 '{strategy_name_to_load}' 使用的最终参数已合并。")
            self.logger.debug(f"最终参数内容: {OmegaConf.to_container(final_strategy_params)}")

            # --- MODIFICATION FOR StrategyBase config handling ---
            # Block to update self.app_config with the merged parameters for the current strategy
            try:
                # Ensure the base 'strategy_params' node exists in app_config to avoid errors on first update
                if OmegaConf.select(self.app_config, 'strategy_params', default=None) is None:
                    OmegaConf.update(self.app_config, 'strategy_params', OmegaConf.create({}), merge=True)
                    self.logger.info("已在 self.app_config 中创建 'strategy_params' 基础节点。")

                # Update app_config with final_strategy_params under strategy_params.{strategy_name_to_load}
                # This makes final_strategy_params (derived from class defaults, YAML, and backtest.yaml overrides)
                # available to StrategyBase as self.app_config.strategy_params[self.strategy_id]
                # The 'merge=False' ensures that if strategy_name_to_load already exists, its content is replaced
                # by final_strategy_params, rather than merging into it. This is important if there are
                # prior (potentially incomplete or outdated) params for this strategy_id in app_config.
                OmegaConf.update(self.app_config, f"strategy_params.{strategy_name_to_load}", final_strategy_params, merge=False)
                self.logger.info(f"已将合并后的策略参数 (final_strategy_params) 更新到 self.app_config.strategy_params.{strategy_name_to_load} (merge=False)。")
            except Exception as e_conf_update:
                self.logger.error(f"在 _initialize_strategy 中更新 self.app_config.strategy_params.{strategy_name_to_load} 失败: {e_conf_update}", exc_info=True)
                return False # Fail strategy initialization if config update fails
            # --- END MODIFICATION ---

            self.strategy = StrategyClassToLoad(
                strategy_id=self.strategy_name, # This is strategy_name_to_load
                app_config=self.app_config,    # Pass the entire app_config
                data_provider=self.data_provider,
                execution_engine=self.broker,
                risk_manager=self.risk_manager,
                live_mode=False                # For backtesting
            )
            logger.info(f"策略 '{strategy_name_to_load}' 初始化成功。")
            return True
        except Exception as e:
            logger.error(f"初始化策略 {strategy_name_to_load} 时出错: {e}", exc_info=True)
            return False

    def _initialize_broker(self):
        """
        (内部方法) 初始化模拟经纪商 (使用 SandboxExecutionEngine)。
        """
        # self.initial_cash 已在 __init__ 中正确设置
        logger.info(f"初始化模拟经纪商 (Sandbox)，初始资金: {self.initial_capital}...")
        try:
            # SandboxExecutionEngine 应该接收其自身特定的配置节点，而不是整个 app_config
            # 它也需要知道初始资金等。
            # 假设 SandboxExecutionEngine 的 __init__ 能够处理从 app_config 中提取所需部分，
            # 或者期望一个更精确的配置对象。
            # 当前的 app_config 包含了所有配置。
            # 确保 SandboxExecutionEngine 的 __init__ 从 app_config.execution_engine.sandbox 读取其特定配置，
            # 并从 app_config.backtest.cash 或 self.initial_capital 获取初始资金。
            self.broker = SandboxExecutionEngine(
                config=self.app_config, # 传递总配置，让 Sandbox 自己提取所需部分
                data_provider=self.data_provider, # 传递 DataProvider
                strategy_name=self.strategy_name # 传递策略名，可能用于日志或特定行为
            )
            # broker 的 connect 方法内部应该使用配置来设置初始资金等
            # self.broker.set_initial_cash(self.initial_capital) # 如果有这样的方法
            self.broker.connect() # connect 应该处理初始化资金
            logger.info("模拟经纪商 (Sandbox) 初始化并连接成功。")
            return True
        except Exception as e:
             logger.error(f"初始化模拟经纪商 (Sandbox) 时出错: {e}", exc_info=True)
             return False

    def _initialize_risk_manager(self):
        """初始化风险管理器。"""
        self.logger.info("初始化风险管理器...")
        try:
            # 从主配置中获取风险管理器的特定配置部分
            # 现在 self.app_config 是合并后的总配置
            rm_config_node = OmegaConf.select(self.app_config, 'risk_manager', default=OmegaConf.create({}))

            # RiskManager 可能期望参数在 'params' 子节点下，或者直接在 'risk_manager' 节点下
            rm_specific_config = OmegaConf.select(rm_config_node, 'params')
            if rm_specific_config is None: # 如果 'params' 不存在，则使用整个 'risk_manager' 节点
                rm_specific_config = rm_config_node
                self.logger.info("在 'risk_manager.params' 未找到配置，将使用 'risk_manager' 下的配置作为风险管理器参数。")

            if not rm_specific_config: # 检查是否为空配置
                self.logger.warning("配置中 risk_manager 部分为空或未找到，RiskManager 将使用其内部默认值（如果有）。")
                rm_specific_config = OmegaConf.create({})


            # 确保 rm_specific_config 是一个普通字典，而不是 OmegaConf DictConfig
            if isinstance(rm_specific_config, DictConfig):
                rm_config_dict = OmegaConf.to_container(rm_specific_config, resolve=True)
            # Correcting indentation for the 'else' corresponding to 'if isinstance(...)'
            else: # 以防万一，它不是 DictConfig 也不是普通 dict
                rm_config_dict = dict(rm_specific_config) if rm_specific_config else {}


            self.risk_manager = RiskManager(config=rm_config_dict) # 假设 RiskManager 的 __init__ 接收 config=Dict[str,Any]
            self.logger.info(f"新的 RiskManager ({self.risk_manager.__class__.__name__}) 初始化成功。")
            self.logger.debug(f"传递给 RiskManager 的配置: {rm_config_dict}")
            return True

        except Exception as e:
            self.logger.error(f"初始化新的 RiskManager 时出错: {e}", exc_info=True)
            self.risk_manager = None # 确保在失败时 risk_manager 为 None
            return False
            # 根据需要，这里可以决定是否要抛出异常使回测引擎停止
            # raise # 取消注释以在风险管理器初始化失败时停止引擎

    def run(self):
        """
        执行完整的回测流程。
        """
        logger.info("===> 开始回测 <===")
        
        # 初始化组件
        # 注意：以下初始化方法如果失败，理想情况下应抛出异常而不是返回 False
        # 为了逐步重构，我们先主要关注 _initialize_strategy 的异常处理

        # 1. 初始化 DataProvider
        try:
            logger.info("步骤 1: 初始化 DataProvider...")
            self.data_provider = DataProvider(self.app_config)
            logger.info("DataProvider 初始化成功。")
        except Exception as e_init_dp:
            logger.error(f"DataProvider 初始化失败: {e_init_dp}", exc_info=True)
            self.results = self._generate_results_on_error("DataProvider initialization failed.")
            self._save_results_to_json()
            raise RuntimeError("DataProvider initialization failed, cannot continue backtest.") from e_init_dp

        # 2. 初始化 Broker
        if not self._initialize_broker(): # TODO: Refactor to raise on error
            logger.error("模拟经纪商初始化失败，回测中止。")
            self.results = self._generate_results_on_error("Broker initialization failed.")
            self._save_results_to_json()
            raise RuntimeError("Broker initialization failed, cannot continue backtest.") # Changed to raise
        
        # 3. 初始化 RiskManager
        if not self._initialize_risk_manager(): # TODO: Refactor to raise on error
            logger.error("风险管理器初始化失败，回测中止。")
            self.results = self._generate_results_on_error("Risk manager initialization failed.")
            self._save_results_to_json()
            raise RuntimeError("Risk manager initialization failed, cannot continue backtest.") # Changed to raise

        # 4. 初始化 Strategy (这将设置 self.strategy_required_timeframes)
        try:
            self._initialize_strategy() # This method now raises StrategyInitializationError on failure
            logger.info(f"策略 {self.strategy.get_name()} 初始化成功。")
        except StrategyInitializationError as e_init_strat:
            logger.error(f"策略初始化失败 (捕获于 BacktestEngine.run): {e_init_strat}，回测中止。")
            self.results = self._generate_results_on_error(f"StrategyInitializationError: {str(e_init_strat)}")
            self._save_results_to_json()
            raise # RE-RAISE to allow run_single_backtest to catch it
        except Exception as e_init_unexpected: # Catch any other unexpected error during strategy init
            logger.error(f"策略实例化或初始化过程中发生非常规的意外错误: {e_init_unexpected}，回测中止。", exc_info=True)
            self.results = self._generate_results_on_error(f"Unexpected strategy initialization error: {str(e_init_unexpected)}")
            self._save_results_to_json()
            raise # RE-RAISE

        # 5. 加载数据 (现在 self.strategy_required_timeframes 已被设置)
        if not self._load_data(): # TODO: Refactor to raise on error
            logger.error("数据加载失败，回测中止。")
            self.results = self._generate_results_on_error("Data loading failed.")
            self._save_results_to_json()
            # Ideally, this should raise an exception that run_single_backtest catches.
            # For now, run_single_backtest might still misinterpret this if it doesn't check return value properly.
            raise RuntimeError("Data loading failed, cannot continue backtest.") # Changed to raise
        
        # 如果所有初始化都成功 (即没有异常被抛出并导致提前退出)
        logger.info(f"使用策略: {self.strategy.get_name()}")
        logger.info(f"回测品种: {self.symbols_to_backtest}")
        logger.info(f"初始资金: {self.initial_capital}")
        
        if not self.backtest_timestamps:
            logger.error("回测时间戳列表为空，无法执行回测循环。")
            self.results = self._generate_results_on_error("Backtest timestamps are empty after initialization.")
            self._save_results_to_json()
            raise RuntimeError("Backtest cannot proceed: Timestamps are empty after initialization.")
            
        logger.info(f"回测时间从 {self.backtest_timestamps[0]} 到 {self.backtest_timestamps[-1]}")

        final_timestamp_count = len(self.backtest_timestamps)
        logger.info(f"[调试] 最终确认的回测时间点数量 (循环将执行次数): {final_timestamp_count}")
        # Redundant check, already handled above
        # if final_timestamp_count == 0:
        #      logger.error("[关键错误] 最终回测时间点列表为空，无法执行回测循环。")
        #      self.results = self._generate_results_on_error("Critical error: Backtest timestamp list is empty before loop.")
        #      self._save_results_to_json()
        #      raise RuntimeError("Backtest cannot proceed with an empty timestamp list.")

        self.equity_curve.loc[self.backtest_timestamps[0]] = [self.initial_capital]
        total_steps = final_timestamp_count
        start_run_time = time.time()
        logger.info(f"开始迭代 {total_steps} 个时间点...")
        logger.info(f"[调试] 第一个时间点: {self.backtest_timestamps[0]}, 最后一个时间点: {self.backtest_timestamps[-1]}")

        current_time_utc_loop = None # For logging in case of loop error
        try: # Wrap main loop
            for i, current_time_utc_loop in enumerate(self.backtest_timestamps):
                if i == 0 or (i + 1) % 10000 == 0:
                    logger.info(f"[调试] 正在处理第 {i+1}/{total_steps} 个时间点: {current_time_utc_loop}")

                current_market_data: Dict[str, Dict[str, pd.DataFrame]] = {}
                for symbol in self.symbols_to_backtest:
                    current_market_data[symbol] = {}
                    if symbol in self.all_market_data:
                        for tf, df in self.all_market_data[symbol].items():
                             relevant_bars = df.loc[:current_time_utc_loop]
                             if not relevant_bars.empty:
                                  current_market_data[symbol][tf] = relevant_bars

                events_df_for_strategy = None
                # Corrected OmegaConf.get usage and string literal for timeframe
                duration_minutes_cfg = self.app_config.get('strategy_defaults.space_definition.duration_minutes', 30)
                m30_timedelta = pd.Timedelta(minutes=duration_minutes_cfg)
                previous_m30_time_utc = current_time_utc_loop - m30_timedelta

                if self.all_events_df is not None and 'timestamp' in self.all_events_df.columns:
                     mask = (self.all_events_df['timestamp'] > previous_m30_time_utc) & \
                            (self.all_events_df['timestamp'] <= current_time_utc_loop)
                     events_now_slice = self.all_events_df.loc[mask]

                     if not events_now_slice.empty:
                         events_now = events_now_slice.copy() # Make a copy
                         if 'Importance' in events_now.columns and 'importance' not in events_now.columns:
                             events_now.rename(columns={'Importance': 'importance'}, inplace=True)
                         elif 'importance' not in events_now.columns and 'Importance' not in events_now.columns:
                             logger.error(f"[EngineRun-Debug] CRITICAL: Neither 'Importance' nor 'importance' column found in events_now. Columns: {events_now.columns.tolist()}")
                         
                         events_df_for_strategy = events_now # Assign the working copy
                         if 'datetime' not in events_df_for_strategy.columns and 'timestamp' in events_df_for_strategy.columns:
                              events_df_for_strategy['datetime'] = events_df_for_strategy['timestamp']
                         # Timezone checks can be added here if necessary
                     else: # if events_now_slice was empty
                         events_df_for_strategy = pd.DataFrame() # Assign an empty DataFrame

                # Strategy core logic call
                self.strategy.process_new_data(current_time_utc_loop, current_market_data, events_df_for_strategy)
                
                current_equity = self.broker.get_account_balance().get('USD', self.initial_capital)
                self.equity_curve.loc[current_time_utc_loop] = [current_equity]

        except Exception as loop_e:
            # Use current_time_utc_loop which holds the timestamp at the point of failure in the loop
            failed_timestamp_str = str(current_time_utc_loop) if current_time_utc_loop else 'unknown'
            logger.critical(f"回测主循环中发生严重错误，策略: {self.strategy.get_name()}, 时间点: {failed_timestamp_str} : {loop_e}", exc_info=True)
            self.results = self._generate_results_on_error(f"Runtime error in strategy loop at {failed_timestamp_str}: {str(loop_e)}")
            self._save_results_to_json()
            raise # Re-raise to be caught by run_single_backtest

        end_run_time = time.time()
        logger.info(f"<=== 回测完成 ===> 总耗时: {end_run_time - start_run_time:.2f} 秒。")

        self.trades = self.broker.get_trade_history() if hasattr(self.broker, 'get_trade_history') else []
        self.results = self._generate_results() # Generate results on successful completion
        self._save_results_to_json()
        return self.results

    def _generate_results(self):
        """
        (内部方法) 计算并生成回测结果报告。
        现在还会将结果保存到 JSON 文件。
        """
        logger.info("开始生成回测结果...")
        final_equity = self.broker.get_equity()
        total_return = (final_equity - self.initial_capital) / self.initial_capital if self.initial_capital else 0
        # 使用 broker 中的 equity_curve
        returns_series = self.broker.equity_curve['Equity'].pct_change().dropna()

        if returns_series.empty:
            logger.warning("没有有效的收益率数据，无法计算 QuantStats 指标。")
            # 仍然可以报告基本信息
            self.results = {
                'initial_cash': self.initial_capital,
                'final_equity': final_equity,
                'total_return': total_return,
                'total_trades': len(self.broker.get_trade_history()) if self.broker and hasattr(self.broker, 'get_trade_history') else 0,
                'quantstats_metrics': 'No returns data available',
                'error': 'No valid returns for analysis'
            }
        else:
            try:
                # --- 使用 QuantStats 生成报告 ---
                logger.info("使用 QuantStats 计算详细指标...")
                # 将 equity 曲线转换为日收益率 (如果不是日频数据)
                # 假设 equity_curve 的索引是时间戳
                # if pd.infer_freq(returns_series.index) != 'D':
                #     logger.debug(f"收益率非日频 ({pd.infer_freq(returns_series.index)})，尝试重采样到日频...")
                #     # 注意: resample 可能需要原始 equity 值而不是 pct_change
                #     daily_returns = self.broker.equity_curve['Equity'].resample('D').last().pct_change().dropna()
                #     if daily_returns.empty:
                #          logger.warning("重采样到日频后无数据，回退到原始收益率序列。")
                #          daily_returns = returns_series # Fallback
                # else:
                #     daily_returns = returns_series
                # ^^^ 重采样逻辑可能复杂且依赖数据频率，暂时直接用原始 returns_series ^^^
                # QuantStats 最好处理日收益率，这里直接传递可能导致年化指标不准，需注意
                qs_report_path_html = None
                qs_report_path_json = None # 用于保存 QuantStats 的原始 JSON 输出
                output_dir = Path(self.app_config.get('paths', {}).get('output_dir', 'output')) / 'backtest_reports'
                output_dir.mkdir(parents=True, exist_ok=True)
                strategy_name = self.app_config.get('backtest', {}).get('strategy_name', 'UnknownStrategy')
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_base = f"{strategy_name}_{timestamp_str}"

                try:
                    # 生成 HTML 报告
                    qs_report_path_html = output_dir / f"{filename_base}.html"
                    logger.info(f"生成 QuantStats HTML 报告到: {qs_report_path_html}")
                    qs.reports.html(returns_series, output=str(qs_report_path_html), title=f"{strategy_name} Backtest")

                    # 获取指标字典 (QuantStats 0.0.50+ 可能直接返回 dict)
                    # 或者解析 HTML / 使用内部函数获取?
                    # 尝试获取常用指标
                    metrics_dict = qs.stats.metrics(returns_series, display=False).round(4).to_dict()
                    logger.info(f"QuantStats 计算出的指标: {metrics_dict}")

                except Exception as qs_e:
                     logger.error(f"生成 QuantStats 报告或提取指标时出错: {qs_e}", exc_info=True)
                     metrics_dict = {"error": f"QuantStats execution failed: {qs_e}"}

                # 汇总结果
                self.results = {
                    'initial_cash': self.initial_capital,
                    'final_equity': final_equity,
                    'total_return': total_return,
                    'total_trades': len(self.broker.get_trade_history()) if self.broker and hasattr(self.broker, 'get_trade_history') else 0,
                    'quantstats_metrics': metrics_dict,
                    'quantstats_report_html': str(qs_report_path_html) if qs_report_path_html else None,
                    'expectancy_per_trade': None # Placeholder, calculate below
                }

                # --- 计算期望收益 (Expectancy) ---
                try:
                    win_rate = metrics_dict.get('win_rate')
                    avg_win = metrics_dict.get('avg_win') # 通常是金额
                    avg_loss = metrics_dict.get('avg_loss') # 通常是正数金额
                    if all(v is not None and not pd.isna(v) for v in [win_rate, avg_win, avg_loss]) and avg_loss > 0:
                        # 确保 win_rate 是 0-1 之间 (QuantStats 可能返回 %)
                        if win_rate > 1: win_rate = win_rate / 100.0
                        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
                        self.results['expectancy_per_trade'] = expectancy
                        logger.info(f"计算得到期望收益 (每笔交易): {expectancy:.4f}")
                    else:
                        logger.warning("无法计算期望收益：缺少胜率、平均盈利或平均亏损数据，或平均亏损为零。")
                except Exception as exp_e:
                    logger.error(f"计算期望收益时出错: {exp_e}", exc_info=True)

            except Exception as e:
                logger.error(f"生成结果时发生未知错误: {e}", exc_info=True)
                self.results = {
                    'initial_cash': self.initial_capital,
                    'final_equity': final_equity,
                    'total_return': total_return,
                    'total_trades': len(self.broker.get_trade_history()) if self.broker and hasattr(self.broker, 'get_trade_history') else 0,
                    'error': f'Error during result generation: {e}'
                }

        logger.info("--- 回测结果摘要 ---")
        for key, value in self.results.items():
            if key == 'quantstats_metrics':
                if isinstance(value, dict) and 'error' not in value:
                    # 打印扩展的关键指标
                    logger.info("  关键 QuantStats 指标:")
                    logger.info(f"    年化收益率 (CAGR): {value.get('cagr')}")
                    logger.info(f"    总回报率 (Total Return): {value.get('cumulative_return')}") # QuantStats 可能叫 cumulative_return
                    logger.info(f"    夏普比率 (Sharpe): {value.get('sharpe')}")
                    logger.info(f"    索提诺比率 (Sortino): {value.get('sortino')}")
                    logger.info(f"    卡玛比率 (Calmar): {value.get('calmar')}")
                    logger.info(f"    最大回撤 (Max Drawdown): {value.get('max_drawdown')}")
                    logger.info(f"    胜率 (Win Rate): {value.get('win_rate')}")
                    logger.info(f"    盈亏比 (Profit Factor): {value.get('profit_factor')}")
                    logger.info(f"    平均盈利 (Avg Win): {value.get('avg_win')}")
                    logger.info(f"    平均亏损 (Avg Loss): {value.get('avg_loss')}")
                elif isinstance(value, dict):
                    logger.error(f"  QuantStats 指标计算错误: {value.get('error')}")
                else:
                    logger.info(f"  QuantStats 指标: {value}")
            elif key == 'expectancy_per_trade':
                if value is not None:
                    logger.info(f"  期望收益 (Expectancy): {value:.4f}") # Corrected format specifier
                else:
                    logger.info("  期望收益 (Expectancy): 未能计算")
            else:
                logger.info(f"{key}: {value}")
        logger.info("---------------------")

        # --- 保存结果到 JSON 文件 ---
        self._save_results_to_json()

    def _generate_results_on_error(self, error_message: str) -> dict:
        """
        在发生错误导致回测未能完成时，生成一个包含错误信息的结果字典。
        """
        self.logger.info(f"正在为错误情况生成结果: {error_message}")
        # 获取尽可能多的信息
        final_equity = self.broker.get_equity() if self.broker else self.initial_capital
        total_trades = len(self.broker.get_trade_history()) if self.broker and hasattr(self.broker, 'get_trade_history') else 0
        
        results = {
            'initial_cash': self.initial_capital,
            'final_equity': final_equity,
            'total_return': (final_equity - self.initial_capital) / self.initial_capital if self.initial_capital else 0,
            'total_trades': total_trades,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'annual_return': 0,
            'error': error_message, # 添加错误信息
            'status': 'failed',
            'strategy_name': self.strategy_name,
            'backtest_id': self.backtest_id,
            'quantstats_metrics': 'Error during backtest execution, no metrics calculated.',
            'trades': self.broker.get_trade_history() if self.broker and hasattr(self.broker, 'get_trade_history') else []
        }
        return results

    def _save_results_to_json(self):
        """将回测配置和结果保存到 JSON 文件。"""
        results_dir = Path('backtesting') / 'results'
        results_dir.mkdir(parents=True, exist_ok=True)

        strategy_name = self.app_config.get('backtest', {}).get('strategy_name', 'UnknownStrategy')
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = results_dir / f"{strategy_name}_{timestamp_str}.json"

        # 获取回测配置用于保存，应该从 engine 块获取
        engine_config_save = self.app_config.get('engine', {}) # This should be self.engine_params or related config
        # Let's use the more specific self.engine_params, self.backtest_params
        backtest_run_config = {
            'start_date': self.start_date_str,
            'end_date': self.end_date_str,
            'initial_capital': self.initial_capital,
            'symbols': self.symbols, # Original symbols from config
            'symbols_backtested': self.symbols_to_backtest, # Actual symbols used
            'data_granularity': self.data_granularity,
            'primary_timeframe': self.primary_timeframe,
            'data_padding_days': self.data_padding_days
        }

        data_to_save = {
            'strategy_name': strategy_name,
            'backtest_run_config': backtest_run_config,
            'strategy_params_used': OmegaConf.to_container(
                OmegaConf.select(self.app_config, f"strategy_params.{strategy_name}"), # Get the actual params used by strategy
                resolve=True
            ) if OmegaConf.select(self.app_config, f"strategy_params.{strategy_name}") else {},
            'results': self.results
        }


        # 获取是否保存交易记录的配置
        save_trades_flag = self.engine_params.get('save_trade_history', False)

        # --- Optionally Add Trade History ---
        if save_trades_flag:
            if self.broker and hasattr(self.broker, 'get_trade_history'):
                try:
                    trade_history = self.broker.get_trade_history()
                    # Convert trade objects (assuming they are dict-like or have a to_dict method)
                    serializable_trades = []
                    for trade in trade_history:
                        if isinstance(trade, dict):
                            serializable_trades.append(trade)
                        elif hasattr(trade, 'to_dict') and callable(trade.to_dict):
                            serializable_trades.append(trade.to_dict())
                        else:
                            # Basic conversion if it's an object with attributes
                            # Be careful, this might include unwanted internal stuff
                            try:
                                trade_dict = vars(trade).copy()
                                # Convert unserializable types within the dict if needed
                                for k, v in trade_dict.items():
                                    if isinstance(v, (pd.Timestamp, Path, datetime)):
                                        trade_dict[k] = str(v)
                                    elif hasattr(v, 'value'): # Handle Enums
                                        trade_dict[k] = v.value
                                serializable_trades.append(trade_dict)
                            except TypeError:
                                logger.warning(f"无法将交易记录对象 {type(trade)} 转换为字典进行保存。")
                                serializable_trades.append(str(trade)) # Fallback to string

                    data_to_save['trade_history'] = serializable_trades
                    logger.info(f"已添加 {len(serializable_trades)} 条交易记录到保存结果中。")
                except Exception as trade_e:
                    logger.error(f"处理交易记录用于保存时出错: {trade_e}", exc_info=True)
                    data_to_save['trade_history'] = None
                else:
                    logger.warning("配置要求保存交易记录，但无法从 Broker 获取。")
                    data_to_save['trade_history'] = None
            else:
                data_to_save['trade_history'] = 'Not Saved (config)' # Indicate why it wasn't saved

        # --- 添加资金曲线数据 ---
        if self.broker and hasattr(self.broker, 'equity_curve') and not self.broker.equity_curve.empty:
            try:
                equity_data = self.broker.equity_curve.reset_index()
                equity_data.columns = ['time', 'equity'] # 重命名列
                # 将时间戳转换为 ISO 格式字符串
                equity_data['time'] = equity_data['time'].dt.strftime('%Y-%m-%dT%H:%M:%S%z')
                data_to_save['equity_curve_data'] = equity_data.to_dict('records')
                logger.debug(f"已添加 {len(data_to_save['equity_curve_data'])} 个资金曲线数据点到保存结果中。")
            except Exception as eq_e:
                logger.error(f"处理资金曲线数据用于保存时出错: {eq_e}", exc_info=True)
                data_to_save['equity_curve_data'] = None # Indicate error
            else:
                logger.warning("未找到或资金曲线为空，无法保存资金曲线数据。")
                data_to_save['equity_curve_data'] = None

        try:
            # Convert pandas Series/Timestamps if they exist in results (QuantStats might return them)
            def default_serializer(obj):
                if isinstance(obj, (pd.Timestamp, Path, datetime)):
                    return str(obj)
                elif isinstance(obj, Decimal):
                    # 将 Decimal 转换为字符串以保持精度，或转换为 float (可能损失精度)
                    return str(obj)
                elif isinstance(obj, pd.Series):
                    # 尝试将 Pandas Series 转换为列表或其他可序列化格式
                    try:
                         return obj.tolist()
                    except Exception:
                         return str(obj) # Fallback
                elif isinstance(obj, float) and (pd.isna(obj) or obj == float('inf') or obj == float('-inf')):
                    return str(obj) # Convert NaN/inf to string
                # Let the base class default method raise the TypeError
                try:
                    # 尝试让json库处理其他类型，如果失败则抛出自定义错误
                    return json.JSONEncoder().default(obj)
                except TypeError:
                    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable and not handled by custom serializer")

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4, default=default_serializer)
            logger.info(f"回测结果已成功保存到: {filename}")
        except Exception as e:
            logger.error(f"保存回测结果到 JSON 文件时出错: {e}", exc_info=True)

    def plot_results(self):
        """
        绘制回测结果图表 (例如资金曲线、交易点位等)。
        """
        logger.info("开始绘制回测结果图表...")
        if self.results is None or 'quantstats_metrics' not in self.results:
            logger.warning("没有有效的回测结果或 QuantStats 指标，无法绘制图表。")
            return

        if not self.broker or not hasattr(self.broker, 'equity_curve') or self.broker.equity_curve.empty:
            logger.warning("Broker 未提供有效的资金曲线 (equity_curve)，无法绘制图表。")
            return

        analyzer_config = OmegaConf.select(self.app_config, 'analyzer', default=OmegaConf.create({}))
        should_plot = OmegaConf.select(analyzer_config, 'plot_results', default=False)

        if not should_plot:
            logger.info("根据配置 (analyzer.plot_results)，跳过图表绘制。")
            return

        plot_save_path_str = OmegaConf.select(analyzer_config, 'plot_save_path', default='output/backtest_plots')
        plot_output_dir = Path(plot_save_path_str)
        plot_output_dir.mkdir(parents=True, exist_ok=True) # 创建目录

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"{self.strategy_name}_{timestamp_str}"

        try:
            # 绘制资金曲线图
            equity_curve_fig = self.broker.equity_curve['Equity'].plot(title='Equity Curve').get_figure()
            equity_plot_path = plot_output_dir / f"{filename_base}_equity_curve.png"
            equity_curve_fig.savefig(equity_plot_path)
            logger.info(f"资金曲线图已保存到: {equity_plot_path}")
            # 可以关闭图像以释放内存
            import matplotlib.pyplot as plt
            plt.close(equity_curve_fig)

            # 如果有交易记录，可以尝试绘制交易点位 (需要 K 线数据和交易数据)
            # ... (这部分比较复杂，需要访问原始K线数据和 self.trades)
            logger.info("交易点位图绘制逻辑暂未完全实现。")

        except Exception as e:
            logger.error(f"绘制图表时发生错误: {e}", exc_info=True)

    def _auto_detect_symbols_from_events(self, events_df, map_func):
        """
        (辅助方法) 根据事件数据和映射函数自动检测交易品种。
        Args:
            events_df (pd.DataFrame): 包含事件数据的 DataFrame，需要有 'impacted_currency' 列。
            map_func (callable or dict): 一个函数或字典，用于将货币映射到交易品种。
                                       例如，event_mapping.currency_to_symbol。
        Returns:
            list: 推断出的交易品种列表 (去重)。
        """
        if events_df is None or events_df.empty or 'impacted_currency' not in events_df.columns:
            logger.warning("事件数据为空或缺少 'impacted_currency' 列，无法自动检测交易品种。")
            return []

        detected_symbols = set()
        for currency in events_df['impacted_currency'].unique():
            symbol = None
            if callable(map_func):
                symbol = map_func(currency)
            elif isinstance(map_func, dict):
                symbol = map_func.get(currency)

            if symbol:
                detected_symbols.add(symbol)
        # else: # This else was misaligned, should be outside the loop or not present if only logging failures
        #     logger.debug(f"无法为货币 '{currency}' 映射到交易品种。") # Corrected indentation if it was meant for per-currency failure

        unique_symbols = list(detected_symbols)
        if not unique_symbols and not events_df['impacted_currency'].empty:
             logger.warning(f"已处理 {len(events_df['impacted_currency'].unique())} 种货币，但未能通过映射表 {map_func} 找到任何交易品种。")
        elif unique_symbols:
             logger.info(f"根据事件自动检测到的交易品种: {unique_symbols}")
        return unique_symbols


    def _get_latest_events(self, current_time):
        # ... (This method seems to be for a different event handling logic, ensure it's used correctly or removed if redundant)
        # The main loop in run() method now handles event filtering directly.
        # If this is kept, its purpose and integration need to be clear.
        logger.debug(f"_get_latest_events called for {current_time}, current logic in run() handles this.")
        return None # Or an empty list, depending on expected return type

    def _determine_symbols_to_backtest(self, event_db_path: str, start_date_utc: datetime, end_date_utc: datetime) -> bool:
        """
        确定最终用于回测的交易品种列表。
        如果配置中 backtest.engine.symbols 非空，则优先使用它。
        否则，尝试从经济日历事件和 app_config.event_mapping.currency_to_symbol 自动推断交易品种。
        """
        # 优先从事件数据中提取symbol字段作为交易品种
        try:
            if filter_events_from_db is None:
                self.logger.error("filter_events_from_db 函数未导入，无法加载事件数据。")
                self.all_events_df = pd.DataFrame()
                return False

            self.logger.info(f"尝试加载 {start_date_utc.date()} 到 {end_date_utc.date()} 范围内的事件数据...")
            events_in_range_df = filter_events_from_db(
                db_path=event_db_path,
                start_date=start_date_utc.strftime('%Y-%m-%d'),
                end_date=end_date_utc.strftime('%Y-%m-%d'),
                min_importance=0 # Load all events in range
            )
            
            if events_in_range_df is not None and not events_in_range_df.empty:
                self.all_events_df = events_in_range_df.copy()
                self.logger.info(f"成功加载 {len(self.all_events_df)} 条事件数据。")
                
                # 从事件数据中提取symbol字段
                if 'symbol' in self.all_events_df.columns:
                    self.symbols_to_backtest = list(self.all_events_df['symbol'].unique())
                    self.logger.info(f"从事件数据中提取到 {len(self.symbols_to_backtest)} 个交易品种: {self.symbols_to_backtest}")
                    return True
                else:
                    self.logger.warning("事件数据中没有'symbol'字段，将使用配置中的交易品种。")
            else:
                self.all_events_df = pd.DataFrame()
                self.logger.warning("从数据库加载的事件数据为空或不存在。")
                
        except Exception as e:
            self.logger.error(f"加载事件数据时出错: {e}", exc_info=True)
            self.all_events_df = pd.DataFrame()
            
        # 后备方案：使用配置中的交易品种
        user_specified_symbols = self.symbols
        if user_specified_symbols and len(user_specified_symbols) > 0:
            self.symbols_to_backtest = list(user_specified_symbols)
            self.logger.info(f"使用配置中指定的交易品种: {self.symbols_to_backtest}")
            return True
            
        self.logger.error("无法确定交易品种：既无法从事件数据中提取，配置中也没有指定。")
        # 下面的自动检测逻辑提升一级缩进，去掉 else:，变为主分支代码
        self.logger.info("配置中 'backtest.engine.symbols' 为空或未提供，尝试从经济事件自动检测交易品种...")
        # 1. 从合并后的 app_config 中获取事件到品种的映射
        currency_to_symbol_map_node = OmegaConf.select(self.app_config, 'event_mapping.currency_to_symbol')
        if currency_to_symbol_map_node is None:
            self.logger.error("自动检测交易品种失败：在合并后的配置中未找到 'event_mapping.currency_to_symbol'。请确保 config/event_mapping.yaml 已被加载并包含此节点，或者 backtesting/config/backtest.yaml 中有此配置。")
            return False
        currency_to_symbol_map = OmegaConf.to_container(currency_to_symbol_map_node, resolve=True)
        if not isinstance(currency_to_symbol_map, dict):
            self.logger.error(f"配置中的 'event_mapping.currency_to_symbol' 不是有效的字典类型: {type(currency_to_symbol_map)}. 内容: {currency_to_symbol_map}")
            return False
        if not currency_to_symbol_map:
            self.logger.error("自动检测交易品种失败：'event_mapping.currency_to_symbol' 为空。")
            return False
        self.logger.info(f"用于自动检测的货币到品种映射 (来自 event_mapping.currency_to_symbol): {currency_to_symbol_map}")
        # 2. 从数据库加载指定时间范围内的事件
        try:
            if filter_events_from_db is None:
                self.logger.error("filter_events_from_db 函数未导入，无法从数据库加载事件。")
                return False
            events_in_range_df = filter_events_from_db(
                db_path=event_db_path,
                start_date=start_date_utc.strftime('%Y-%m-%d'),
                end_date=end_date_utc.strftime('%Y-%m-%d'),
                min_importance=0
            )
            if events_in_range_df is not None:
                self.all_events_df = events_in_range_df.copy()
                self.logger.info(f"在 _determine_symbols_to_backtest 中已将加载的事件数据 ({len(self.all_events_df)}条) 存储到 self.all_events_df。")
            else:
                self.all_events_df = pd.DataFrame()
                self.logger.warning("在 _determine_symbols_to_backtest 中，从数据库加载的事件数据为 None。")
        except Exception as e:
            self.logger.error(f"从事件数据库 {event_db_path} 加载事件时出错: {e}", exc_info=True)
            self.all_events_df = pd.DataFrame()
            return False
        if self.all_events_df.empty:
            self.logger.warning(f"在时间范围 {start_date_utc.date()} 到 {end_date_utc.date()} 内未找到经济事件，无法自动推断交易品种。")
            self.symbols_to_backtest = []
            return True
        self.logger.info(f"成功从数据库加载了 {len(self.all_events_df)} 条事件用于品种检测 (通过 self.all_events_df)。")
        if 'Currency' in self.all_events_df.columns and 'impacted_currency' not in self.all_events_df.columns:
            self.logger.info("将 'Currency' 列重命名为 'impacted_currency' 以进行品种检测。")
            self.all_events_df = self.all_events_df.rename(columns={'Currency': 'impacted_currency'})
        elif 'currency' in self.all_events_df.columns and 'impacted_currency' not in self.all_events_df.columns:
            self.logger.info("将 'currency' 列重命名为 'impacted_currency' 以进行品种检测。")
            self.all_events_df = self.all_events_df.rename(columns={'currency': 'impacted_currency'})
        detected_symbols = self._auto_detect_symbols_from_events(self.all_events_df, currency_to_symbol_map)
        if not detected_symbols:
            self.logger.warning("未能从事件中自动检测到任何交易品种。请检查事件数据和映射配置。")
            self.symbols_to_backtest = []
        else:
            self.symbols_to_backtest = detected_symbols
            self.logger.info(f"自动检测到并设置为回测的交易品种: {self.symbols_to_backtest}")
        return True

# (主程序入口注释不变)

# 如果需要直接运行引擎进行测试
# if __name__ == '__main__':
#     # 需要先设置好日志和配置
#     # config = ...
#     # setup_logging(config)
#     # engine = BacktestEngine(config)
#     # results = engine.run()
#     pass
