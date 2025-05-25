import argparse
import logging
import sys
import time
import signal # 用于更优雅地处理 SIGINT (Ctrl+C)
from typing import Optional # <-- 添加导入

# 尝试导入更新器类和核心工具
try:
    from market_price_data.history import HistoryUpdater
    from market_price_data.realtime import RealtimeUpdater
    # 虽然此脚本不直接用 utils，但更新器类会用
    # from core.utils import setup_logging # 可能需要在这里早期设置日志
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logging.error("无法导入 HistoryUpdater 或 RealtimeUpdater。请确保它们存在且 market_price_data 包在 Python 路径中。", exc_info=True)
    sys.exit(1)

# 全局变量，用于信号处理
shutdown_requested = False
realtime_updater_instance: Optional[RealtimeUpdater] = None

def handle_signal(signum, frame):
    """信号处理函数，用于优雅地停止实时更新器"""
    global shutdown_requested, realtime_updater_instance
    if not shutdown_requested:
        print("\n收到停止信号 (Ctrl+C)... 正在尝试优雅停止...", file=sys.stderr)
        shutdown_requested = True
        if realtime_updater_instance:
            # 调用 stop_updater 会设置内部事件并等待线程退出
            # 不再需要在这里直接操作 stop_event
            realtime_updater_instance.stop_updater()
    else:
        print("\n已在停止过程中，请稍候...", file=sys.stderr)

def main():
    global realtime_updater_instance # 允许信号处理函数访问实例

    # --- 基本日志配置 (在加载应用配置前) ---
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('DataUpdaterCLI')

    # --- 参数解析 ---
    parser = argparse.ArgumentParser(description="MT5 数据更新器命令行工具")
    subparsers = parser.add_subparsers(dest='command', help='选择要执行的操作 (history 或 realtime)', required=True)

    # --- 通用参数 --- (适用于两个子命令)
    common_parser = argparse.ArgumentParser(add_help=False) # 父解析器，不直接使用
    common_parser.add_argument(
        '-c', '--config', 
        default='market_price_data/config/updater.yaml', 
        help='模块特定配置文件的相对路径 (默认: market_price_data/config/updater.yaml)'
    )
    common_parser.add_argument(
        '-s', '--symbols', 
        nargs='+', 
        help='(可选) 要处理的品种列表 (覆盖配置文件)'
    )
    common_parser.add_argument(
        '-t', '--timeframes', 
        nargs='+', 
        help='(可选) 要处理的时间周期列表 (覆盖配置文件)'
    )
    common_parser.add_argument(
        '-l', '--log-level', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
        help='(可选) 覆盖配置文件中的日志级别'
    )

    # --- history 子命令 ---
    parser_history = subparsers.add_parser('history', parents=[common_parser], help='运行历史数据更新')
    # history 特有的参数可以加在这里

    # --- realtime 子命令 ---
    parser_realtime = subparsers.add_parser('realtime', parents=[common_parser], help='运行实时数据监控')
    parser_realtime.add_argument(
        '--timeout', 
        type=int, 
        default=0, 
        help='(可选) 运行超时时间(秒)。0 表示无限期运行，直到手动中断。'
    )

    args = parser.parse_args()

    # TODO: 实现将命令行参数 args.symbols, args.timeframes, args.log_level 
    #       传递给 Updater 类或用于覆盖加载后的配置。
    #       目前 Updater 类在 __init__ 中直接加载配置文件。
    logger.warning("命令行参数覆盖配置的功能尚未完全实现。当前将使用配置文件中的设置。")

    # --- 执行命令 ---
    if args.command == 'history':
        logger.info("执行历史数据更新...")
        try:
            updater = HistoryUpdater(config_rel_path=args.config)
            if updater.config and updater.updater_enabled:
                # TODO: 在这里根据 args.log_level 重新配置日志级别 (如果提供)
                # TODO: 根据 args.symbols, args.timeframes 筛选或修改 updater 内部列表
                logger.info("启动历史数据更新周期...")
                updater.run_update_cycle()
                logger.info("历史数据更新完成。")
            else:
                logger.warning("历史数据更新器未启用或初始化失败，操作未执行。")
        except Exception as e:
            logger.error(f"运行历史数据更新时发生错误: {e}", exc_info=True)
            sys.exit(1)

    elif args.command == 'realtime':
        logger.info("执行实时数据监控...")
        
        # 注册信号处理程序 (仅用于实时模式)
        signal.signal(signal.SIGINT, handle_signal) # 处理 Ctrl+C
        signal.signal(signal.SIGTERM, handle_signal) # 处理 kill 命令

        try:
            realtime_updater_instance = RealtimeUpdater(config_rel_path=args.config)
            if realtime_updater_instance.config and realtime_updater_instance.updater_enabled:
                # TODO: 参数覆盖逻辑
                logger.info("启动实时数据监控器...")
                realtime_updater_instance.start_updater()
                logger.info("实时监控已启动。按 Ctrl+C 停止。")

                start_time = time.time()
                while not shutdown_requested:
                    # 检查超时
                    if args.timeout > 0 and (time.time() - start_time) > args.timeout:
                        logger.info(f"达到超时时间 ({args.timeout}秒)，正在停止...")
                        shutdown_requested = True # 标记为请求关闭
                        realtime_updater_instance.stop_updater()
                        break
                    
                    # 检查监控线程是否意外退出 (可选)
                    # all_threads_alive = True
                    # for t in realtime_updater_instance._threads:
                    #     if not t.is_alive():
                    #         logger.warning(f"监控线程 {t.name} 已意外退出！")
                    #         all_threads_alive = False
                    # if not all_threads_alive and not shutdown_requested:
                    #     logger.error("一个或多个监控线程意外终止，停止更新器。")
                    #     shutdown_requested = True
                    #     realtime_updater_instance.stop_updater()
                    #     break
                    
                    # 主线程短暂休眠，避免 CPU 空转
                    time.sleep(1)

            else:
                logger.warning("实时数据更新器未启用或初始化失败，操作未执行。")

        except Exception as e:
            logger.error(f"运行实时数据监控时发生错误: {e}", exc_info=True)
            # 确保即使发生异常也尝试停止更新器
            if realtime_updater_instance and realtime_updater_instance.mt5_initialized:
                 logger.info("发生错误后尝试停止更新器...")
                 realtime_updater_instance.stop_updater()
            sys.exit(1)
        finally:
            # 确保在退出前（无论是正常停止还是异常）都尝试停止
            if realtime_updater_instance and not shutdown_requested: # 如果没有通过信号或超时停止
                 logger.info("程序退出前确保停止更新器...")
                 realtime_updater_instance.stop_updater()
            logger.info("实时数据监控程序结束。")

if __name__ == '__main__':
    main() 