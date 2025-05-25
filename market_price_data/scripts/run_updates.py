import sys
import os
from pathlib import Path
import logging

# 将项目根目录添加到 sys.path
# 假设此脚本位于 project_root/market_price_data/scripts/
# 则项目根目录是此文件路径的三级父目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

# 尝试导入更新器类
# 注意：这假设 history.py 和 realtime.py 在 market_price_data 目录下，
# 并且可以被 Python 解释器找到 (通过 __init__.py 或直接导入)
try:
    from market_price_data.history import HistoryUpdater
    from market_price_data.realtime import RealtimeUpdater
    from core.utils import setup_logging, load_app_config # 假设核心工具可用
except ImportError as e:
    print(f"Error importing updater classes or core utilities: {e}", file=sys.stderr)
    print("Please ensure the project structure is correct and core modules are accessible.", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    # --- 基本设置 ---
    # 使用一个简单的基础日志记录器，直到配置被加载
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('RunUpdatesScript')

    # --- 加载共享配置（如果需要，可以根据 updater 调整） ---
    # 假设 updater 类会自己加载其特定配置，但我们可能需要共享配置（如日志）
    # 这里简化处理，假设 updater 内部处理配置加载
    logger.info("Starting update processes...")

    # --- 运行历史数据更新 ---
    logger.info("--- Initializing and running History Updater ---")
    try:
        # HistoryUpdater 初始化时会加载其配置并设置自己的日志
        history_updater = HistoryUpdater() # 使用默认配置路径
        if history_updater and history_updater.updater_enabled:
            logger.info("History updater is enabled. Running update cycle...")
            history_updater.run_update_cycle()
            logger.info("History update cycle finished.")
        elif history_updater:
            logger.warning("History updater is disabled in its configuration. Skipping run.")
        else:
            logger.error("Failed to initialize HistoryUpdater.")
    except Exception as e:
        logger.error(f"An error occurred during history update: {e}", exc_info=True)
    logger.info("--- History Updater process complete ---")

    # --- 运行实时数据更新 ---
    # 注意: 实时更新通常是长时间运行的进程。
    # 这个脚本将启动它，但它可能会在后台继续运行（如果设计如此）。
    logger.info("--- Initializing and starting Realtime Updater ---")
    try:
        # RealtimeUpdater 初始化时会加载其配置并设置自己的日志
        realtime_updater = RealtimeUpdater() # 使用默认配置路径
        if realtime_updater and realtime_updater.updater_enabled:
            logger.info("Realtime updater is enabled. Starting updater...")
            # start_updater 通常会启动后台线程
            realtime_updater.start_updater()
            logger.info("Realtime updater started (likely running in background threads). Monitor logs for activity.")
            # 这里可能需要添加逻辑来保持主脚本运行，或者明确告知用户实时更新器已在后台启动
            # 例如，可以等待用户输入或进入一个休眠循环，除非实时更新器设计为分离进程
            # 为了简单起见，这里仅启动它
        elif realtime_updater:
            logger.warning("Realtime updater is disabled in its configuration. Skipping start.")
        else:
            logger.error("Failed to initialize RealtimeUpdater.")
    except Exception as e:
        logger.error(f"An error occurred during realtime update startup: {e}", exc_info=True)
    logger.info("--- Realtime Updater process startup attempted ---")

    logger.info("Update script finished execution (Realtime may continue in background).") 