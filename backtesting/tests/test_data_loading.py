import pytest
from unittest.mock import Mock, patch
from backtesting.engine import BacktestEngine
from omegaconf import OmegaConf

@pytest.fixture
def data_engine():
    config = OmegaConf.create({
        'engine': {
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'symbols': ['EURUSD'],
            'cash': 100000
        },
        'data': {
            'provider': 'MT5',
            'timeframe': 'D1'
        }
    })
    return BacktestEngine(config, "DataTestStrategy")

@patch('data.historical_data_provider.MT5DataProvider')
def test_historical_data_loading(mock_provider, data_engine):
    """测试历史数据加载完整性"""
    # 配置mock返回测试数据
    mock_provider.return_value.load_data.return_value = {
        'EURUSD': Mock(shape=(100, 5))
    }
    
    data_engine.load_historical_data()
    
    assert data_engine.historical_data is not None
    assert 'EURUSD' in data_engine.historical_data
    assert len(data_engine.historical_data['EURUSD']) == 100
    mock_provider.return_value.load_data.assert_called_once_with(
        symbols=['EURUSD'],
        start_date='2024-01-01',
        end_date='2024-12-31',
        timeframe='D1'
    )

def test_data_quality_checks(data_engine):
    """测试数据质量验证逻辑"""
    test_data = {
        'EURUSD': Mock()
    }
    test_data['EURUSD'].isnull().sum.return_value = 0
    test_data['EURUSD'].duplicated().sum.return_value = 0
    
    result = data_engine.validate_data_quality(test_data)
    
    assert result is True
