from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    # Add more types like STOP_LIMIT, TRAILING_STOP etc. if needed

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"      # Order received but not yet active (e.g., future stop/limit)
    NEW = "NEW"            # Order is active but not yet filled
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class Order:
    """
    标准化的订单数据结构。
    """
    symbol: str                 # 交易品种 (e.g., "EURUSD")
    side: OrderSide             # 订单方向 (BUY/SELL)
    order_type: OrderType         # 订单类型 (MARKET, LIMIT, etc.)
    volume: float               # 订单数量/手数
    
    order_id: Optional[str] = None  # 交易所或经纪商返回的订单 ID
    client_order_id: str = field(default_factory=lambda: f"cli_{int(datetime.now().timestamp() * 1000)}") # 客户端生成的唯一 ID
    
    limit_price: Optional[float] = None # 限价单价格
    stop_price: Optional[float] = None  # 止损单触发价格
    
    status: OrderStatus = OrderStatus.NEW # 订单状态
    creation_time: datetime = field(default_factory=datetime.utcnow) # 订单创建时间 (UTC)
    last_update_time: Optional[datetime] = None # 最后更新时间 (UTC)
    
    executed_volume: float = 0.0 # 已成交数量
    average_filled_price: Optional[float] = None # 平均成交价格
    
    commission: Optional[float] = None # 交易佣金
    commission_asset: Optional[str] = None # 佣金货币
    
    # Optional fields for more complex orders
    time_in_force: Optional[str] = None # GTC, IOC, FOK etc.
    stop_loss: Optional[float] = None   # 附加的止损价格
    take_profit: Optional[float] = None # 附加的止盈价格
    
    # Metadata for linking back to strategy or signals
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """将订单对象转换为字典。"""
        data = {
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "volume": self.volume,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "creation_time": self.creation_time.isoformat() if self.creation_time else None,
            "last_update_time": self.last_update_time.isoformat() if self.last_update_time else None,
            "executed_volume": self.executed_volume,
            "average_filled_price": self.average_filled_price,
            "commission": self.commission,
            "commission_asset": self.commission_asset,
            "time_in_force": self.time_in_force,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "metadata": self.metadata
        }
        # Remove None values for cleaner representation
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建订单对象。"""
        # Convert enum strings back to enums
        data['side'] = OrderSide(data['side'])
        data['order_type'] = OrderType(data['order_type'])
        data['status'] = OrderStatus(data['status'])
        # Convert ISO time strings back to datetime
        if 'creation_time' in data and data['creation_time']:
            data['creation_time'] = datetime.fromisoformat(data['creation_time'])
        if 'last_update_time' in data and data['last_update_time']:
             data['last_update_time'] = datetime.fromisoformat(data['last_update_time'])
             
        return cls(**data)

# Example Usage:
# buy_order = Order(symbol="EURUSD", side=OrderSide.BUY, order_type=OrderType.MARKET, volume=0.01)
# print(buy_order)
# print(buy_order.to_dict()) 