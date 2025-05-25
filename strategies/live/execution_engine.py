from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from .order import Order, OrderStatus

class ExecutionEngineBase(ABC):
    """
    交易执行引擎的抽象基类。
    定义了与经纪商或交易所交互的标准接口。
    """
    def __init__(self, config: dict):
        self.config = config
        self.logger = self._setup_logger()

    def _setup_logger(self):
        """设置执行引擎日志记录器。"""
        # TODO: 集成项目的主日志系统
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger = logging.getLogger(self.__class__.__name__)
        return logger

    @abstractmethod
    def connect(self):
        """建立与交易接口的连接。"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开与交易接口的连接。"""
        pass

    @abstractmethod
    def place_order(self, order: Order) -> Optional[Order]:
        """
        提交一个新订单。

        Args:
            order (Order): 要提交的订单对象。

        Returns:
            Optional[Order]: 更新了状态和 ID 的订单对象，如果提交失败则返回 None 或原始订单。
                         实现者应确保返回的订单包含 broker/exchange 分配的 order_id。
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> bool:
        """
        取消一个挂单。
        必须提供 order_id 或 client_order_id 中的至少一个。

        Args:
            order_id (Optional[str]): 经纪商/交易所的订单 ID。
            client_order_id (Optional[str]): 客户端生成的订单 ID。

        Returns:
            bool: 如果取消请求成功发送则返回 True，否则 False。
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[Order]:
        """
        查询特定订单的状态。

        Args:
            order_id (Optional[str]): 经纪商/交易所的订单 ID。
            client_order_id (Optional[str]): 客户端生成的订单 ID。

        Returns:
            Optional[Order]: 最新的订单状态对象，如果找不到订单则返回 None。
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        获取所有当前活动的挂单。

        Args:
            symbol (Optional[str]): 如果提供，则只返回该品种的挂单。

        Returns:
            List[Order]: 活动挂单的列表。
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取指定品种的当前持仓信息。

        Args:
            symbol (str): 交易品种。

        Returns:
            Optional[Dict[str, Any]]: 包含持仓信息的字典 (e.g., {'symbol': symbol, 'volume': float, 'average_price': float, 'unrealized_pnl': float})，
                                    如果没有持仓则返回 None 或 volume 为 0 的字典。
        """
        pass

    @abstractmethod
    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        获取所有持仓信息。

        Returns:
            List[Dict[str, Any]]: 持仓信息字典的列表。
        """
        pass

    @abstractmethod
    def get_account_balance(self, currency: Optional[str] = None) -> Optional[Dict[str, float]]:
        """
        获取账户余额信息。

        Args:
            currency (Optional[str]): 如果提供，则只返回指定货币的余额。

        Returns:
            Optional[Dict[str, float]]: 包含不同货币余额的字典 (e.g., {'USD': 10000.0, 'EUR': 500.0})，或单个货币的余额。
                                     如果查询失败则返回 None。
        """
        pass

    # Optional: Methods for market data (if the execution venue also provides data)
    # @abstractmethod
    # def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
    #     pass
    #
    # @abstractmethod
    # def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict[str, List]]:
    #     pass 