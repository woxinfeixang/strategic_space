# -*- coding: utf-8 -*-
import sys
from pathlib import Path
import MetaTrader5 as mt5
import pandas as pd
import traceback
from datetime import datetime
from omegaconf import DictConfig, OmegaConf
from ..utils import load_app_config, initialize_mt5, shutdown_mt5, MT5_AVAILABLE

def print_terminal_info():
    """打印终端信息"""
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print("无法获取终端信息")
        return
        
    print("\n--- 终端信息 ---")
    for prop in dir(terminal_info):
        if not prop.startswith('_'):
            print(f"{prop}: {getattr(terminal_info, prop)}")

def print_account_info():
    """打印账户信息"""
    account_info = mt5.account_info()
    if account_info is None:
        print("无法获取账户信息")
        return
        
    print("\n--- 账户信息 ---")
    for prop in dir(account_info):
        if not prop.startswith('_'):
            print(f"{prop}: {getattr(account_info, prop)}")

def print_symbols():
    """打印可交易品种"""
    symbols = mt5.symbols_get()
    if symbols is None:
        print("无法获取交易品种")
        return
        
    print(f"\n--- 交易品种 (共{len(symbols)}个) ---")
    for i, symbol in enumerate(symbols[:10]):  # 只显示前10个
        print(f"{i+1}. {symbol.name}")
    
    if len(symbols) > 10:
        print(f"... 还有 {len(symbols)-10} 个品种未显示")

def print_symbol_info(symbol="EURUSD"):
    """打印指定品种的详细信息"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"无法获取品种 {symbol} 的信息")
        return
        
    print(f"\n--- 品种信息: {symbol} ---")
    for prop in dir(symbol_info):
        if not prop.startswith('_'):
            print(f"{prop}: {getattr(symbol_info, prop)}")

def print_tick_info(symbol="EURUSD"):
    """打印最新报价信息"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"无法获取品种 {symbol} 的报价")
        return
        
    print(f"\n--- 最新报价: {symbol} ---")
    print(f"时间: {datetime.fromtimestamp(tick.time)}")
    print(f"卖价: {tick.bid}")
    print(f"买价: {tick.ask}")
    print(f"最后成交价: {tick.last}")
    print(f"成交量: {tick.volume}")

def check_mt5_status():
    config: Optional[DictConfig] = None
    mt5_initialized_by_util = False
    try:
        # 加载配置 using utility
        try:
            config = load_app_config('market_price_data')
            print("配置文件加载成功。")
        except Exception as load_err:
            print(f"无法加载配置文件: {load_err}")
            return False

        if not config:
            print("无法加载配置文件 或 配置为空。")
            return False
            
        # 获取MT5配置 from OmegaConf
        mt5_config = OmegaConf.select(config, 'mt5')
        if not mt5_config:
             print("在配置中未找到 'mt5' 部分。")
             return False
             
        print(f"使用 MT5 配置: {OmegaConf.to_container(mt5_config, resolve=True)}")
        
        # 初始化MT5 using utility
        mt5_initialized_by_util = initialize_mt5(mt5_config)
        if not mt5_initialized_by_util:
            print(f"通过工具函数初始化 MT5 失败。") # Logger should have details
            return False
        else:
             print("通过工具函数初始化 MT5 成功。")
            
        # 打印各种信息
        print(f"MT5版本: {mt5.version()}")
        print_terminal_info()
        print_account_info()
        print_symbols()
        # Allow specifying symbol via config? For now, hardcoded default
        target_symbol = OmegaConf.select(config, 'tools.mt5_info.default_symbol', default="EURUSD")
        print_symbol_info(target_symbol)
        print_tick_info(target_symbol)
        
        return True
        
    except Exception as e:
        print(f"获取 MT5 信息时发生错误: {str(e)}")
        print(traceback.format_exc())
        return False
        
    finally:
        # 关闭MT5连接 using utility
        if mt5_initialized_by_util:
             print("正在关闭 MT5 连接 (via utility)...")
             shutdown_mt5()
        else:
             print("跳过关闭 MT5 连接，因为它未被此脚本成功初始化。")

if __name__ == "__main__":
    print("正在获取MT5信息...")
    if not MT5_AVAILABLE:
        print("错误: MetaTrader5 库未安装或无法导入。")
    else:
        success = check_mt5_status()
        print(f"\n操作{'成功' if success else '失败'}") 