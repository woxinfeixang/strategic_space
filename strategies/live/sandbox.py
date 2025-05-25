import pandas as pd
import time
from typing import List, Dict, Optional, Any
from .order import Order, OrderStatus, OrderSide, OrderType
from .execution_engine import ExecutionEngineBase
from datetime import datetime
import random
from decimal import Decimal, getcontext

# 设置 Decimal 精度
getcontext().prec = 28

class SandboxExecutionEngine(ExecutionEngineBase):
    """
    一个简单的模拟交易执行引擎。
    用于在没有真实经纪商连接的情况下测试策略逻辑。
    模拟市价单立即成交，不处理限价/止损单逻辑。
    """
    def __init__(self, config: dict, data_provider, strategy_name: Optional[str] = None):
        super().__init__(config)
        self.strategy_name = strategy_name
        self.initial_cash = Decimal(config.get('execution_engine', {}).get('initial_cash', '100000'))
        self.commission_per_trade = Decimal(config.get('execution_engine', {}).get('commission_per_trade', '0.0'))
        self.balance: Dict[str, Decimal] = {"USD": self.initial_cash} # 假设基础货币是 USD
        self.positions: Dict[str, Dict[str, Any]] = {} # symbol -> {'volume': Decimal, 'average_price': Decimal, 'last_price': Decimal}
        self.open_orders: Dict[str, Order] = {} # client_order_id -> Order
        self.order_history: List[Order] = []
        self.trade_history: List[Dict[str, Any]] = [] # 用于记录成交信息
        self.data_provider = data_provider # 需要数据提供者获取当前价格
        self.connected = False
        self.equity_curve = pd.DataFrame(columns=['Equity'], dtype=object)
        self.last_update_time = None # 记录上次更新时间
        self.logger.info(f"Sandbox initialized with cash: {self.initial_cash} USD, commission: {self.commission_per_trade}")

    def connect(self):
        self.logger.info("Connecting to Sandbox environment...")
        self.connected = True
        self.logger.info("Sandbox connected.")

    def disconnect(self):
        self.logger.info("Disconnecting from Sandbox environment...")
        self.connected = False
        self.logger.info("Sandbox disconnected.")

    def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """获取用于模拟成交的当前市场价格。"""
        try:
            # 使用 data_provider 获取最新价格
            latest_prices = self.data_provider.get_latest_prices([symbol])
            if latest_prices and symbol in latest_prices and latest_prices[symbol] is not None:
                # 尝试使用 'close' 或 'open' 作为当前价格
                if 'close' in latest_prices[symbol]:
                    return Decimal(str(latest_prices[symbol]['close']))
                elif 'open' in latest_prices[symbol]:
                    return Decimal(str(latest_prices[symbol]['open']))
                else: # Fallback: average of high/low if available
                    if 'high' in latest_prices[symbol] and 'low' in latest_prices[symbol]:
                        return (Decimal(str(latest_prices[symbol]['high'])) + Decimal(str(latest_prices[symbol]['low']))) / Decimal('2')
            self.logger.warning(f"Could not retrieve current price for {symbol} from data provider.")
            return None
        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {e}")
            return None

    def place_order(self, order: Order) -> Optional[Order]:
        """模拟提交订单。市价单立即成交。"""
        if not self.connected:
            self.logger.error("Cannot place order: Not connected.")
            order.status = OrderStatus.REJECTED
            return order

        self.logger.info(f"Received order: {order.client_order_id} - {order.side.value} {order.volume} {order.symbol} @ {order.order_type.value}")
        self.open_orders[order.client_order_id] = order
        order.status = OrderStatus.NEW
        order.last_update_time = datetime.utcnow()
        self._update_equity_curve(order.last_update_time) # 在接收订单时尝试更新一次曲线

        # 模拟市价单立即成交
        if order.order_type == OrderType.MARKET:
            current_price = self._get_current_price(order.symbol)
            if current_price is None:
                self.logger.error(f"Cannot execute market order {order.client_order_id}: Failed to get current price for {order.symbol}.")
                order.status = OrderStatus.REJECTED
                self.order_history.append(order)
                if order.client_order_id in self.open_orders: del self.open_orders[order.client_order_id]
                self._update_equity_curve(datetime.utcnow()) # 更新曲线
                return order

            # 模拟点差和滑点 (使用 Decimal)
            spread_factor = Decimal(str(random.uniform(-0.00005, 0.00005))) # 更小的模拟滑点
            simulated_fill_price = current_price * (Decimal('1') + spread_factor)

            order_volume_dec = Decimal(str(order.volume))
            cost = order_volume_dec * simulated_fill_price
            commission = self.commission_per_trade
            # 计算总成本/收益 (Decimal)
            if order.side == OrderSide.BUY:
                total_change = -(cost + commission) # 资金减少
            else: # SELL
                total_change = cost - commission # 资金增加

            base_currency = "USD" # TODO: Get base currency properly

            # 检查余额 (使用 Decimal 比较)
            if order.side == OrderSide.BUY and self.balance.get(base_currency, Decimal('0')) < cost + commission:
                self.logger.warning(f"Order rejected {order.client_order_id}: Insufficient funds.")
                order.status = OrderStatus.REJECTED
                self.order_history.append(order)
                if order.client_order_id in self.open_orders: del self.open_orders[order.client_order_id]
                self._update_equity_curve(datetime.utcnow()) # 更新曲线
                return order

            # 更新持仓 (使用 Decimal)
            position = self.positions.get(order.symbol, {'volume': Decimal('0'), 'average_price': Decimal('0'), 'last_price': Decimal('0')})
            current_volume = position['volume']
            current_avg_price = position['average_price']

            if order.side == OrderSide.BUY:
                new_volume = current_volume + order_volume_dec
                if current_volume >= 0: # 开多或加仓多
                    new_avg_price = ((current_avg_price * current_volume) + (simulated_fill_price * order_volume_dec)) / new_volume if new_volume != Decimal('0') else Decimal('0')
                else: # 平空或转多
                    # 如果平仓后还有多头，平均价格需要重新计算（这里简化，假设完全平仓或反手）
                    if new_volume > 0: new_avg_price = simulated_fill_price
                    else: new_avg_price = Decimal('0') # 完全平仓
            else: # SELL
                new_volume = current_volume - order_volume_dec
                if current_volume <= 0: # 开空或加仓空
                    new_avg_price = ((current_avg_price * abs(current_volume)) + (simulated_fill_price * order_volume_dec)) / abs(new_volume) if new_volume != Decimal('0') else Decimal('0')
                else: # 平多或转空
                    # 如果平仓后还有空头，平均价格需要重新计算（这里简化）
                    if new_volume < 0: new_avg_price = simulated_fill_price
                    else: new_avg_price = Decimal('0') # 完全平仓

            # 更新余额
            self.balance[base_currency] = self.balance.get(base_currency, Decimal('0')) + total_change

            # 更新持仓字典
            self.positions[order.symbol] = {'volume': new_volume, 'average_price': new_avg_price, 'last_price': simulated_fill_price}

            # 更新订单状态 (使用 Decimal)
            order.status = OrderStatus.FILLED
            order.executed_volume = float(order_volume_dec) # Order 类可能期望 float
            order.average_filled_price = float(simulated_fill_price) # Order 类可能期望 float
            order.commission = float(commission)
            order.commission_asset = base_currency
            fill_time = datetime.utcnow()
            order.last_update_time = fill_time
            order.order_id = f"sandbox_{int(time.time()*1000)}_{random.randint(100,999)}" # Generate a fake ID

            self.order_history.append(order)
            if order.client_order_id in self.open_orders: del self.open_orders[order.client_order_id]
            self.logger.info(f"Order Filled: {order.to_dict()}")
            self.logger.info(f"New Position: {order.symbol} -> {self.positions[order.symbol]}")
            self.logger.info(f"New Balance: {self.balance}")

            # --- 记录成交信息到 trade_history --- 
            trade_record = {
                'order_id': order.order_id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'side': order.side.value,
                'volume': float(order_volume_dec),
                'price': float(simulated_fill_price),
                'commission': float(commission),
                'timestamp': fill_time
            }
            self.trade_history.append(trade_record)
            # ------------------------------------

            # 更新资金曲线
            self._update_equity_curve(fill_time)

        else:
            # 对于 LIMIT/STOP 订单，在 Sandbox 中保持 NEW 状态
            self.logger.warning(f"Order type {order.order_type.value} not fully simulated in Sandbox. Order {order.client_order_id} remains NEW.")
            # 添加到历史记录但保持在 open_orders 中
            self.order_history.append(order)

        return order

    def cancel_order(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> bool:
        """模拟取消订单。只能取消非市价挂单。"""
        if not self.connected:
            self.logger.error("Cannot cancel order: Not connected.")
            return False

        target_cli_id = client_order_id
        if order_id:
            # Find client_order_id from order_id in history (might be slow)
            found = False
            for o in reversed(self.order_history):
                if o.order_id == order_id:
                    target_cli_id = o.client_order_id
                    found = True
                    break
            if not found:
                self.logger.error(f"Cannot cancel order: Order ID {order_id} not found in history.")
                return False

        if not target_cli_id:
            self.logger.error("Cannot cancel order: No client_order_id or order_id provided.")
            return False

        if target_cli_id in self.open_orders:
            order_to_cancel = self.open_orders[target_cli_id]
            if order_to_cancel.status in [OrderStatus.NEW, OrderStatus.PENDING]:
                order_to_cancel.status = OrderStatus.CANCELED
                order_to_cancel.last_update_time = datetime.utcnow()
                del self.open_orders[target_cli_id]
                # Update history as well if needed, though it's already appended
                self.logger.info(f"Order Canceled: {target_cli_id}")
                return True
            else:
                self.logger.warning(f"Cannot cancel order {target_cli_id}: Status is {order_to_cancel.status.value}.")
                return False
        else:
            self.logger.warning(f"Cannot cancel order {target_cli_id}: Not found in open orders.")
            # Check history to see if it was already filled/canceled etc.
            for o in reversed(self.order_history):
                if o.client_order_id == target_cli_id:
                    self.logger.info(f"Order {target_cli_id} already has final status: {o.status.value}")
                    return False # Already in final state
            return False

    def get_order_status(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Optional[Order]:
        """模拟查询订单状态。"""
        target_cli_id = client_order_id
        if order_id:
            # Find client_order_id from order_id in history (might be slow)
            found_order = None # 用于存储找到的订单
            for o in reversed(self.order_history):
                if o.order_id == order_id:
                    target_cli_id = o.client_order_id
                    found_order = o # 保存找到的订单
                    break
            if target_cli_id is None:
                # 如果没找到，可能就不在历史里
                self.logger.info(f"Order ID {order_id} not found in current session history.")
                return None # 直接返回 None

        if target_cli_id:
            if target_cli_id in self.open_orders:
                return self.open_orders[target_cli_id]
            # Check history if not open (使用之前找到的 found_order)
            if found_order:
                return found_order # 返回在历史中找到的订单
            # 如果之前没通过 order_id 找到，再按 client_order_id 查一次历史
            elif client_order_id: # 确保 client_order_id 确实被提供了
                for o in reversed(self.order_history):
                    if o.client_order_id == client_order_id:
                        self.logger.info(f"Order {client_order_id} found in history with status {o.status.value}.")
                        return o

        self.logger.info(f"Order status not found for client_id={client_order_id}, order_id={order_id}")
        return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """模拟获取挂单。"""
        if symbol:
            return [o for o in self.open_orders.values() if o.symbol == symbol]
        else:
            return list(self.open_orders.values())

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取指定品种的当前持仓信息。"""
        pos = self.positions.get(symbol)
        if pos and pos.get('volume', Decimal('0')) != Decimal('0'):
            # 返回一个包含 Decimal 的字典，调用者需要处理
            return pos
        return None

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有非零持仓信息。"""
        all_pos = []
        for symbol, pos_data in self.positions.items():
            if pos_data.get('volume', Decimal('0')) != Decimal('0'):
                # 返回包含 Decimal 的字典列表
                all_pos.append({
                    'symbol': symbol,
                    'volume': pos_data['volume'],
                    'average_price': pos_data['average_price'],
                    'last_price': pos_data.get('last_price') # 可能还没有last_price
                })
        return all_pos

    def get_account_balance(self, currency: Optional[str] = None) -> Optional[Dict[str, float]]:
        """获取账户余额。"""
        if currency:
            bal = self.balance.get(currency)
            return {currency: float(bal)} if bal is not None else None
        # 返回所有货币的余额 (float)
        return {k: float(v) for k, v in self.balance.items()}

    # --- 新增方法 --- 
    def get_equity(self, current_time_utc: Optional[datetime] = None) -> Decimal:
        """计算当前总资产净值 (现金 + 持仓市值)。"""
        total_equity = self.balance.get("USD", Decimal('0'))
        for symbol, position in self.positions.items():
            volume = position.get('volume', Decimal('0'))
            if volume != Decimal('0'):
                # 尝试获取最新价格更新持仓市值
                last_price = self._get_current_price(symbol)
                if last_price is not None:
                    position['last_price'] = last_price # 更新最后价格
                else:
                    # 如果无法获取最新价，使用平均持仓成本价作为估算
                    last_price = position.get('average_price', Decimal('0'))
                
                # 市值 = 持仓量 * 最新价格
                market_value = volume * last_price
                total_equity += market_value
        return total_equity

    def _update_equity_curve(self, timestamp: datetime):
        """内部方法，在指定时间戳更新资金曲线。"""
        # 使用 Decimal 记录净值
        current_equity = self.get_equity(timestamp) 
        # 确保时间戳是 timezone-aware (UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=pytz.utc)
        else:
            timestamp = timestamp.astimezone(pytz.utc)
            
        # 使用 loc 添加或更新行，确保索引是 Timestamp
        # 直接将 Decimal 对象存入 DataFrame
        self.equity_curve.loc[pd.Timestamp(timestamp)] = [current_equity]
        self.last_update_time = timestamp
        # logger.debug(f"Equity curve updated at {timestamp}: {current_equity}")

    def get_trade_history(self) -> List[Dict[str, Any]]:
        """返回模拟成交记录列表。"""
        # 返回包含 float 的字典列表
        return self.trade_history
    # --------------- 

# Example Usage (Optional)
if __name__ == '__main__':
    # This part will only run when sandbox.py is executed directly
    # Setup basic logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Mock config and data provider for testing
    test_config = {
        'execution_engine': {
            'initial_cash': 100000,
            'commission_per_trade': 1.5
        }
    }

    class MockDataProvider:
        def get_latest_prices(self, symbols: List[str]):
            # Simulate some price movement
            prices = {}
            for s in symbols:
                prices[s] = {'close': round(1.12345 + random.uniform(-0.001, 0.001), 5)}
            return prices

    # Initialize
    mock_dp = MockDataProvider()
    sandbox = SandboxExecutionEngine(test_config, mock_dp)
    sandbox.connect()

    # --- Simulate some trades ---
    print("\n--- Simulating Trades ---")
    # 1. Buy EURUSD
    buy_order_1 = Order(symbol="EURUSD", side=OrderSide.BUY, volume=10000, order_type=OrderType.MARKET, client_order_id="buy1")
    filled_order_1 = sandbox.place_order(buy_order_1)
    time.sleep(0.1)

    # 2. Buy more EURUSD
    buy_order_2 = Order(symbol="EURUSD", side=OrderSide.BUY, volume=5000, order_type=OrderType.MARKET, client_order_id="buy2")
    filled_order_2 = sandbox.place_order(buy_order_2)
    time.sleep(0.1)

    # 3. Sell some EURUSD
    sell_order_1 = Order(symbol="EURUSD", side=OrderSide.SELL, volume=8000, order_type=OrderType.MARKET, client_order_id="sell1")
    filled_order_3 = sandbox.place_order(sell_order_1)
    time.sleep(0.1)

    # 4. Sell GBPUSD (Short)
    sell_order_2 = Order(symbol="GBPUSD", side=OrderSide.SELL, volume=5000, order_type=OrderType.MARKET, client_order_id="sell_short_gbp")
    filled_order_4 = sandbox.place_order(sell_order_2)
    time.sleep(0.1)

    # 5. Buy to close GBPUSD short
    buy_order_3 = Order(symbol="GBPUSD", side=OrderSide.BUY, volume=5000, order_type=OrderType.MARKET, client_order_id="buy_close_gbp")
    filled_order_5 = sandbox.place_order(buy_order_3)
    time.sleep(0.1)

    # --- Check final state ---
    print("\n--- Final State ---")
    print("Open Orders:", sandbox.get_open_orders())
    print("Positions:", sandbox.get_all_positions())
    print("Balance:", sandbox.get_account_balance())
    print("Equity:", sandbox.get_equity())
    print("\nTrade History:")
    for trade in sandbox.get_trade_history():
        print(trade)
    print("\nEquity Curve:")
    # Ensure equity curve is sorted by time before printing
    sandbox.equity_curve.sort_index(inplace=True)
    print(sandbox.equity_curve)

    sandbox.disconnect() 