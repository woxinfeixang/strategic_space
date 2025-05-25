# -*- coding: utf-8 -*-
import MetaTrader5 as mt5
from pathlib import Path
import traceback
from omegaconf import DictConfig, OmegaConf
from ..utils import load_app_config, initialize_mt5, shutdown_mt5, MT5_AVAILABLE
from typing import Optional

def check_trading_status():
    config: Optional[DictConfig] = None
    mt5_initialized_by_util = False
    try:
        # 加载配置 using utility
        try:
            config = load_app_config('market_price_data')
            print("配置文件加载成功。")
        except Exception as load_err:
            print(f"无法加载配置文件: {load_err}")
            return

        if not config:
            print("无法加载配置文件 或 配置为空。")
            return
        
        # 获取MT5配置 from OmegaConf
        mt5_config = OmegaConf.select(config, 'mt5')
        if not mt5_config:
             print("在配置中未找到 'mt5' 部分。")
             return
             
        print(f"使用 MT5 配置: {OmegaConf.to_container(mt5_config, resolve=True)}")

        # 初始化MT5 using utility
        mt5_initialized_by_util = initialize_mt5(mt5_config)
        if not mt5_initialized_by_util:
            print(f"通过工具函数初始化 MT5 失败。")
            return
        else:
             print("通过工具函数初始化 MT5 成功。")
        
        # 检查终端交易状态
        terminal_info = mt5.terminal_info()
        terminal_trade_allowed = terminal_info.trade_allowed if terminal_info else False
        
        # 检查账户交易状态
        account_info = mt5.account_info()
        account_trade_allowed = account_info.trade_allowed if account_info else False
        
        print("\n=== MT5交易状态检查 ===")
        print(f"终端允许交易: {'是' if terminal_trade_allowed else '否'}")
        print(f"账户允许交易: {'是' if account_trade_allowed else '否'}")
        
        if terminal_trade_allowed and account_trade_allowed:
            print("\n✓ 交易功能已完全启用，您可以正常交易了！")
        elif not terminal_trade_allowed and account_trade_allowed:
            print("\n✗ MT5终端禁止交易，但账户允许交易")
            print("  请参考'启用MT5交易功能指南.md'中的方法1启用交易")
        elif terminal_trade_allowed and not account_trade_allowed:
            print("\n✗ MT5终端允许交易，但账户禁止交易")
            print("  请联系您的经纪商了解账户限制原因")
        else:
            print("\n✗ MT5终端和账户都禁止交易")
            print("  请先按照'启用MT5交易功能指南.md'启用终端交易，再联系经纪商")
    
    except Exception as e: # Catch broader exceptions
         print(f"检查交易状态时发生错误: {e}")
         print(traceback.format_exc())
         
    finally:
        # 关闭MT5连接 using utility
        if mt5_initialized_by_util:
             print("正在关闭 MT5 连接 (via utility)...")
             shutdown_mt5()
        else:
             # Attempt shutdown anyway if init failed, might partially connect
             print("初始化失败，仍尝试关闭 MT5 连接 (via utility)...")
             shutdown_mt5()

if __name__ == "__main__":
    if not MT5_AVAILABLE:
        print("错误: MetaTrader5 库未安装或无法导入。")
    else:
        check_trading_status() 