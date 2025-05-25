import logging
import time
from typing import Dict, List, Optional, Any
import pandas as pd
from omegaconf import OmegaConf, DictConfig
import os # For getenv
from datetime import datetime

# 假设基类和 Order 定义可导入
from .execution_engine import ExecutionEngineBase
from .order import Order, OrderStatus, OrderSide, OrderType

# 尝试导入 MT5 库和核心工具
try:
    import MetaTrader5 as mt5
    from core.utils import initialize_mt5, shutdown_mt5, MT5_AVAILABLE, setup_logging # Import setup_logging
except ImportError as e:
    # Basic logging setup if core.utils fails
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.error(f"无法导入 MetaTrader5 或 core.utils: {e}. MT5ExecutionEngine 将不可用。", exc_info=True)
    mt5 = None
    MT5_AVAILABLE = False
    # Define stubs if needed for class definition
    def initialize_mt5(*args, **kwargs): return False
    def shutdown_mt5(*args, **kwargs): pass
    # Fallback logger setup
    def setup_logging(log_config, log_filename, logger_name):
        logger = logging.getLogger(logger_name)
        if not logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

class MT5ExecutionEngine(ExecutionEngineBase):
    """
    使用 MetaTrader 5 作为交易执行后端。
    处理与 MT5 API 的连接、下单、订单查询和持仓获取。
    支持基于策略名称的魔术数字管理。
    """
    def __init__(self, config: DictConfig):
        """
        初始化 MT5 执行引擎。

        Args:
            config (DictConfig): 全局合并后的配置对象。
        """
        # We need a logger before super().__init__ if config access fails
        self.logger = logging.getLogger(self.__class__.__name__)

        # Try to get execution config safely
        self.mt5_connect_config = OmegaConf.select(config, "execution.mt5", default=None)
        if not self.mt5_connect_config:
            self.logger.critical("配置中缺少 'execution.mt5' 部分。无法初始化 MT5 引擎。")
            raise ValueError("MT5 configuration missing in 'execution.mt5' section.")

        # Now setup logger properly using config (call super() first to set self.config)
        super().__init__(config) # This sets self.config=config
        log_filename = OmegaConf.select(self.config, "logging.mt5_engine_log_filename", default="mt5_engine.log")
        # Re-assign self.logger with the properly configured one
        self.logger = setup_logging(self.config.logging, log_filename, logger_name=self.__class__.__name__)

        if not MT5_AVAILABLE:
            self.logger.critical("MetaTrader5 库不可用。MT5ExecutionEngine 无法运行。")
            raise ImportError("MetaTrader5 library is required for MT5ExecutionEngine but not found.")

        # 从配置安全地读取参数
        self.terminal_path = self.mt5_connect_config.get('terminal_path')
        self.login = self.mt5_connect_config.get('login')
        # 从环境变量读取密码, fallback to config (though not recommended)
        self.password = os.getenv('MT5_PASSWORD', self.mt5_connect_config.get('password', ''))
        self.server = self.mt5_connect_config.get('server')
        self.deviation_points = self.mt5_connect_config.get('deviation_points', 10)
        # Get default magic number from mt5 specific config if available
        self.default_magic_number = self.mt5_connect_config.get('magic_number', 0)
        self.symbol_map = self.mt5_connect_config.get('symbol_map', {}) # Symbol mapping
        # Get strategy specific params for magic number lookup later
        self.strategy_params = OmegaConf.select(config, 'strategy_params', default=OmegaConf.create({}))

        if not self.default_magic_number:
            self.logger.warning("未在 execution.mt5 配置中指定 default_magic_number。默认为 0。")
            self.default_magic_number = 0

        self.connected = False
        # --- 新增: Client Order ID 到 Broker Ticket ID 的映射 ---
        self.client_to_broker_id_map: Dict[str, int] = {}
        # ----------------------------------------------------------

        self.logger.info("MT5ExecutionEngine initialized.")
        if not self.password:
            self.logger.warning("MT5 密码为空。请设置 MT5_PASSWORD 环境变量或在配置中提供密码 (不推荐)。")

    def _get_strategy_magic_number(self, strategy_name: Optional[str] = None) -> int:
        """
        根据策略名称从配置中获取魔术数字。
        如果策略名称未提供或未找到特定配置，则返回默认魔术数字。
        """
        if strategy_name:
            strategy_config = self.strategy_params.get(strategy_name)
            if strategy_config:
                magic = strategy_config.get('magic_number')
                if magic is not None:
                    try:
                        magic_int = int(magic)
                        self.logger.debug(f"为策略 '{strategy_name}' 找到魔术数字: {magic_int}")
                        return magic_int
                    except (ValueError, TypeError):
                         self.logger.error(f"策略 '{strategy_name}' 的魔术数字配置 '{magic}' 不是有效的整数。将使用默认值。")
                else:
                     self.logger.warning(f"策略 '{strategy_name}' 的配置中未找到 'magic_number'，将使用默认值。")
            else:
                self.logger.warning(f"未找到策略 '{strategy_name}' 的参数配置，将使用默认魔术数字。")

        self.logger.debug(f"使用默认魔术数字: {self.default_magic_number}")
        return self.default_magic_number

    def _map_symbol_to_mt5(self, symbol: str) -> str:
        """将内部标准品种名称映射到 MT5 特定名称。"""
        mt5_symbol = self.symbol_map.get(symbol, symbol)
        if mt5_symbol != symbol:
            self.logger.debug(f"将品种 '{symbol}' 映射到 MT5 品种 '{mt5_symbol}'")
        return mt5_symbol

    def _map_symbol_from_mt5(self, mt5_symbol: str) -> str:
        """将 MT5 特定品种名称映射回内部标准名称。"""
        # Invert the map (be careful if mappings are not one-to-one)
        # Consider caching the inverted map if called frequently
        inv_map = {v: k for k, v in self.symbol_map.items()}
        internal_symbol = inv_map.get(mt5_symbol, mt5_symbol)
        if internal_symbol != mt5_symbol:
             self.logger.debug(f"将 MT5 品种 '{mt5_symbol}' 映射回内部品种 '{internal_symbol}'")
        return internal_symbol

    def connect(self) -> None:
        """建立到 MT5 终端的连接。"""
        if self.connected:
            self.logger.info("MT5 engine is already connected.")
            return

        self.logger.info("正在连接到 MT5...")
        # Construct connect_params dict carefully
        connect_params = {}
        if self.terminal_path: connect_params['path'] = self.terminal_path
        # Ensure login is int if present
        if self.login is not None:
            try:
                connect_params['login'] = int(self.login)
            except (ValueError, TypeError):
                self.logger.error(f"MT5 登录 ID '{self.login}' 无效，无法连接。")
                return # Or raise error
        if self.password: connect_params['password'] = self.password
        if self.server: connect_params['server'] = self.server
        # Add timeout from config if needed by initialize_mt5
        timeout = self.mt5_connect_config.get('timeout')
        if timeout: connect_params['timeout'] = timeout

        # Pass self.logger to the utility function
        self.connected = initialize_mt5(self.logger, connect_params)

        if self.connected:
            account_info = mt5.account_info()
            if account_info:
                self.logger.info(f"MT5 连接成功。账户: {account_info.login}, 服务器: {account_info.server}, 余额: {account_info.balance:.2f} {account_info.currency}")
            else:
                # MT5 connection might be ok even if account_info fails initially
                self.logger.warning("MT5 已连接，但获取账户信息失败 (可能是暂时性问题)。")
        else:
            self.logger.error("MT5 连接失败。请检查 MT5 终端是否运行、配置是否正确以及网络连接。")
            # Consider raising an exception if connection is critical
            # raise ConnectionError("Failed to connect to MetaTrader 5")

    def disconnect(self) -> None:
        """断开与 MT5 终端的连接。"""
        if self.connected:
            self.logger.info("正在断开 MT5 连接...")
            # Pass self.logger to the utility function
            shutdown_mt5(self.logger)
            self.connected = False
            self.logger.info("MT5 连接已断开。")
        else:
             self.logger.info("MT5 engine is not connected.")

    def place_order(self, order: Order) -> Optional[Order]:
        """提交订单到 MT5。"""
        if not self.connected:
            self.logger.error("无法下单：未连接到 MT5。")
            order.status = OrderStatus.REJECTED
            return order

        mt5_symbol = self._map_symbol_to_mt5(order.symbol)
        symbol_info = mt5.symbol_info(mt5_symbol)
        if symbol_info is None:
            self.logger.error(f"无法获取品种信息 '{mt5_symbol}' ({order.symbol})。订单 {order.client_order_id} 被拒绝。")
            order.status = OrderStatus.REJECTED
            return order

        self.logger.info(f"准备向 MT5 下单: {order.to_dict()}")

        # 使用 client_order_id 的哈希值作为 magic number
        # 确保为正数并限制在 32 位正整数范围内
        magic = abs(hash(order.client_order_id)) % (2**31 - 1)
        self.logger.debug(f"Generated magic number: {magic} from client_order_id: {order.client_order_id}")

        # 将 client_order_id 存储在内部映射中
        self.client_to_broker_id_map[order.client_order_id] = magic

        # 构建 MT5 请求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": float(order.volume),
            "type": mt5.ORDER_TYPE_BUY if order.side == OrderSide.BUY else mt5.ORDER_TYPE_SELL,
            "magic": magic, # 使用生成的 magic number
            "comment": order.client_order_id, # 将 client_order_id 放入 comment
            "deviation": self.deviation_points, # For market orders
            "type_time": mt5.ORDER_TIME_GTC, # Default time in force
            "type_filling": mt5.ORDER_FILLING_IOC, # Default filling type (configurable?)
        }

        # 添加价格、止损、止盈 (如果适用)
        if order.order_type == OrderType.LIMIT or order.order_type == OrderType.STOP:
            request["price"] = float(order.limit_price) if order.order_type == OrderType.LIMIT else float(order.stop_price)
        if order.stop_loss:
            request["sl"] = float(order.stop_loss)
        if order.take_profit:
            request["tp"] = float(order.take_profit)

        # 发送订单请求
        result = None
        try:
            result = mt5.order_send(request)
        except Exception as e:
             self.logger.error(f"调用 mt5.order_send 时发生异常 for request {request}: {e}", exc_info=True)
             order.status = OrderStatus.REJECTED # Assume rejection on exception
             return order

        if result is None:
            error_code = mt5.last_error()
            self.logger.error(f"MT5 order_send 失败。订单: {order.client_order_id}, 错误: {error_code} - {self._parse_retcode(error_code)}")
            # 更新内部状态为 REJECTED
            self.client_to_broker_id_map.pop(order.client_order_id)
            order.status = OrderStatus.REJECTED
            return order

        # 订单发送成功，记录 MT5 ticket ID
        mt5_ticket_id = result.order
        self.logger.info(f"MT5 order_send 成功。Client Order ID: {order.client_order_id}, MT5 Ticket ID: {mt5_ticket_id}, Magic: {magic}, Comment: {result.comment}")

        # 更新内部映射，关联 MT5 ticket ID
        self.client_to_broker_id_map[order.client_order_id] = mt5_ticket_id
        order.order_id = str(mt5_ticket_id) # 将 MT5 ticket ID 存为 broker_order_id
        order.status = OrderStatus.NEW
        order.last_update_time = datetime.utcnow() # 保持 order 对象使用 UTC

        return order

    def _get_ticket_from_client_id(self, client_order_id: str) -> Optional[int]:
        """尝试从内存映射或挂单评论中查找与 client_order_id 对应的 MT5 ticket。"""
        if not self.connected: return None

        # 1. 检查内存映射 (最快)
        if client_order_id in self.client_to_broker_id_map:
            ticket = self.client_to_broker_id_map[client_order_id]
            self.logger.debug(f"从内存映射找到 Client ID {client_order_id} 对应的 Ticket ID: {ticket}")
            return ticket

        # 2. 如果映射中没有，尝试通过评论搜索挂单 (效率较低)
        self.logger.debug(f"在内存映射中未找到 Client ID {client_order_id}，尝试通过评论搜索挂单...")
        try:
            orders = mt5.orders_get() # Get all open orders
            if orders:
                for o in orders:
                    if o.comment == client_order_id:
                        # 假设 client_order_id 是唯一的
                        self.logger.debug(f"在挂单中通过评论找到 Client ID {client_order_id} 对应的 Ticket ID: {o.ticket}")
                        # Optionally add to map for future lookups?
                        try:
                           ticket_id = int(o.ticket)
                           self.client_to_broker_id_map[client_order_id] = ticket_id # Cache it
                           return ticket_id
                        except (ValueError, TypeError):
                           self.logger.error(f"找到匹配评论的订单，但其 Ticket '{o.ticket}' 无效。")
                           return None # Found match but invalid ticket
                self.logger.debug(f"在挂单中未找到匹配评论 '{client_order_id}' 的订单。")
            else:
                 self.logger.debug("mt5.orders_get() 未返回任何挂单用于搜索。")

        except Exception as e:
             self.logger.error(f"通过评论搜索挂单时出错 for client ID {client_order_id}: {e}", exc_info=True)

        # 3. 未实现通过评论搜索历史订单 (非常慢)
        self.logger.warning(f"在挂单中未找到 Client ID '{client_order_id}' 对应的 Ticket ID。未实现通过评论搜索历史订单。")
        return None

    def cancel_order(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> bool:
        """取消一个挂单。"""
        if not self.connected:
            self.logger.error("无法取消订单：未连接到 MT5。")
            return False

        ticket_to_cancel: Optional[int] = None

        # 优先级：order_id > client_order_id (via map/search)
        if order_id:
             try:
                 ticket_to_cancel = int(order_id)
                 self.logger.debug(f"准备取消订单，使用提供的 Order ID (Ticket): {ticket_to_cancel}")
             except (ValueError, TypeError):
                 self.logger.error(f"提供的 Order ID '{order_id}' 不是有效的整数 Ticket ID。")
                 return False
        elif client_order_id:
            self.logger.debug(f"准备取消订单，使用提供的 Client Order ID: {client_order_id}")
            ticket_to_cancel = self._get_ticket_from_client_id(client_order_id)
            if ticket_to_cancel is None:
                 self.logger.error(f"无法找到 Client ID '{client_order_id}' 对应的 MT5 Ticket。取消失败。")
                 return False
        else:
            self.logger.error("取消订单需要提供 order_id (ticket) 或 client_order_id。")
            return False

        # Sanity check
        if ticket_to_cancel is None:
            self.logger.error(f"未能确定要取消的订单 Ticket ID from input (order_id='{order_id}', client_order_id='{client_order_id}')")
            return False

        # 构建取消请求
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket_to_cancel,
            # "comment": "Cancelled by system" # Optional comment
        }

        self.logger.info(f"发送取消请求到 MT5 for Ticket {ticket_to_cancel}: {request}")
        result = None
        try:
            result = mt5.order_send(request)
        except Exception as e:
             self.logger.error(f"调用 mt5.order_send 取消订单 {ticket_to_cancel} 时发生异常: {e}", exc_info=True)
             return False

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.logger.info(f"订单 Ticket {ticket_to_cancel} 已成功取消。Retcode: {result.retcode}, Comment: {result.comment}")
            # --- 从映射中移除 (如果存在) ---
            # Find client_id associated with this ticket to remove from map
            client_id_to_remove = None
            for cid, tid in self.client_to_broker_id_map.items():
                 if tid == ticket_to_cancel:
                     client_id_to_remove = cid
                     break
            if client_id_to_remove:
                 # Use pop for safe removal
                 removed_ticket = self.client_to_broker_id_map.pop(client_id_to_remove, None)
                 if removed_ticket:
                      self.logger.debug(f"已从映射中移除 Client ID {client_id_to_remove} (Ticket: {ticket_to_cancel})")
                 else:
                      self.logger.warning(f"尝试从映射移除 Client ID {client_id_to_remove}，但它不存在。")

            # Also try removing using the original client_order_id if provided
            elif client_order_id:
                removed_ticket = self.client_to_broker_id_map.pop(client_order_id, None)
                if removed_ticket:
                    self.logger.debug(f"已从映射中移除 Client ID {client_order_id} (Ticket: {ticket_to_cancel})")

            # ----------------------------------
            return True
        else:
            retcode = result.retcode if result else 'N/A'
            retcode_msg = self._parse_retcode(retcode) if isinstance(retcode, int) else 'N/A'
            comment = result.comment if result else 'N/A'
            self.logger.error(f"取消订单 Ticket {ticket_to_cancel} 失败。Retcode: {retcode} ({retcode_msg}), Comment: {comment}")
            # 检查是否订单已不存在 (可能已成交或之前已取消)
            if result and result.retcode == mt5.TRADE_RETCODE_INVALID_ORDER:
                 self.logger.warning(f"取消失败可能是因为订单 Ticket {ticket_to_cancel} 已不存在。")
                 # Attempt to remove from map anyway if we know the client_id
                 client_id_to_remove = None
                 for cid, tid in self.client_to_broker_id_map.items():
                      if tid == ticket_to_cancel:
                          client_id_to_remove = cid
                          break
                 if client_id_to_remove:
                      removed_ticket = self.client_to_broker_id_map.pop(client_id_to_remove, None)
                      if removed_ticket:
                           self.logger.debug(f"Removed non-existent order {ticket_to_cancel} (Client ID: {client_id_to_remove}) from map.")
                 elif client_order_id: # Try original client_id if ticket search failed
                      removed_ticket = self.client_to_broker_id_map.pop(client_order_id, None)
                      if removed_ticket:
                           self.logger.debug(f"Removed non-existent order (Ticket unknown, Client ID: {client_order_id}) from map.")

            return False

    def get_order_status(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[Order]:
        """获取订单状态。"""
        if not self.connected:
            self.logger.error("无法获取订单状态：未连接到 MT5。")
            return None

        ticket_to_find: Optional[int] = None
        original_client_id = client_order_id # Keep original for history lookup if needed

        # 优先级：order_id > client_order_id (via map/search)
        if order_id:
             try:
                 ticket_to_find = int(order_id)
                 self.logger.debug(f"查询订单状态，使用提供的 Order ID (Ticket): {ticket_to_find}")
                 # If ticket is given, we don't need client_id for the primary lookup
                 client_order_id = None
             except (ValueError, TypeError):
                 self.logger.error(f"提供的 Order ID '{order_id}' 不是有效的整数 Ticket ID。")
                 return None
        elif client_order_id:
            self.logger.debug(f"查询订单状态，使用提供的 Client Order ID: {client_order_id}")
            ticket_to_find = self._get_ticket_from_client_id(client_order_id)
            if ticket_to_find is None:
                 self.logger.warning(f"无法找到 Client ID '{client_order_id}' 对应的 MT5 Ticket，将尝试仅通过 Client ID 在历史记录中查找 (如果实现)。")
                 # Keep client_order_id set for history lookup, ticket_to_find remains None
                 pass
            else:
                 # Found ticket via client_id, prioritize ticket for lookup
                 self.logger.debug(f"通过 Client ID '{client_order_id}' 找到 Ticket: {ticket_to_find}")
                 client_order_id = None
        else:
            self.logger.error("获取订单状态需要提供 order_id (ticket) 或 client_order_id。")
            return None

        mt5_order_info = None

        # 1. 尝试使用 Ticket 在挂单中查找 (如果 ticket 已知)
        if ticket_to_find is not None:
            self.logger.debug(f"尝试使用 Ticket {ticket_to_find} 获取挂单信息...")
            try:
                # Use mt5.orders_get(ticket=...) which is efficient
                orders = mt5.orders_get(ticket=ticket_to_find)
                if orders and len(orders) > 0:
                    # Should only be one order for a unique ticket
                    mt5_order_info = orders[0]
                    self.logger.debug(f"在挂单中找到 Ticket {ticket_to_find} 的信息。")
                else:
                     self.logger.debug(f"在挂单中未找到 Ticket {ticket_to_find}。")
            except Exception as e:
                 self.logger.error(f"使用 Ticket {ticket_to_find} 调用 mt5.orders_get 时出错: {e}", exc_info=True)
                 # Continue to history search in case of error

        # 2. 如果在挂单中未找到，尝试在历史订单中查找 (优先使用 Ticket)
        if mt5_order_info is None:
            lookup_info = f"Ticket '{ticket_to_find}'" if ticket_to_find else f"Client ID '{original_client_id}'"
            self.logger.debug(f"尝试在历史订单中查找 {lookup_info}...")
            try:
                if ticket_to_find is not None:
                    # Use mt5.history_orders_get(ticket=...) which is efficient
                    history_orders = mt5.history_orders_get(ticket=ticket_to_find)
                    if history_orders and len(history_orders) > 0:
                         mt5_order_info = history_orders[0]
                         self.logger.debug(f"在历史订单中找到 Ticket {ticket_to_find} 的信息。")
                    else:
                         self.logger.debug(f"在历史订单中未找到 Ticket {ticket_to_find}。")
                elif original_client_id:
                    # Searching history by comment is extremely inefficient and not implemented reliably here.
                    # If historical lookup by client_id is required, a separate persistent mapping is needed.
                    self.logger.warning(f"未实现通过 Client ID '{original_client_id}' 在历史记录中高效搜索。无法获取历史订单状态。")
                    pass
            except Exception as e:
                 self.logger.error(f"查找历史订单时出错 (Ticket: {ticket_to_find}, ClientID: {original_client_id}): {e}", exc_info=True)

        # 3. 如果找到订单信息，转换为内部 Order 对象
        if mt5_order_info:
            self.logger.debug(f"找到订单信息，正在转换为 Order 对象: {vars(mt5_order_info)}") # Log attributes
            internal_order = self._mt5_order_to_order_obj(mt5_order_info)
            
            # --- Restore Client ID and Update Map ---
            if internal_order:
                 # Try to get client ID from comment field of MT5 object
                 retrieved_comment = getattr(mt5_order_info, 'comment', None)
                 
                 # If the internal order's client_id is missing, try using the comment
                 if not internal_order.client_order_id and retrieved_comment and retrieved_comment.startswith('cli_'):
                      internal_order.client_order_id = retrieved_comment
                      self.logger.debug(f"从 MT5 评论恢复 Client ID: {retrieved_comment}")
                 # Else if we looked up by client_id originally, restore it if needed
                 elif not internal_order.client_order_id and original_client_id:
                     internal_order.client_order_id = original_client_id
                     self.logger.debug(f"手动将原始 Client ID '{original_client_id}' 添加到 Order 对象。")

                 # Update map if we found the ticket and the client_id is known
                 if ticket_to_find and internal_order.client_order_id and internal_order.client_order_id not in self.client_to_broker_id_map:
                      self.client_to_broker_id_map[internal_order.client_order_id] = ticket_to_find
                      self.logger.debug(f"在状态检查后更新 client->broker 映射: {internal_order.client_order_id} -> {ticket_to_find}")

            return internal_order
        else:
            lookup_info = f"Ticket: {ticket_to_find}" if ticket_to_find else f"ClientID: {original_client_id}"
            self.logger.warning(f"未能找到订单信息 ({lookup_info})。")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取所有或指定品种的挂单。"""
        if not self.connected:
            self.logger.error("无法获取挂单：未连接到 MT5。")
            return []
        mt5_symbol = self._map_symbol_to_mt5(symbol) if symbol else None
        try:
            if mt5_symbol:
                 mt5_orders = mt5.orders_get(symbol=mt5_symbol)
            else:
                 mt5_orders = mt5.orders_get()

            if mt5_orders is None:
                 self.logger.warning(f"mt5.orders_get 返回 None (Symbol: {mt5_symbol}). Last Error: {mt5.last_error()}")
                 return []

            orders = [self._mt5_order_to_order_obj(o) for o in mt5_orders if o]
            # Filter out None results from conversion errors
            orders = [o for o in orders if o is not None]
            self.logger.debug(f"找到 {len(orders)} 个挂单 (Symbol: {symbol or 'All'}).")
            return orders
        except Exception as e:
            self.logger.error(f"获取挂单时出错 (Symbol: {symbol}): {e}", exc_info=True)
            return []

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取指定品种的当前持仓。"""
        if not self.connected:
            self.logger.error("无法获取持仓：未连接到 MT5。")
            return None
        mt5_symbol = self._map_symbol_to_mt5(symbol)
        try:
            positions = mt5.positions_get(symbol=mt5_symbol)
            if positions is None:
                 self.logger.warning(f"mt5.positions_get 返回 None for symbol {mt5_symbol}. Last Error: {mt5.last_error()}")
                 # Return zero position for clarity instead of None
                 return {
                     'symbol': symbol, 'volume': 0.0, 'average_price': 0.0,
                     'profit': 0.0, 'side': None, 'raw_data': None, 'ticket': None # Ensure ticket is None for zero pos
                 }

            if len(positions) > 0:
                # Assume only one position per symbol (MT5 hedging mode might differ)
                if len(positions) > 1:
                    self.logger.warning(f"找到多个持仓 for symbol {mt5_symbol} ({symbol}). 将只返回第一个。")
                pos_info = self._mt5_position_to_dict(positions[0])
                self.logger.debug(f"找到持仓 for {symbol}: {pos_info}")
                return pos_info
            else:
                 self.logger.debug(f"没有找到 {symbol} ({mt5_symbol}) 的持仓。")
                 # Return a zero position dictionary
                 return {
                     'symbol': symbol, 'volume': 0.0, 'average_price': 0.0,
                     'profit': 0.0, 'side': None, 'raw_data': None, 'ticket': None # Ensure ticket is None
                 }
        except Exception as e:
             self.logger.error(f"获取持仓时出错 for symbol {symbol}: {e}", exc_info=True)
             return None # Indicate error

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有当前持仓。"""
        if not self.connected:
            self.logger.error("无法获取所有持仓：未连接到 MT5。")
            return []
        try:
            positions = mt5.positions_get()
            if positions is None:
                self.logger.warning(f"mt5.positions_get 返回 None when fetching all positions. Last Error: {mt5.last_error()}")
                return []
            all_pos = [self._mt5_position_to_dict(p) for p in positions if p]
            self.logger.debug(f"找到 {len(all_pos)} 个总持仓。")
            return all_pos
        except Exception as e:
            self.logger.error(f"获取所有持仓时出错: {e}", exc_info=True)
            return []

    def get_account_balance(self, currency: Optional[str] = None) -> Optional[Dict[str, float]]:
        """获取账户余额信息。"""
        if not self.connected:
            self.logger.error("无法获取账户余额：未连接到 MT5。")
            return None
        try:
            account_info = mt5.account_info()
            if account_info:
                # Map MT5 fields to a standard dictionary
                balance_info = {
                    'balance': account_info.balance,
                    'equity': account_info.equity,
                    'profit': account_info.profit,
                    'margin': account_info.margin,
                    'margin_free': account_info.margin_free,
                    'margin_level': account_info.margin_level,
                    'currency': account_info.currency
                }
                # Filter by currency if requested (though usually account has one base currency)
                if currency and account_info.currency.upper() != currency.upper():
                    self.logger.warning(f"请求的货币 '{currency}' 与账户货币 '{account_info.currency}' 不匹配。返回 None。")
                    return None
                self.logger.debug(f"获取到账户余额信息: {balance_info}")
                return balance_info
            else:
                 self.logger.error(f"无法获取账户信息 (mt5.account_info() 返回 None). Last Error: {mt5.last_error()}")
                 return None
        except Exception as e:
             self.logger.error(f"获取账户余额时出错: {e}", exc_info=True)
             return None

    def _mt5_position_to_dict(self, pos_info: Any) -> Dict[str, Any]:
        """将 MT5 PositionInfo 对象转换为字典。"""
        if pos_info is None: return {}
        side = None
        if pos_info.type == mt5.POSITION_TYPE_BUY:
             side = OrderSide.BUY
        elif pos_info.type == mt5.POSITION_TYPE_SELL:
             side = OrderSide.SELL

        return {
            'symbol': self._map_symbol_from_mt5(pos_info.symbol), # Map symbol back
            'ticket': pos_info.ticket,
            'volume': pos_info.volume,
            'average_price': pos_info.price_open,
            'current_price': pos_info.price_current,
            'profit': pos_info.profit, # MT5 position profit
            'swap': pos_info.swap,
            'sl': pos_info.sl if pos_info.sl > 0 else None, # Use None if SL is 0
            'tp': pos_info.tp if pos_info.tp > 0 else None, # Use None if TP is 0
            'magic': pos_info.magic,
            'side': side.value if side else None, # Use enum value
            'time': pd.to_datetime(pos_info.time, unit='s', utc=True), # Convert timestamp
            # Include raw data as dict if needed for debugging (using vars)
            'raw_data': {field: getattr(pos_info, field) for field in pos_info._fields}
        }

    def _mt5_order_to_order_obj(self, mt5_order: Any) -> Optional[Order]:
        """将 MT5 OrderInfo 对象转换为内部 Order 对象。"""
        if mt5_order is None: return None
        try:
            # Map MT5 order type to internal OrderType
            # Note: This mapping might be ambiguous for filled orders if original type isn't stored
            order_type_map = {
                mt5.ORDER_TYPE_BUY: OrderType.MARKET,
                mt5.ORDER_TYPE_SELL: OrderType.MARKET,
                mt5.ORDER_TYPE_BUY_LIMIT: OrderType.LIMIT,
                mt5.ORDER_TYPE_SELL_LIMIT: OrderType.LIMIT,
                mt5.ORDER_TYPE_BUY_STOP: OrderType.STOP,
                mt5.ORDER_TYPE_SELL_STOP: OrderType.STOP,
                # mt5.ORDER_TYPE_BUY_STOP_LIMIT: OrderType.STOP_LIMIT, # Define if needed
                # mt5.ORDER_TYPE_SELL_STOP_LIMIT: OrderType.STOP_LIMIT,
            }
            # Use get with a default or log warning for unmapped types
            order_type = order_type_map.get(mt5_order.type)
            if order_type is None:
                self.logger.warning(f"无法映射未知的 MT5 订单类型: {mt5_order.type} for ticket {mt5_order.ticket}")
                return None # Skip orders with unmappable types

            # Map MT5 order side based on type
            side_map = {
                 mt5.ORDER_TYPE_BUY: OrderSide.BUY,
                 mt5.ORDER_TYPE_SELL: OrderSide.SELL,
                 mt5.ORDER_TYPE_BUY_LIMIT: OrderSide.BUY,
                 mt5.ORDER_TYPE_SELL_LIMIT: OrderSide.SELL,
                 mt5.ORDER_TYPE_BUY_STOP: OrderSide.BUY,
                 mt5.ORDER_TYPE_SELL_STOP: OrderSide.SELL,
                 # Add stop limit types if needed
            }
            side = side_map.get(mt5_order.type)
            if side is None: # Should not happen if order_type mapping worked
                 self.logger.error(f"无法确定订单方向 for MT5 type {mt5_order.type}, ticket {mt5_order.ticket}")
                 return None

            # Map MT5 order state to internal OrderStatus
            status_map = {
                mt5.ORDER_STATE_STARTED: OrderStatus.NEW, # Changed from PENDING
                mt5.ORDER_STATE_PLACED: OrderStatus.NEW,
                mt5.ORDER_STATE_CANCELED: OrderStatus.CANCELED,
                mt5.ORDER_STATE_PARTIAL: OrderStatus.PARTIALLY_FILLED,
                mt5.ORDER_STATE_FILLED: OrderStatus.FILLED,
                mt5.ORDER_STATE_REJECTED: OrderStatus.REJECTED,
                mt5.ORDER_STATE_EXPIRED: OrderStatus.EXPIRED,
                # Intermediate states mapped to PENDING
                mt5.ORDER_STATE_REQUEST_ADD: OrderStatus.PENDING,
                mt5.ORDER_STATE_REQUEST_MODIFY: OrderStatus.PENDING,
                mt5.ORDER_STATE_REQUEST_CANCEL: OrderStatus.PENDING,
            }
            # Default to REJECTED for unknown states? Or log and return None?
            status = status_map.get(mt5_order.state, OrderStatus.REJECTED)
            if mt5_order.state not in status_map:
                 self.logger.warning(f"无法映射未知的 MT5 订单状态: {mt5_order.state} for ticket {mt5_order.ticket}. Defaulting to {status.value}.")

            # Create Order object
            # 提取 client_order_id (现在直接从 comment 获取，不再检查 'cli_' 前缀)
            client_id = mt5_order.comment
            if not client_id:
                # 如果 comment 为空或 None，记录警告，但仍然尝试创建 Order 对象
                self.logger.warning(f"MT5 订单 Ticket {mt5_order.ticket} 的 comment 字段为空，无法提取 client_order_id。")

            order = Order(
                symbol=self._map_symbol_from_mt5(mt5_order.symbol), # Map symbol back
                side=side,
                order_type=order_type,
                volume=mt5_order.volume_initial, # Initial requested volume
                order_id=str(mt5_order.ticket),
                client_order_id=client_id, # Use extracted client_id or None
                # Determine price based on order type
                limit_price=mt5_order.price_open if order_type == OrderType.LIMIT else None,
                stop_price=mt5_order.price_open if order_type == OrderType.STOP else None, # price_open used for stop/limit trigger
                status=status,
                creation_time=pd.to_datetime(mt5_order.time_setup, unit='s', utc=True),
                # Use time_done if it's set (non-zero), otherwise None
                last_update_time=pd.to_datetime(mt5_order.time_done, unit='s', utc=True) if mt5_order.time_done > 0 else None,
                executed_volume=mt5_order.volume_current, # Currently executed volume
                # Use price_current for average fill price if filled/partially filled? Needs verification.
                average_filled_price=mt5_order.price_current if status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED] else None,
                stop_loss=mt5_order.sl if mt5_order.sl > 0 else None,
                take_profit=mt5_order.tp if mt5_order.tp > 0 else None,
                # Include magic number in metadata
                metadata={'magic': mt5_order.magic, 'mt5_type': mt5_order.type, 'mt5_state': mt5_order.state}
            )
            # Commission needs to be fetched from deals associated with the order
            # order.commission = ...

            self.logger.debug(f"将 MT5 OrderInfo (Ticket: {mt5_order.ticket}) 转换为 Order 对象: {order.to_dict()}")
            return order
        except Exception as e:
             self.logger.error(f"将 MT5 OrderInfo (Ticket: {mt5_order.ticket}) 转换为 Order 对象时出错: {e}", exc_info=True)
             return None

    def _parse_retcode(self, retcode: int) -> str:
         """将 MT5 返回码转换为可读字符串。"""
         # Based on MQL5 documentation
         code_map = {
             10004: "REQUOTE",
             10006: "REQUEST_REJECTED",
             10007: "REQUEST_CANCELED",
             10008: "REQUEST_PLACED",
             10009: "TRADE_RETCODE_DONE", # Request completed
             10010: "TRADE_RETCODE_DONE_PARTIAL", # Request completed partially
             10011: "TRADE_RETCODE_ERROR", # Processing error
             10012: "TRADE_RETCODE_TIMEOUT", # Request timed out
             10013: "TRADE_RETCODE_INVALID", # Invalid request
             10014: "TRADE_RETCODE_INVALID_VOLUME",
             10015: "TRADE_RETCODE_INVALID_PRICE",
             10016: "TRADE_RETCODE_INVALID_STOPS",
             10017: "TRADE_RETCODE_TRADE_DISABLED",
             10018: "TRADE_RETCODE_MARKET_CLOSED",
             10019: "TRADE_RETCODE_NO_MONEY",
             10020: "TRADE_RETCODE_PRICE_CHANGED",
             10021: "TRADE_RETCODE_PRICE_OFF", # No quotes
             10022: "TRADE_RETCODE_INVALID_EXPIRATION",
             10023: "TRADE_RETCODE_ORDER_CHANGED", # Order state changed
             10024: "TRADE_RETCODE_TOO_MANY_REQUESTS",
             10025: "TRADE_RETCODE_NO_CHANGES", # No changes for modification request
             10026: "TRADE_RETCODE_SERVER_DISABLES_AT", # Autotrading disabled by server
             10027: "TRADE_RETCODE_CLIENT_DISABLES_AT", # Autotrading disabled by client
             10028: "TRADE_RETCODE_LOCKED", # Request locked for processing
             10029: "TRADE_RETCODE_FROZEN", # Order or position frozen
             10030: "TRADE_RETCODE_INVALID_FILL", # Invalid order filling type
             10031: "TRADE_RETCODE_CONNECTION", # No connection to trade server
             10032: "TRADE_RETCODE_ONLY_REAL", # Operation allowed only for live accounts
             10033: "TRADE_RETCODE_LIMIT_ORDERS", # Limit of pending orders reached
             10034: "TRADE_RETCODE_LIMIT_VOLUME", # Limit of volume reached
             10035: "TRADE_RETCODE_INVALID_ORDER", # Order not found
             10036: "TRADE_RETCODE_POSITION_CLOSED", # Position closed
             10038: "TRADE_RETCODE_INVALID_CLOSE_VOLUME",
             10039: "TRADE_RETCODE_CLOSE_ORDER_EXIST", # Close order already exists for the position
             10040: "TRADE_RETCODE_LIMIT_POSITIONS", # Limit of open positions reached
             10041: "TRADE_RETCODE_REJECT_CANCEL", # Request to activate pending order rejected, order canceled
             10042: "TRADE_RETCODE_LONG_ONLY", # Order type prohibited (longs only)
             10043: "TRADE_RETCODE_SHORT_ONLY", # Order type prohibited (shorts only)
             10044: "TRADE_RETCODE_CLOSE_ONLY", # Order type prohibited (close only)
             10045: "TRADE_RETCODE_FIFO_CLOSE", # Closing is prohibited due to FIFO rule
         }
         # Ensure retcode is int before lookup
         try:
             return code_map.get(int(retcode), f"UNKNOWN_RETCODE_{retcode}")
         except (ValueError, TypeError):
             return f"INVALID_RETCODE_TYPE_{retcode}"
