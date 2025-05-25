import MetaTrader5 as mt5
import sys
from pathlib import Path
import traceback
from omegaconf import DictConfig, OmegaConf
from ..utils import load_app_config, initialize_mt5, shutdown_mt5, MT5_AVAILABLE

def check_mt5_status():
    config: Optional[DictConfig] = None # Initialize config
    mt5_initialized_by_util = False
    try:
        print("开始检查MT5状态...")
        
        # 加载配置 using utility
        try:
            config = load_app_config('market_price_data')
            print("配置文件加载成功。")
        except Exception as load_err:
            print(f"无法加载配置文件: {load_err}")
            return False

        if not config:
            print("加载的配置为空。")
            return False
            
        # 获取MT5配置 (从 OmegaConf 对象)
        mt5_config = OmegaConf.select(config, 'mt5')
        if not mt5_config:
            print("在配置中未找到 'mt5' 部分。")
            return False

        print(f"MT5 配置部分: {OmegaConf.to_container(mt5_config, resolve=True)}") # Print resolved config
        
        # 初始化MT5 using utility
        print("尝试通过工具函数初始化MT5...")
        mt5_initialized_by_util = initialize_mt5(mt5_config) # Pass mt5 config section
        
        if not mt5_initialized_by_util:
            # initialize_mt5 应该已经记录了错误
            print("通过工具函数初始化 MT5 失败。")
            return False
        else:
            print("通过工具函数初始化 MT5 成功。")
            
        # 获取MT5版本 (需要确保已初始化)
        version = mt5.version()
        print(f"MT5版本: {version}")
        
        # 获取终端信息
        print("尝试获取终端信息...")
        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            # MT5 可能在获取信息时断开连接
            last_error = mt5.last_error()
            print(f"无法获取MT5终端信息。 错误: {last_error}")
            # 不需要返回 False，可能只是暂时问题，但后面会关闭连接
            # return False
        else:
            print(f"终端名称: {terminal_info.name}")
            print(f"连接状态: {terminal_info.connected}")
            print(f"允许交易: {terminal_info.trade_allowed}")
        
        # 主要检查连接状态
        # return terminal_info.connected if terminal_info else False
        # 改为直接返回初始化结果，因为 initialize_mt5 内部应该已经检查了连接
        return mt5_initialized_by_util
        
    except Exception as e:
        print(f"检查MT5状态时发生错误: {str(e)}")
        print(f"错误详情:\n{traceback.format_exc()}")
        return False
        
    finally:
        # 关闭MT5连接 using utility
        print("尝试通过工具函数关闭MT5连接...")
        # 仅在由工具成功初始化时调用关闭，避免重复关闭或在未初始化时关闭
        if mt5_initialized_by_util:
            shutdown_mt5() # Use utility function
            print("已调用工具函数关闭 MT5 连接。")
        else:
            print("跳过关闭 MT5 连接，因为它未被此脚本成功初始化。")

if __name__ == "__main__":
    print("脚本开始执行...")
    # Check MT5 library availability first
    if not MT5_AVAILABLE:
        print("错误: MetaTrader5 库未安装或无法导入。请先安装。")
    else:
        result = check_mt5_status()
        print(f"检查结果: {'成功' if result else '失败'}")
    print("脚本执行结束") 