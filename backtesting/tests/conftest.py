import pytest
from omegaconf import OmegaConf

@pytest.fixture(scope="session")
def base_config():
    return OmegaConf.create({
        'engine': {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'symbols': ['EURUSD', 'GBPUSD'],
            'cash': 100000,
            'commission': 0.001
        },
        'data': {
            'provider': 'MT5',
            'timeframe': 'D1',
            'data_path': 'data/historical/'
        },
        'backtest': {
            'strategy_name': 'BaseStrategy',
            'output_dir': 'backtesting/results/'
        }
    })
