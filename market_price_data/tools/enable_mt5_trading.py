# -*- coding: utf-8 -*-
import MetaTrader5 as mt5
from pathlib import Path
import subprocess
import os
import time
import traceback
from omegaconf import DictConfig, OmegaConf
from ..utils import load_app_config, initialize_mt5, shutdown_mt5, MT5_AVAILABLE

def check_trading_enabled():
    """检查是否允许交易"""
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print("无法获取终端信息")
        return False
    
    return terminal_info.trade_allowed

def enable_trading():
    """尝试启用交易"""
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
        
        # 从配置中获取 MT5 路径
        mt5_path = mt5_config.get('terminal_path')
        if not mt5_path:
            print("在 mt5 配置部分未找到 'terminal_path'。")
            return False
        
        print(f"MT5 路径: {mt5_path}")
        print(f"使用的 MT5 配置: {OmegaConf.to_container(mt5_config, resolve=True)}")

        # 关闭现有的MT5连接 (use utility)
        print("检查并关闭现有的MT5连接 (via utility)... ")
        shutdown_mt5() # Utility handles check if initialized
        time.sleep(1)
        
        # 尝试使用/portable参数启动MT5（便携模式可能会重置某些限制）
        print("尝试以便携模式重启MT5...")
        try:
            subprocess.Popen([mt5_path, "/portable"], shell=True)
        except FileNotFoundError:
            print(f"错误: 无法找到 MT5 可执行文件于 '{mt5_path}'")
            return False
        except Exception as popen_e:
            print(f"启动 MT5 进程时出错: {popen_e}")
            return False
        
        # 等待MT5启动
        print("等待MT5启动 (10秒)... ")
        time.sleep(10)
        
        # 尝试重新连接 (use utility)
        print("尝试通过工具函数重新初始化 MT5...")
        mt5_initialized_by_util = initialize_mt5(mt5_config)
        if not mt5_initialized_by_util:
            print(f"通过工具函数重新初始化 MT5 失败。")
            return False
        else:
            print("通过工具函数重新初始化 MT5 成功。")
        
        # 检查是否允许交易
        trading_enabled = check_trading_enabled()
        print(f"交易功能当前状态: {'启用' if trading_enabled else '禁用'}")
        
        if not trading_enabled:
            print("提示：请在MT5客户端中手动启用交易功能:")
            print("1. 打开MT5客户端")
            print("2. 依次点击：工具 -> 选项 -> 交易")
            print("3. 勾选'启用交易'选项")
            print("4. 点击'确定'保存设置")
        
        return trading_enabled
    
    except Exception as e:
        print(f"启用交易时发生错误: {str(e)}")
        print(traceback.format_exc())
        return False
    
    finally:
        # 关闭MT5连接 (use utility)
        if mt5_initialized_by_util:
            print("正在关闭 MT5 连接 (via utility)... ")
            shutdown_mt5()
        else:
            # 如果重新初始化失败，尝试最后一次关闭，以防万一
            print("由于重新初始化失败，尝试最后一次关闭 MT5 连接...")
            shutdown_mt5() # Call even if init failed, as first shutdown might have failed

if __name__ == "__main__":
    print("正在尝试启用MT5交易功能...")
    if not MT5_AVAILABLE:
        print("错误: MetaTrader5 库未安装或无法导入。")
    else:
        success = enable_trading()
        print(f"\n操作结果: 交易功能已{'启用' if success else '禁用或启用失败'}")
        
        if not success:
            print("\n您也可以通过以下方法手动启用交易功能:")
            print("方法1: 在MT5界面上方工具栏找到并点击'交易'按钮")
            print("方法2: 检查账户是否有限制，可能需要联系经纪商")
            print("方法3: 确认是否在正式账户而非演示账户") 