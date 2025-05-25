# Strategic Space Trading System Agent Guidelines

## Build/Test Commands
- Run backtests: `python run_backtest.py --config config/backtest_test_all.yaml`
- Run specific test: `pytest backtesting/tests/test_engine.py -v`
- Run all tests: `pytest backtesting/tests/ -v`

## Code Style Guidelines
- Use PEP 8 formatting with descriptive variable names
- Document functions and classes with docstrings in Chinese
- Use type hints for function parameters and return values
- Error handling: Use try/except blocks with specific exception types
- Path handling: Use Path objects from pathlib rather than string concatenation
- Logging: Configure hierarchical logging with proper levels

## Chinese Default
- By default, all comments, docstrings, and user-facing text should be in Chinese
- Variable names and function names should be in English

## Config Management
- Use OmegaConf for configuration files in YAML format
- Follow the hierarchical config approach with common.yaml as the base