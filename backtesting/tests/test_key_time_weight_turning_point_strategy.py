import pytest
from datetime import datetime, timedelta
import pandas as pd
from backtesting.engine import BacktestEngine
from strategies.key_time_weight_turning_point_strategy import KeyTimeWeightTurningPointStrategy

class TestKeyTimeWeightTurningPointStrategy:
    @pytest.fixture
    def strategy_config(self):
        return {
            'strategy_name': 'KTWTPS_TEST',
            'parameters': {
                'key_time_hours_after_event': [1, 3],
                'use_space_boundaries_as_turning_points': True,
                'confirm_with_m5_m15': False
            }
        }

    @pytest.fixture
    def engine(self):
        from backtesting.utils.config import load_config
        config = load_config('backtesting/config/backtest.yaml')
        engine = BacktestEngine(
            config=config,
            strategy_name='KTWTPS_TEST'
        )
        # 生成测试数据
        engine.data_provider.generate_test_data(
            symbol='EURUSD',
            start_date='2023-01-01',
            end_date='2023-01-10',
            timeframe='30min',
            data_points=100
        )
        return engine

    def test_strategy_initialization(self, strategy_config, engine):
        # 测试策略正确加载
        strategy = KeyTimeWeightTurningPointStrategy(
            config=strategy_config,
            data_provider=engine.data_provider,
            execution_engine=engine.execution_engine,
            risk_manager=engine.risk_manager
        )
        
        assert strategy.strategy_name == 'KTWTPS_TEST'
        assert strategy.key_time_hours_after_event == [1, 3]
        assert strategy.use_space_boundaries_as_turning_points is True

    def test_key_time_detection(self, strategy_config, engine):
        # 测试关键时间识别逻辑
        strategy = KeyTimeWeightTurningPointStrategy(
            config=strategy_config,
            data_provider=engine.data_provider,
            execution_engine=engine.execution_engine,
            risk_manager=engine.risk_manager
        )

        # 模拟事件时间
        event_time = pd.Timestamp('2023-01-01 12:00:00')
        test_cases = [
            ('2023-01-01 12:59:00', False),
            ('2023-01-01 13:00:00', True),  # 事件后1小时
            ('2023-01-01 15:00:00', True),  # 事件后3小时
            ('2023-01-01 16:01:00', False)
        ]

        for time_str, expected in test_cases:
            current_time = pd.Timestamp(time_str)
            space_info = {'event_time': event_time}
            result = strategy._is_key_time(current_time, space_info)
            assert (result is not None) == expected

    def test_turning_point_detection(self, strategy_config, engine):
        strategy = KeyTimeWeightTurningPointStrategy(
            config=strategy_config,
            data_provider=engine.data_provider,
            execution_engine=engine.execution_engine,
            risk_manager=engine.risk_manager
        )

        # 测试边界检测
        space_info = {
            'upper_bound': 1.1050,
            'lower_bound': 1.0950,
            'event_time': pd.Timestamp('2023-01-01 12:00:00')
        }

        test_bars = [
            {'high': 1.1052, 'low': 1.1045, 'expected': 'UPPER_BOUND'},
            {'high': 1.0955, 'low': 1.0948, 'expected': 'LOWER_BOUND'},
            {'high': 1.1000, 'low': 1.0990, 'expected': None}
        ]

        for bar in test_bars:
            result = strategy._is_at_turning_point(bar, space_info)
            assert result == bar['expected']
