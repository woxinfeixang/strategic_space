from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict

from strategies.live.order import OrderSide # 假设 OrderSide 在这里可用，如果不在，需要调整导入路径


class RiskManager:
    def __init__(self, config: Dict[str, Any]):
        """
        初始化风险管理器。

        Args:
            config: 包含风险管理参数的配置字典。
                    预期包含键：
                    - 'risk_per_trade_percentage': 每次交易的风险百分比。
                                                 如果配置文件中是 "1" 代表 1%，则代码中应处理为 0.01。
                                                 如果配置文件中是 "0.01" 代表 1%，则代码中应直接使用 0.01。
                                                 当前假设配置文件提供的是直接的小数值 (如 0.01 代表 1%)。
                    - 'default_contract_size': 默认合约大小。
                    - 'min_volume': 最小交易手数 (可选)。
                    - 'volume_precision': 手数精度 (小数点后位数, 可选)。
        """
        # 修改点：假设配置文件中的 risk_per_trade_percentage 是直接的比例值，例如 "0.01" 代表 1%
        # 如果配置文件中是 "1" (代表1%)，则需要 self.risk_per_trade_percentage = Decimal(str(config.get("risk_per_trade_percentage", "1"))) / Decimal("100")
        # 根据我们 backtest.yaml 的 "0.01"，我们直接使用它
        self.risk_per_trade_percentage = Decimal(str(config.get("risk_per_trade_percentage", "0.01"))) # 移除 / Decimal("100")
        self.default_contract_size = Decimal(str(config.get("default_contract_size", "1"))) # 默认为1，应根据实际情况调整
        self.min_volume = Decimal(str(config.get("min_volume", "0.01")))
        self.volume_precision = int(config.get("volume_precision", 2))

    def calculate_order_volume(
        self,
        account_equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        side: OrderSide, # 用于未来可能的扩展，当前计算基于价格绝对差异
        contract_size: Decimal | None = None,
    ) -> Decimal:
        """
        根据固定风险比例计算订单手数。

        Args:
            account_equity: 当前账户净值。
            entry_price: 预期的入场价格。
            stop_loss_price: 止损价格。
            side: 交易方向 (OrderSide.BUY 或 OrderSide.SELL)。
            contract_size: 当前交易品种的合约大小。如果为None，则使用默认值。

        Returns:
            计算得出的订单手数，如果无法计算或低于最小手数，则返回 Decimal('0')。
        """
        if entry_price == stop_loss_price:
            # 避免除以零错误
            return Decimal("0")

        risk_amount_per_trade = account_equity * self.risk_per_trade_percentage
        price_diff_per_share = abs(entry_price - stop_loss_price)
        
        current_contract_size = contract_size if contract_size is not None else self.default_contract_size

        if price_diff_per_share <= Decimal("0") or current_contract_size <= Decimal("0"):
            # 避免无效计算
            return Decimal("0")

        # 每手（一个合约单位）的风险值
        risk_per_contract_unit = price_diff_per_share * current_contract_size

        if risk_per_contract_unit <= Decimal("0"):
            return Decimal("0")

        # 计算理论手数
        volume = risk_amount_per_trade / risk_per_contract_unit

        # 应用最小手数和精度调整
        if volume < self.min_volume:
            return Decimal("0") # 如果计算出的手数小于最小手数，则不交易或按最小手数交易（这里选择不交易）

        # 向下取整到指定精度
        quantizer = Decimal("1e-" + str(self.volume_precision)) # 例如 Decimal('0.01')
        volume_adjusted = volume.quantize(quantizer, rounding=ROUND_DOWN)
        
        return volume_adjusted

# 示例用法 (用于测试，实际使用时会集成到策略中)
if __name__ == '__main__':
    # 示例配置
    sample_config = {
        "risk_per_trade_percentage": "5",    # 5% 风险
        "default_contract_size": "100000", # 例如外汇标准手
        "min_volume": "0.01",
        "volume_precision": 2
    }
    risk_manager = RiskManager(sample_config)

    # 模拟账户和市场情况
    current_equity = Decimal("10000")    # 10000 美元净值
    entry = Decimal("1.12345")           # 入场价
    stop_loss = Decimal("1.12000")       # 止损价
    
    calculated_volume = risk_manager.calculate_order_volume(
        account_equity=current_equity,
        entry_price=entry,
        stop_loss_price=stop_loss,
        side=OrderSide.BUY # 假设是买入
    )
    print(f"账户净值: {current_equity}")
    print(f"每次交易风险: {risk_manager.risk_per_trade_percentage*100}%")
    print(f"入场价: {entry}, 止损价: {stop_loss}")
    print(f"合约大小: {risk_manager.default_contract_size}")
    print(f"计算出的手数: {calculated_volume}")

    # 测试止损价等于入场价
    calculated_volume_zero_diff = risk_manager.calculate_order_volume(
        current_equity, entry, entry, OrderSide.BUY
    )
    print(f"止损价等于入场价时计算的手数: {calculated_volume_zero_diff}")

    # 测试计算手数低于最小手数
    calculated_volume_low = risk_manager.calculate_order_volume(
        Decimal("100"), Decimal("1.12345"), Decimal("1.12300"), OrderSide.BUY
    )
    print(f"低净值导致手数低于最小手数: {calculated_volume_low}")

    # 测试不同合约大小
    sample_config_stock = {
        "risk_per_trade_percentage": "2",    # 2% 风险
        "default_contract_size": "100",    # 假设股票每手100股
        "min_volume": "1",                 # 股票最小交易1手 (整数)
        "volume_precision": 0              # 股票手数通常是整数
    }
    risk_manager_stock = RiskManager(sample_config_stock)
    calculated_volume_stock = risk_manager_stock.calculate_order_volume(
        account_equity=Decimal("50000"),
        entry_price=Decimal("150.75"),
        stop_loss_price=Decimal("145.25"),
        side=OrderSide.BUY,
        contract_size=Decimal("100") # 显式传入合约大小
    )
    print(f"股票示例手数: {calculated_volume_stock}") 