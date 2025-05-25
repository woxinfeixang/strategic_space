import pytest
from omegaconf import OmegaConf
from backtesting.engine import BacktestEngine

@pytest.fixture
def sample_config():
    return OmegaConf.create({
        'engine': {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'symbols': ['EURUSD'],
            'cash': 100000
        },
        'backtest': {
            'strategy_name': 'SampleStrategy'
        }
    })

def test_engine_initialization(sample_config):
    """测试回测引擎初始化"""
    engine = BacktestEngine(sample_config, "SampleStrategy")
    assert engine is not None
    assert engine.strategy is None
    assert engine.broker is None
    assert engine.risk_manager is None
