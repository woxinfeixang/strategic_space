# strategies/utils/signal_aggregator.py
# 跨策略信号聚合工具

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd


class SignalAggregator:
    """
    跨策略信号聚合器，用于集中管理各策略生成的信号并识别共振
    """
    
    def __init__(self, logger, config=None):
        """
        初始化信号聚合器
        
        Args:
            logger: 日志记录器
            config: 配置字典，包含信号聚合相关参数
        """
        self.logger = logger
        self.config = config or {}
        
        # 策略权重，默认所有策略权重相等
        self.strategy_weights = self.config.get("strategy_weights", {})
        
        # 默认策略权重值
        self.default_strategy_weight = self.config.get("default_strategy_weight", 1.0)
        
        # 共振时间窗口（分钟）
        self.resonance_time_window_minutes = self.config.get("resonance_time_window_minutes", 120)
        
        # 共振阈值（权重）
        self.resonance_threshold = self.config.get("resonance_threshold", 2.0)
        
        # 信号保留时间（小时）
        self.signal_retain_hours = self.config.get("signal_retain_hours", 48)
        
        # 信号存储，格式为 {symbol: {action: [{timestamp, strategy, weight}, ...]}
        self._signals = {}
        
        self.logger.info("信号聚合器初始化完成")
    
    def submit_signal(self, strategy_name: str, symbol: str, action: str, 
                     timestamp: datetime, confidence: float = 1.0, 
                     metadata: Dict[str, Any] = None) -> None:
        """
        提交一个交易信号到聚合器
        
        Args:
            strategy_name: 策略名称
            symbol: 交易品种
            action: 交易动作，"BUY"或"SELL"
            timestamp: 信号生成时间
            confidence: 信号置信度（0-1）
            metadata: 信号附加元数据
        """
        if action not in ["BUY", "SELL"]:
            self.logger.warning(f"无效的交易动作: {action}，必须是 'BUY' 或 'SELL'")
            return
        
        # 获取策略权重
        weight = self.strategy_weights.get(strategy_name, self.default_strategy_weight)
        
        # 调整权重根据置信度
        adjusted_weight = weight * confidence
        
        # 初始化品种和动作的信号列表
        if symbol not in self._signals:
            self._signals[symbol] = {"BUY": [], "SELL": []}
            
        # 添加信号
        signal = {
            "timestamp": timestamp,
            "strategy": strategy_name,
            "weight": adjusted_weight,
            "metadata": metadata or {}
        }
        
        self._signals[symbol][action].append(signal)
        self.logger.debug(f"添加信号: {strategy_name} 对 {symbol} 生成 {action} 信号，权重 {adjusted_weight:.2f}")
    
    def check_resonance(self, current_time: datetime) -> Dict[str, Dict[str, Any]]:
        """
        检查当前是否存在共振信号
        
        Args:
            current_time: 当前时间
            
        Returns:
            共振信号字典 {symbol: {'action': 'BUY'/'SELL', 'weight': float, 'strategies': list}}
        """
        resonant_signals = {}
        time_window = timedelta(minutes=self.resonance_time_window_minutes)
        
        # 遍历所有品种
        for symbol, actions in self._signals.items():
            # 检查买入信号
            buy_signals = [s for s in actions["BUY"] if 
                          (current_time - s["timestamp"]) <= time_window]
            
            # 检查卖出信号
            sell_signals = [s for s in actions["SELL"] if 
                           (current_time - s["timestamp"]) <= time_window]
            
            # 计算买入权重和卖出权重
            buy_weight = sum(s["weight"] for s in buy_signals)
            sell_weight = sum(s["weight"] for s in sell_signals)
            
            # 检查是否满足共振阈值
            if buy_weight >= self.resonance_threshold and buy_weight > sell_weight:
                resonant_signals[symbol] = {
                    "action": "BUY",
                    "weight": buy_weight,
                    "strategies": list(set(s["strategy"] for s in buy_signals))
                }
                self.logger.info(f"检测到买入共振信号: {symbol}，权重 {buy_weight:.2f}，策略 {resonant_signals[symbol]['strategies']}")
            
            elif sell_weight >= self.resonance_threshold and sell_weight > buy_weight:
                resonant_signals[symbol] = {
                    "action": "SELL",
                    "weight": sell_weight,
                    "strategies": list(set(s["strategy"] for s in sell_signals))
                }
                self.logger.info(f"检测到卖出共振信号: {symbol}，权重 {sell_weight:.2f}，策略 {resonant_signals[symbol]['strategies']}")
        
        return resonant_signals
    
    def clean_old_signals(self, current_time: Optional[datetime] = None) -> None:
        """
        清理过期的信号
        
        Args:
            current_time: 当前时间，如果为None则使用当前系统时间
        """
        if current_time is None:
            current_time = datetime.now()
            
        retain_cutoff = current_time - timedelta(hours=self.signal_retain_hours)
        
        for symbol in list(self._signals.keys()):
            for action in ["BUY", "SELL"]:
                if symbol in self._signals and action in self._signals[symbol]:
                    # 筛选保留的信号
                    original_count = len(self._signals[symbol][action])
                    self._signals[symbol][action] = [
                        s for s in self._signals[symbol][action] 
                        if s["timestamp"] >= retain_cutoff
                    ]
                    removed_count = original_count - len(self._signals[symbol][action])
                    
                    if removed_count > 0:
                        self.logger.debug(f"清理 {symbol} {action} 共 {removed_count} 个过期信号")
            
            # 如果某个品种的信号列表为空，则移除该品种
            if all(not self._signals[symbol][action] for action in ["BUY", "SELL"]):
                del self._signals[symbol]
                self.logger.debug(f"移除品种 {symbol} 空信号列表")
    
    def get_signals_for_symbol(self, symbol: str, window_minutes: Optional[int] = None,
                             current_time: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取指定品种的信号
        
        Args:
            symbol: 交易品种
            window_minutes: 时间窗口（分钟），仅返回时间窗口内的信号，None表示返回所有信号
            current_time: 当前时间，如果为None则使用当前系统时间
            
        Returns:
            信号字典 {"BUY": [...], "SELL": [...]}
        """
        if symbol not in self._signals:
            return {"BUY": [], "SELL": []}
        
        if window_minutes is None:
            return self._signals[symbol]
        
        if current_time is None:
            current_time = datetime.now()
            
        time_window = timedelta(minutes=window_minutes)
        
        result = {"BUY": [], "SELL": []}
        for action in ["BUY", "SELL"]:
            result[action] = [s for s in self._signals[symbol][action] 
                             if (current_time - s["timestamp"]) <= time_window]
            
        return result
    
    def get_all_signals(self) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        获取所有信号
        
        Returns:
            所有信号 {symbol: {"BUY": [...], "SELL": [...]}}
        """
        return self._signals 