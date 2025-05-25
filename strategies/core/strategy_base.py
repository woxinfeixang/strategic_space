import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
import pandas as pd
from datetime import datetime
# from .risk_manager import RiskManagerBase, get_risk_manager # <-- 注释掉
from omegaconf import DictConfig, OmegaConf
from decimal import Decimal, InvalidOperation

# --- 添加 Order 类及相关枚举的导入 ---
from strategies.live.order import Order, OrderSide, OrderType, OrderStatus
# ------------------------------------

# MODIFIED: Added os, importlib.util, re for config file loading
import os
import importlib.util
import re

logger = logging.getLogger(__name__)

class StrategyBase(ABC):
    """
    策略的抽象基类。

    所有具体策略都应继承此类并实现 process_new_data 方法。
    该基类提供了与执行引擎交互、管理订单和更新持仓的基础结构。
    """
    def __init__(self, 
                 strategy_id: str,
                 app_config: DictConfig,
                 data_provider: Any, 
                 execution_engine: Any, 
                 risk_manager: Any,
                 live_mode: bool = False):
        """
        初始化策略基类。

        Args:
            strategy_id (str): 策略的唯一标识符 (例如，策略类名 "MyAwesomeStrategy").
            app_config (DictConfig): 完整的应用程序配置对象。
            data_provider (Any): 数据提供者实例。
            execution_engine (Any): 执行引擎实例。
            risk_manager (Any): 风险管理器实例。
            live_mode (bool): 是否为实盘模式。
        """
        self.strategy_id = strategy_id
        self.app_config = app_config 
        self.live_mode = live_mode
        self.data_provider = data_provider
        self.execution_engine = execution_engine
        self.risk_manager = risk_manager
        
        self.logger = logging.getLogger(self.strategy_id)
        self.logger.setLevel(logging.DEBUG) # Ensure DEBUG logs are processed by this logger

        # 1. Get base parameters from app_config.strategy_params.[strategy_id]
        base_params = OmegaConf.create({})
        if hasattr(app_config, 'strategy_params') and app_config.strategy_params is not None:
            # Ensure strategy_params is a DictConfig or dict before calling get
            if isinstance(app_config.strategy_params, (dict, DictConfig)):
                base_params = OmegaConf.create(app_config.strategy_params.get(self.strategy_id, {}))
            else:
                self.logger.warning(
                    f"'{self.strategy_id}': app_config.strategy_params is not a dictionary/DictConfig "
                    f"(type: {type(app_config.strategy_params)}). Cannot get strategy-specific params."
                )
        else:
            self.logger.warning(
                f"'{self.strategy_id}': app_config.strategy_params not found or is None. "
                "Initializing base_params to empty DictConfig."
            )
        
        # 2. Load parameters from the strategy's dedicated config file
        #    The config_key for loading from file is derived from self.strategy_id.
        #    This allows strategies to be identified by their unique strategy_id.
        file_params = self._load_config_from_file(self.strategy_id)

        # 3. Merge: File parameters override base_params from app_config.
        #    self.params will hold the final, merged parameters for the strategy.
        if file_params: # file_params is already OmegaConf.DictConfig or None
            self.params = OmegaConf.merge(base_params, file_params)
            self.logger.info(
                f"Successfully loaded and merged parameters from dedicated config file for '{self.strategy_id}'. "
                "File parameters override any same-named parameters from the main app_config."
            )
        else:
            self.params = base_params # Use only params from app_config if file loading fails or file is empty/not found
            self.logger.info(
                f"No dedicated config file found, loaded, or file was empty for '{self.strategy_id}'. "
                f"Using parameters from main app_config for this strategy (if any)."
            )
        
        # Ensure self.config also points to these final merged params for compatibility if any old code uses self.config
        # However, the primary access should be via self.params.
        # self.config = self.params # This was original: self.params = config; self.config = config.
        # Let self.config point to the full app_config for broader access if needed.
        # And self.params be the specific, merged params for this strategy instance.
        # The original self.config = config (which was strategy-specific params) is now self.params.
        # Let's keep self.config pointing to the full app_config as per the new __init__ structure.
        # No, the original code had self.config = config where config was strategy-specific.
        # So, self.config should also point to the final self.params for max compatibility.
        self.config = self.params

        self.positions: Dict[str, Any] = {} # 用于存储策略视角的持仓信息
        self.logger.info(f"Strategy '{self.strategy_id}' initialized. Final params: {OmegaConf.to_container(self.params) if self.params else '{}'}")

    def get_required_timeframes(self) -> List[str]:
        """
        返回策略执行所需的时间框架列表。
        默认实现会尝试从策略特定参数中获取 'primary_timeframe'，
        然后从全局回测引擎配置中获取 'primary_timeframe'，
        如果都未找到，则默认为 ['M30']。
        子策略应覆盖此方法以指定其确切的时间框架需求，例如 ['M30', 'H1']。
        """
        # 1. 尝试从策略特定参数 self.params 获取
        strategy_primary_tf = self.params.get('primary_timeframe')
        if strategy_primary_tf and isinstance(strategy_primary_tf, str):
            self.logger.debug(f"Strategy '{self.strategy_id}' is using its own primary_timeframe: {strategy_primary_tf}")
            return [strategy_primary_tf]
        
        # 2. 尝试从全局引擎配置 self.app_config 获取
        engine_primary_tf = OmegaConf.select(self.app_config, "backtest.engine.primary_timeframe")
        if engine_primary_tf and isinstance(engine_primary_tf, str):
            self.logger.debug(f"Strategy '{self.strategy_id}' is using engine's primary_timeframe: {engine_primary_tf}")
            return [engine_primary_tf]
            
        # 3. 默认值
        self.logger.debug(f"Strategy '{self.strategy_id}' using default primary_timeframe: M30 (not found in strategy or engine config).")
        return ["M30"]

    def _to_snake_case(self, name: str) -> str:
        """Converts a PascalCase or camelCase string to snake_case."""
        if not name:
            return ""
        # Ensure name is a string
        name_str = str(name)
        # Insert underscore before a capital letter that is preceded by a lowercase letter or digit,
        # or before a capital letter that is followed by a lowercase letter (to handle acronyms like "EURUSD" -> "eurusd")
        s1 = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name_str)
        # Insert underscore before a capital letter that is followed by a lowercase letter,
        # and is not at the beginning of the string (part of an acronym or start of new word)
        s2 = re.sub(r'(?<=[A-Z])([A-Z][a-z])', r'_\1', s1)
        return s2.lower()

    def _load_config_from_file(self, strategy_identifier: str) -> Optional[DictConfig]:
        """
        Dynamically loads parameters from a strategy-specific configuration file.
        The config file is expected to be in strategies/config/{strategy_identifier_snake_case}_config.py.
        Args:
            strategy_identifier (str): The identifier for the strategy (e.g., its class name or unique ID).
        Returns:
            Optional[DictConfig]: Loaded parameters as OmegaConf DictConfig, or None if loading fails.
        """
        if not strategy_identifier:
            self.logger.warning("Cannot load config from file: strategy_identifier is empty.")
            return None

        # Derive snake_case filename from the strategy_identifier
        config_file_name_base = self._to_snake_case(strategy_identifier)
        config_file_name = f"{config_file_name_base}_config.py"
        
        # Construct path relative to the 'strategies' directory.
        # This assumes the CWD or Python's path allows resolution from 'strategies/config/...'.
        # For robustness in different execution environments, an absolute path or a path
        # derived from a known base directory (e.g., a workspace root passed via config) would be better.
        # For now, using relative path as per typical project structure.
        # Using os.path.abspath and __file__ of a known module could make this more robust if needed.
        # Let's assume the execution context allows this relative path.
        current_script_dir = os.path.dirname(os.path.abspath(__file__)) # strategies/core
        workspace_root_guess = os.path.dirname(current_script_dir) # strategies/
        config_file_path = os.path.join(workspace_root_guess, "config", config_file_name)
        
        self.logger.debug(f"Attempting to load config file for '{strategy_identifier}' from resolved path: '{config_file_path}'")

        if not os.path.isfile(config_file_path):
            self.logger.info(f"Dedicated config file not found for '{strategy_identifier}' at '{config_file_path}'.")
            return None

        try:
            # Create a unique module name to avoid import caching issues
            module_name = f"strategy_configs.{config_file_name_base}_config_module"
            
            spec = importlib.util.spec_from_file_location(module_name, config_file_path)
            if spec and spec.loader:
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module) # Execute the config file as a module
                
                loaded_params_dict = {}
                for attr_name in dir(config_module):
                    if not attr_name.startswith("__"): # Exclude built-in/private attributes
                        value = getattr(config_module, attr_name)
                        # We expect config files to define dicts or simple types for parameters
                        loaded_params_dict[attr_name] = value 
                
                if not loaded_params_dict:
                    self.logger.warning(f"Config file '{config_file_path}' for '{strategy_identifier}' was loaded but contained no extractable parameters.")
                    return None
                    
                self.logger.info(f"Successfully parsed parameters from '{config_file_path}' for '{strategy_identifier}'.")
                return OmegaConf.create(loaded_params_dict) # Convert the dict of params to DictConfig
            else:
                self.logger.error(f"Could not create module spec or loader for config file: '{config_file_path}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error loading or parsing config file '{config_file_path}' for '{strategy_identifier}': {e}", exc_info=True)
            return None

    @abstractmethod
    def process_new_data(self, current_time: datetime,
                         market_data: Dict[str, Dict[str, pd.DataFrame]],
                         event_data: Optional[pd.DataFrame]) -> None:
        """
        处理新的市场数据和/或事件数据，生成并执行交易决策。
        这是策略逻辑的核心入口点，由 StrategyOrchestrator 周期性调用。

        Args:
            current_time (datetime): 当前时间 (UTC)。
            market_data (Dict[str, Dict[str, pd.DataFrame]]): 包含所有相关时间和品种的
                                                               最新合并价格数据的嵌套字典。
                                                               结构: market_data[timeframe][symbol] = DataFrame。
                                                               如果某个组合数据获取失败，对应键可能不存在。
            event_data (Optional[pd.DataFrame]): 新产生的相关事件数据 DataFrame。
                                                 如果当前周期没有新事件，则为 None。
        """
        pass

    def update_positions(self, executed_order: Order) -> None:
        """
        根据已执行的订单更新内部持仓状态。
        持仓量为正表示多头，为负表示空头。

        Args:
            executed_order (Order): 已成功执行的订单对象。
        """
        if not executed_order or executed_order.status != OrderStatus.FILLED or executed_order.executed_volume == 0:
            self.logger.debug(f"订单未完全执行或非成交状态，不更新持仓: {executed_order.client_order_id if executed_order else 'N/A'}")
            return

        symbol = executed_order.symbol
        trade_qty = executed_order.executed_volume
        trade_price = executed_order.average_filled_price
        
        if trade_price is None:
            self.logger.error(f"订单 {executed_order.client_order_id} 成交价格未知，无法更新持仓。")
            return

        current_pos = self.positions.get(symbol, {'volume': 0.0, 'average_price': 0.0})
        current_volume = current_pos['volume']
        current_avg_price = current_pos['average_price']
        
        new_volume: float
        new_avg_price: float

        if executed_order.side == OrderSide.BUY:
            new_volume = current_volume + trade_qty
            if current_volume >= 0:  # 原持仓为多头或空仓
                if new_volume != 0: # 避免除以零
                    new_avg_price = (current_avg_price * current_volume + trade_price * trade_qty) / new_volume
                else: # 理论上 current_volume >=0 且 trade_qty > 0, new_volume 不会是0除非 trade_qty 是0 (已被上面检查排除)
                    new_avg_price = 0.0 
            else:  # 原持仓为空头 (current_volume < 0)
                if new_volume == 0: # 空头被完全平仓
                    new_avg_price = 0.0
                elif new_volume > 0: # 空头被平仓后反手做多
                    new_avg_price = trade_price
                else:  # 空头部分平仓 (new_volume < 0 且 new_volume > current_volume)
                    new_avg_price = current_avg_price # 剩余空头成本不变
        
        elif executed_order.side == OrderSide.SELL:
            new_volume = current_volume - trade_qty
            if current_volume <= 0: # 原持仓为空头或空仓
                if new_volume != 0: # 避免除以零 (计算新空头或增加空头的平均成本)
                    # (旧总成本 + 新交易成本) / 新总数量
                    # 旧总成本 = current_avg_price * abs(current_volume)
                    # 新交易成本 = trade_price * trade_qty
                    # 新总数量 = abs(new_volume)
                    new_avg_price = (current_avg_price * abs(current_volume) + trade_price * trade_qty) / abs(new_volume)
                else: # 理论上 current_volume <=0 且 trade_qty > 0, new_volume 不会是0
                    new_avg_price = 0.0
            else: # 原持仓为多头 (current_volume > 0)
                if new_volume == 0: # 多头被完全平仓
                    new_avg_price = 0.0
                elif new_volume < 0: # 多头被平仓后反手做空
                    new_avg_price = trade_price
                else: # 多头部分平仓 (new_volume > 0 且 new_volume < current_volume)
                    new_avg_price = current_avg_price # 剩余多头成本不变
        else:
            self.logger.warning(f"未知的订单方向: {executed_order.side}，无法更新持仓。")
            return

        self.positions[symbol] = {'volume': new_volume, 'average_price': new_avg_price}
        self.logger.info(f"持仓更新: {symbol} | 旧: {{vol:{{current_volume:.4f}}, avg_p:{{current_avg_price:.5f}}}} | 交易: {{side:{{executed_order.side.value}}, vol:{{trade_qty:.4f}}, p:{{trade_price:.5f}}}} | 新: {{vol:{{new_volume:.4f}}, avg_p:{{new_avg_price:.5f}}}}")

    def prepare_order(self, signal_data: Dict[str, Any]) -> Optional[Order]:
        """
        根据策略信号准备标准化的订单对象。
        
        - 会自动为订单生成包含策略名称和时间戳的 client_order_id (格式: {策略名}_{ms时间戳})，
          除非信号数据中已明确提供了 client_order_id。
        - 会自动将策略名称添加到订单的 metadata['strategy_name'] 中。

        Args:
            signal_data (Dict[str, Any]): 包含订单参数的字典，至少应包含
                                           symbol, side, order_type, volume。
                                           side 和 order_type 应为对应的枚举类型 (OrderSide, OrderType)。
                                           可以包含可选的 limit_price, stop_price,
                                           stop_loss, take_profit, client_order_id 等。

        Returns:
            Optional[Order]: 标准化的订单对象, 如果信号无效则返回 None。
        """
        try:
            required_keys = ['symbol', 'side', 'order_type', 'volume']
            missing_keys = [k for k in required_keys if k not in signal_data]
            if missing_keys:
                self.logger.error(f"准备订单失败：信号数据缺少必要字段: {', '.join(missing_keys)}。信号: {signal_data}")
                return None

            # 基本类型和值检查
            if not isinstance(signal_data['symbol'], str) or not signal_data['symbol']:
                self.logger.error(f"准备订单失败：'symbol' 必须为非空字符串。信号: {signal_data}")
                return None
            if not isinstance(signal_data['side'], OrderSide):
                self.logger.error(f"准备订单失败：'side' 必须为 OrderSide 枚举类型。信号: {signal_data}")
                return None
            if not isinstance(signal_data['order_type'], OrderType):
                self.logger.error(f"准备订单失败：'order_type' 必须为 OrderType 枚举类型。信号: {signal_data}")
                return None
            if not isinstance(signal_data['volume'], (float, int)) or signal_data['volume'] <= 0:
                self.logger.error(f"准备订单失败：'volume' 必须为正数。信号: {signal_data}")
                return None


            client_id = signal_data.get('client_order_id', f"{self.strategy_id}_{int(datetime.now().timestamp() * 1000)}")
            
            custom_metadata = signal_data.get('metadata', {})
            if not isinstance(custom_metadata, dict):
                self.logger.warning(f"信号数据中的 'metadata' 不是字典类型，将使用空字典。信号 'metadata': {custom_metadata}")
                custom_metadata = {}
            custom_metadata['strategy_name'] = self.strategy_id

            order_instance = Order(
                symbol=str(signal_data['symbol']),
                side=signal_data['side'],
                order_type=signal_data['order_type'],
                volume=float(signal_data['volume']),
                client_order_id=client_id,
                limit_price=float(signal_data['limit_price']) if signal_data.get('limit_price') is not None else None,
                stop_price=float(signal_data.get('stop_price')) if signal_data.get('stop_price') is not None else None,
                stop_loss=float(signal_data.get('stop_loss')) if signal_data.get('stop_loss') is not None else None,
                take_profit=float(signal_data.get('take_profit')) if signal_data.get('take_profit') is not None else None,
                metadata=custom_metadata
                # OrderStatus 默认为 NEW，creation_time 默认为 utcnow()
            )
            
            self.logger.debug(f"准备订单: {order_instance.client_order_id} for strategy {self.strategy_id} - {order_instance.to_dict()}")
            return order_instance
            
        except KeyError as e: # 应该被上面的 missing_keys 检查捕获
            self.logger.error(f"准备订单失败：信号数据处理时发生 KeyError {e}。信号: {signal_data}")
            return None
        except ValueError as e: # 例如，float转换失败
             self.logger.error(f"准备订单失败：信号数据值无效或类型转换失败 {e}。信号: {signal_data}")
             return None
        except Exception as e:
            self.logger.error(f"准备订单时发生未知错误: {e}", exc_info=True)
            return None

    def place_order_from_signal(self, signal_data: Dict[str, Any]) -> Optional[Order]:
        """
        根据信号数据准备并尝试通过执行引擎下单。
        如果信号数据中 'volume' 为 None 或 0，则会尝试使用风险管理器计算手数。
        """
        if self.risk_manager and (signal_data.get('volume') is None or signal_data.get('volume') == 0):
            self.logger.info(f"订单 {signal_data.get('client_order_id', 'N/A')} 手数未指定或为0，尝试使用风险管理器计算。")
            
            # 准备风险计算所需的参数
            risk_calc_signal = {
                'symbol': signal_data.get('symbol'),
                'stop_loss': signal_data.get('stop_loss'),
                'side': signal_data.get('side'), # 期望是 OrderSide 枚举
                'entry_price': signal_data.get('limit_price') or signal_data.get('stop_price'), # 市价单可能没有预设入场价
                'strategy_name': self.strategy_id
            }

            # 检查必要参数
            required_for_calc = ['symbol', 'stop_loss', 'side']
            if any(risk_calc_signal.get(k) is None for k in required_for_calc):
                self.logger.error(f"风险计算失败：缺少必要参数 (symbol, stop_loss, side)。信号: {risk_calc_signal}")
                return None

            try:
                # 1. 获取账户净值
                account_equity_decimal = self.execution_engine.get_equity()
                if account_equity_decimal is None:
                    self.logger.error("无法从执行引擎获取账户净值，手数计算中止。")
                    return None
                
                # 2. 获取合约大小
                symbol_info = self.data_provider.market_provider.get_symbol_info(risk_calc_signal['symbol'])
                if not symbol_info:
                    self.logger.error(f"无法获取品种 {risk_calc_signal['symbol']} 的规格信息，手数计算中止。")
                    return None
                
                # 使用 'trade_contract_size'，如果不存在，则用风险管理器的默认值
                # 新的 RiskManager 实例现在是 self.risk_manager，它有 default_contract_size 属性
                contract_size_str = str(symbol_info.get('trade_contract_size', self.risk_manager.default_contract_size if self.risk_manager else "1"))
                contract_size_val = Decimal(contract_size_str)

                # 3. 确定入场价 (如果信号中没有，例如市价单，RiskManager 可能需要估算)
                # 新的 RiskManager.calculate_order_volume 需要 entry_price
                # 如果 risk_calc_signal['entry_price'] 是 None，我们需要一个估算。
                # 然而，当前版本的 RiskManager 需要明确的 entry_price。
                # 我们假设对于市价单，策略层面应该已经有了一个预期的入场价估算，或者在 backtest.yaml 中配置。
                # 如果 entry_price 为 None，这里的 calculate_order_volume 可能会失败或返回0。
                # 这里的 signal_data 通常是 prepare_order 之前的，prepare_order 会处理市价单的 entry_price。
                # 但 volume 计算在 prepare_order 之前。
                # 策略在生成 signal_data 时，即使是市价单，也应提供一个近似的 entry_price 用于风险计算。
                # 或者，RiskManager 需要有能力在 entry_price 为 None 时，自行从 data_provider 获取当前市场价。
                # 当前 RiskManager.calculate_order_volume 强制要求 entry_price。
                
                entry_price_val = risk_calc_signal.get('entry_price')
                if entry_price_val is None:
                    self.logger.error(
                        f"风险计算失败：信号 {risk_calc_signal.get('symbol', 'N/A')} 未提供有效的 entry_price (例如从 signal_data['limit_price'] 或 signal_data['stop_price'] 或预估的市价价格)。"
                        f"手数计算中止。"
                    )
                    return None # 中止手数计算

                try:
                    entry_price_decimal = Decimal(str(entry_price_val))
                    stop_loss_decimal = Decimal(str(risk_calc_signal['stop_loss']))
                except InvalidOperation as e:
                    self.logger.error(f"手数计算时，入场价或止损价转换为 Decimal 失败: {e}. Entry: {entry_price_val}, SL: {risk_calc_signal.get('stop_loss', 'N/A')}", exc_info=True)
                    return None
                
                # 确保 side 是 OrderSide 枚举
                side_enum = risk_calc_signal['side']
                if not isinstance(side_enum, OrderSide):
                    self.logger.error(f"手数计算的 side 类型错误: {type(side_enum)}，期望 OrderSide。")
                    return None

                self.logger.debug(
                    f"调用 RiskManager.calculate_order_volume 参数: "
                    f"equity={account_equity_decimal}, entry={entry_price_decimal}, "
                    f"sl={stop_loss_decimal}, side={side_enum}, contract_size={contract_size_val}"
                )

                calculated_volume_decimal = self.risk_manager.calculate_order_volume(
                    account_equity=account_equity_decimal,
                    entry_price=entry_price_decimal, # 确保是 Decimal
                    stop_loss_price=stop_loss_decimal, # 确保是 Decimal
                    side=side_enum, # 确保是 OrderSide 枚举
                    contract_size=contract_size_val # 确保是 Decimal
                )
                
                new_volume = float(calculated_volume_decimal)
                self.logger.info(f"风险管理器计算出的手数: {new_volume} (来自 Decimal: {calculated_volume_decimal})")

                if new_volume > 0:
                    signal_data['volume'] = new_volume
                else:
                    self.logger.warning(f"风险管理器计算出的手数为 {new_volume}，订单中止。信号: {signal_data}")
                    return None # 中止订单
            
            except InvalidOperation as e: # 处理 Decimal 转换错误
                self.logger.error(f"手数计算时发生 Decimal 转换错误: {e}. Signal: {signal_data}, RiskCalc: {risk_calc_signal}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"使用风险管理器计算手数时出错: {e}. Signal: {signal_data}, RiskCalc: {risk_calc_signal}", exc_info=True)
                return None
        
        # 准备订单对象
        order = self.prepare_order(signal_data)
        if not order:
            self.logger.error(f"订单准备失败。Signal: {signal_data}")
            return None

        try:
            # --- 修改：调用 execution_engine.submit_order ---
            # 假设 submit_order 返回包含订单状态和ID的字典或更新后的Order对象
            # result = self.execution_engine.place_order(order) # 旧的调用
            if hasattr(self.execution_engine, 'submit_order'):
                submitted_order_info = self.execution_engine.submit_order(order)
            elif hasattr(self.execution_engine, 'place_order'): # 后备到 place_order
                self.logger.warning("ExecutionEngine 没有 submit_order 方法，尝试使用 place_order。")
                submitted_order_info = self.execution_engine.place_order(order)
            else:
                self.logger.error("ExecutionEngine 既没有 submit_order 也没有 place_order 方法。无法提交订单。")
                return None # 或者根据情况返回原始 order 对象，表示已准备但未提交
            # --- 修改结束 ---

            if submitted_order_info:
                # TODO: 根据执行引擎的返回结果更新 order 对象的状态或创建一个新的已提交 Order 对象
                # 例如，如果 submitted_order_info 是一个包含 server_order_id 和 status 的字典:
                if isinstance(submitted_order_info, dict):
                    order.server_order_id = submitted_order_info.get('order_id', order.server_order_id)
                    # 更新状态，如果执行引擎立即返回状态的话
                    # new_status_str = submitted_order_info.get('status')
                    # if new_status_str:
                    #     try:
                    #         order.status = OrderStatus[new_status_str.upper()]
                    #     except KeyError:
                    #         self.logger.warning(f"从执行引擎返回了未知的订单状态字符串: {new_status_str}")
                    self.logger.info(f"订单已提交到执行引擎: ClientID={order.client_order_id}, ServerID={order.server_order_id}, Details: {submitted_order_info}")

                elif isinstance(submitted_order_info, Order): # 如果返回的是更新后的Order对象
                    order = submitted_order_info # 直接使用返回的更新后的 Order 对象
                    self.logger.info(f"订单已提交到执行引擎并更新: ClientID={order.client_order_id}, ServerID={order.server_order_id}, Status={order.status.value}")
                
                return order # 返回准备好的、可能已被执行引擎部分更新的订单对象
            else:
                self.logger.error(f"订单提交失败，执行引擎未返回有效信息。ClientID={order.client_order_id}")
                # 订单已准备但提交失败，可以考虑返回 order 让调用方知道，或者返回 None
                return None # 表示提交失败
        except Exception as e:
            self.logger.error(f"提交订单 {order.client_order_id if order else 'N/A'} 时发生异常: {e}", exc_info=True)
            return None

    @classmethod
    def get_name(cls) -> str:
        """获取策略类的名称。"""
        return cls.__name__

    # ---- 旧的下单和手数计算方法 (可能需要审阅或废弃) ----
    def _place_order(self, symbol: str, side: str, entry_price: float, current_bar_time: datetime, stop_loss_price: float, take_profit_price: float, comment: str):
        """
        【已废弃或内部使用】旧的下单接口，具体策略不应直接调用此方法。
        应通过构建 signal_data 并调用 place_order_from_signal。
        """
        self.logger.warning(f"[{self.strategy_id}] _place_order 被直接调用 (Symbol: {symbol}, Side: {side})。此方法可能已废弃或仅供内部兼容。推荐使用 place_order_from_signal。")
        # 简单的信号构建，实际应由具体策略逻辑完成
        signal = {
            'symbol': symbol,
            'side': OrderSide.BUY if side.upper() == 'BUY' else OrderSide.SELL if side.upper() == 'SELL' else None,
            'order_type': OrderType.MARKET,
            'volume': 0,  # 设置为0以触发 place_order_from_signal 中的手数计算
            'entry_price': entry_price, # 旧接口有，新接口中 entry_price 通常从 metadata 或市价获取
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'metadata': {'comment': comment, 'triggered_at_bar': current_bar_time}
        }
        if signal['side'] is None:
            self.logger.error(f"_place_order 中无效的 side: {side}")
            return
        self.place_order_from_signal(signal)

    def _calculate_order_size(self, symbol: str, entry_price: float, stop_loss_price: float, account_currency: str = 'USD') -> Optional[float]:
        """
        【已废弃】手数计算逻辑已移至 place_order_from_signal 方法内部，通过 RiskManager 计算。
        此方法不应再被直接调用。
        """
        self.logger.warning(
            f"[{self.strategy_id}] _calculate_order_size 被直接调用。"
            f"手数计算逻辑已移至 place_order_from_signal 方法内部，通过 RiskManager 计算。此方法不再执行实际计算。"
        )
        # 为了避免意外破坏仍然调用此方法的旧代码 (如果有的话)，可以返回一个明确的 None 或 0，
        # 或者如果 place_order_from_signal 能够处理 signal_data 中 volume 为 None/0 的情况，这里返回0是安全的。
        return 0 # 返回0，以期望 place_order_from_signal 进行实际计算

    def _get_pip_size(self, symbol: str) -> float:
        """
        获取指定品种的点（pip）大小。

        尝试从 DataProvider 获取精确的 tick_size (通常等同于 pip_size)。
        如果失败，则回退到基于品种名称的常见估算值。

        Args:
            symbol (str): 交易品种，例如 "EURUSD"。

        Returns:
            float: 该品种的点大小。
        """
        pip_size_default = 0.0001 # 大多数货币对
        if "JPY" in symbol.upper():
            pip_size_default = 0.01 # 日元对

        if not self.data_provider:
            self.logger.warning(f"[{self.strategy_id}] DataProvider 未初始化，无法获取 {symbol} 的精确 pip_size。使用默认值: {pip_size_default}")
            return pip_size_default

        try:
            # 优先尝试从 market_provider 获取
            market_provider = getattr(self.data_provider, 'market_provider', self.data_provider)
            
            if hasattr(market_provider, 'get_symbol_info') and callable(market_provider.get_symbol_info):
                symbol_info = market_provider.get_symbol_info(symbol)
                if symbol_info and isinstance(symbol_info, dict) and 'tick_size' in symbol_info and isinstance(symbol_info['tick_size'], (float, int)) and symbol_info['tick_size'] > 0:
                    tick_s = float(symbol_info['tick_size'])
                    self.logger.debug(f"[{self.strategy_id}] 从 DataProvider 获取到 {symbol} 的 tick_size: {tick_s}")
                    return tick_s
                else:
                    self.logger.warning(f"[{self.strategy_id}] DataProvider.get_symbol_info({symbol}) 未返回有效 tick_size 或 tick_size 非正数。Info: {symbol_info}。使用默认值: {pip_size_default}")
            else:
                self.logger.warning(f"[{self.strategy_id}] DataProvider (或其 market_provider) 缺少 get_symbol_info 方法或该方法不可调用，无法获取 {symbol} 的精确 pip_size。使用默认值: {pip_size_default}")
        except Exception as e:
            self.logger.error(f"[{self.strategy_id}] 调用 DataProvider 获取 {symbol} 的 pip_size 时出错: {e}。使用默认值: {pip_size_default}", exc_info=True)
        
        return pip_size_default

    def _map_event_to_symbol(self, event_data: pd.Series) -> Optional[str]:
        """
        """
        pass