#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python API 接口，用于访问 economic_calendar 模块的功能。
"""
import logging
import pandas as pd
import os
from typing import Optional
import sqlite3
import subprocess
import shlex

# --- 从共享 utils 导入配置加载和路径解析 ---
# 假设 api.py 位于 economic_calendar/ 下
import sys
from pathlib import Path

# 添加项目根目录到 sys.path (如果需要直接运行此文件或被其他模块调用)
# economic_calendar/api.py -> economic_calendar -> project_root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.utils import load_app_config, get_absolute_path
except ImportError as e:
     # 提供更明确的错误信息，指示可能需要将项目根添加到 PYTHONPATH
     print(f"ERROR: Failed to import shared utils: {e}. "
           "Ensure the project root directory is in your PYTHONPATH "
           "or the script is run from the project root.")
     # 尝试从可能的相对路径导入（不太推荐，但作为备用）
     try:
         # 假设 market_price_data 和 economic_calendar 是兄弟目录
         sys.path.insert(0, str(PROJECT_ROOT.parent)) # 添加上一级目录
         from core.utils import load_app_config, get_absolute_path
     except ImportError:
         raise ImportError("Could not import shared utils even after adjusting path. "
                           "Please check project structure and PYTHONPATH.") from e


logger = logging.getLogger(__name__)

def get_latest_realtime_events() -> Optional[pd.DataFrame]:
    """
    获取最新的、已筛选的实时经济日历事件。

    读取由实时工作流生成的最新筛选结果文件 (通常是 filtered_live.csv)。

    Returns:
        Optional[pd.DataFrame]: 包含事件数据的 DataFrame，如果找不到文件或出错则返回 None。
    """
    logger.info("尝试获取最新的实时经济事件...")
    try:
        config = load_app_config("economic_calendar/config/processing.yaml")
        if not config:
            logger.error("无法加载应用配置。")
            return None

        # 获取筛选后的实时数据目录路径
        filtered_live_dir_path = get_absolute_path(config, "economic_calendar.paths.filtered_live_dir")
        if not filtered_live_dir_path or not filtered_live_dir_path.is_dir():
            logger.error(f"筛选后的实时数据目录无效或未找到: {filtered_live_dir_path}")
            return None

        # 构造预期的文件名
        csv_prefix = config.get('economic_calendar', {}).get('files', {}).get('filtered_csv_prefix', 'filtered_')
        live_filename = f"{csv_prefix}live.csv"
        file_path = filtered_live_dir_path / live_filename

        if not file_path.is_file():
            logger.warning(f"未找到最新的筛选后实时数据文件: {file_path}")
            return None

        logger.info(f"正在读取实时事件文件: {file_path}")
        # 使用 pandas 读取 CSV
        df = pd.read_csv(file_path, encoding=config.get('economic_calendar', {}).get('export', {}).get('csv_encoding', 'utf-8'))
        logger.info(f"成功加载 {len(df)} 条实时事件。")
        return df

    except Exception as e:
        logger.error(f"获取最新实时事件时出错: {e}", exc_info=True)
        return None

def get_historical_events(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    获取指定日期范围内的、已处理的历史经济日历事件。

    从 SQLite 数据库中查询数据。

    Args:
        start_date (str): 开始日期 (YYYY-MM-DD)。
        end_date (str): 结束日期 (YYYY-MM-DD)。

    Returns:
        Optional[pd.DataFrame]: 包含事件数据的 DataFrame，如果出错则返回 None。
    """
    logger.info(f"尝试获取历史经济事件 (日期范围: {start_date} 到 {end_date})...")
    conn = None
    try:
        config = load_app_config("economic_calendar/config/processing.yaml")
        if not config:
            logger.error("无法加载应用配置。")
            return None

        # 获取数据库文件路径
        db_dir_path = get_absolute_path(config, "economic_calendar.paths.db_dir")
        if not db_dir_path or not db_dir_path.is_dir():
            logger.error(f"数据库目录无效或未找到: {db_dir_path}")
            return None
        db_filename = config.get('economic_calendar', {}).get('files', {}).get('events_db', 'economic_events.db')
        db_filepath = db_dir_path / db_filename

        if not db_filepath.is_file():
            logger.error(f"数据库文件未找到: {db_filepath}")
            return None

        # 获取表名
        table_name = config.get('economic_calendar', {}).get('db_table_name', 'events')

        logger.info(f"连接到数据库: {db_filepath}")
        conn = sqlite3.connect(str(db_filepath))

        # 构造 SQL 查询
        # 假设数据库中的 Date 列是 YYYY-MM-DD 格式的文本
        query = f"SELECT * FROM {table_name} WHERE Date BETWEEN ? AND ? ORDER BY Date, Time" # 使用参数化查询
        logger.debug(f"执行 SQL 查询: {query} (参数: {start_date}, {end_date})")

        # 使用 pandas 读取数据
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))

        logger.info(f"成功从数据库加载 {len(df)} 条历史事件。")
        return df

    except sqlite3.Error as db_err:
        logger.error(f"查询数据库时出错: {db_err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"获取历史事件时出错: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()
            logger.debug("数据库连接已关闭。")

def trigger_realtime_update() -> bool:
    """
    触发实时经济日历数据的下载和处理工作流。

    通过执行 `run_realtime_workflow.py` 脚本来完成。

    Returns:
        bool: 如果工作流成功执行则返回 True，否则返回 False。
    """
    logger.info("尝试触发实时数据更新工作流...")
    try:
        config = load_app_config("economic_calendar/config/processing.yaml")
        if not config:
            logger.error("无法加载应用配置以触发实时更新。")
            return False

        # 确定工作流脚本的路径
        # 假设 tasks 目录与 api.py 的父目录 (economic_calendar) 同级
        tasks_dir = PROJECT_ROOT / "economic_calendar" / "tasks"
        workflow_script_name = config.get("economic_calendar", {}).get("workflows", {}).get("realtime_script", "run_realtime_workflow.py")
        workflow_script_path = tasks_dir / workflow_script_name

        if not workflow_script_path.is_file():
            logger.error(f"实时工作流脚本未找到: {workflow_script_path}")
            return False

        # 使用 subprocess 执行脚本
        # 确保使用 Python 解释器执行 .py 文件
        # 使用 sys.executable 来获取当前 Python 解释器的路径
        command = f'"{sys.executable}" "{workflow_script_path}"'
        logger.info(f"执行命令: {command}")

        # 使用 shlex.split 来正确处理路径中的空格
        # cwd 设置为项目根目录，以确保脚本内部的相对路径正确解析
        result = subprocess.run(shlex.split(command),
                                capture_output=True,
                                text=True,
                                check=False, # 设置为 False，手动检查返回码
                                cwd=PROJECT_ROOT)

        if result.returncode == 0:
            logger.info("实时数据更新工作流成功完成。")
            logger.debug(f"脚本输出:\n{result.stdout}")
            return True
        else:
            logger.error(f"实时数据更新工作流执行失败。返回码: {result.returncode}")
            logger.error(f"脚本错误输出:\n{result.stderr}")
            return False

    except Exception as e:
        logger.error(f"触发实时数据更新工作流时发生意外错误: {e}", exc_info=True)
        return False

def trigger_historical_update(start_date: Optional[str] = None, end_date: Optional[str] = None) -> bool:
    """
    触发历史经济日历数据的下载和处理工作流。

    通过执行 `run_historical_workflow.py` 脚本来完成。
    可以接受可选的开始和结束日期作为参数传递给脚本。

    Args:
        start_date (Optional[str]): 开始日期 (YYYY-MM-DD)。如果提供，会传递给工作流脚本。
        end_date (Optional[str]): 结束日期 (YYYY-MM-DD)。如果提供，会传递给工作流脚本。

    Returns:
        bool: 如果工作流成功执行则返回 True，否则返回 False。
    """
    logger.info("尝试触发历史数据更新工作流...")
    try:
        config = load_app_config("economic_calendar/config/processing.yaml")
        if not config:
            logger.error("无法加载应用配置以触发历史更新。")
            return False

        # 确定工作流脚本的路径
        tasks_dir = PROJECT_ROOT / "economic_calendar" / "tasks"
        workflow_script_name = config.get("economic_calendar", {}).get("workflows", {}).get("historical_script", "run_historical_workflow.py")
        workflow_script_path = tasks_dir / workflow_script_name

        if not workflow_script_path.is_file():
            logger.error(f"历史工作流脚本未找到: {workflow_script_path}")
            return False

        # 构造命令，包括可选的日期参数
        command_parts = [f'"{sys.executable}"', f'"{workflow_script_path}"']
        if start_date:
            command_parts.append(f'--start_date "{start_date}"')
        if end_date:
            command_parts.append(f'--end_date "{end_date}"')

        command = " ".join(command_parts)
        logger.info(f"执行命令: {command}")

        # 使用 subprocess 执行脚本
        result = subprocess.run(shlex.split(command),
                                capture_output=True,
                                text=True,
                                check=False,
                                cwd=PROJECT_ROOT)

        if result.returncode == 0:
            logger.info("历史数据更新工作流成功完成。")
            logger.debug(f"脚本输出:\n{result.stdout}")
            return True
        else:
            logger.error(f"历史数据更新工作流执行失败。返回码: {result.returncode}")
            logger.error(f"脚本错误输出:\n{result.stderr}")
            return False

    except Exception as e:
        logger.error(f"触发历史数据更新工作流时发生意外错误: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    # 用于测试 API 函数
    print("--- 测试 get_latest_realtime_events ---")
    latest_events_df = get_latest_realtime_events()
    if latest_events_df is not None:
        print("成功获取最新实时事件:")
        print(latest_events_df.head())
    else:
        print("获取最新实时事件失败。")

    # --- 添加 get_historical_events 测试 ---
    print("\n--- 测试 get_historical_events ---")
    # 示例日期范围，请根据您的数据调整
    test_start_date = "2024-01-01"
    test_end_date = "2024-01-31"
    historical_events_df = get_historical_events(test_start_date, test_end_date)
    if historical_events_df is not None:
        print(f"成功获取 {test_start_date} 到 {test_end_date} 的历史事件:")
        print(historical_events_df.head())
        print(f"(共 {len(historical_events_df)} 条)")
    else:
        print(f"获取 {test_start_date} 到 {test_end_date} 的历史事件失败。")

    # --- 添加 trigger_realtime_update 测试 ---
    print("\n--- 测试 trigger_realtime_update ---")
    # 注意：这将实际执行工作流脚本
    # success = trigger_realtime_update()
    # if success:
    #     print("实时工作流触发成功。")
    # else:
    #     print("实时工作流触发失败。")
    # 建议手动测试或在需要时取消注释上面的代码
    print("(触发实时工作流的测试默认注释掉，以避免意外执行)")

    # --- 添加 trigger_historical_update 测试 ---
    print("\n--- 测试 trigger_historical_update ---")
    # 注意：这将实际执行工作流脚本
    # test_hist_start = "2024-01-01"
    # test_hist_end = "2024-01-05"
    # success_hist = trigger_historical_update(start_date=test_hist_start, end_date=test_hist_end)
    # if success_hist:
    #     print(f"历史工作流触发成功 (日期: {test_hist_start} 到 {test_hist_end})。")
    # else:
    #     print(f"历史工作流触发失败 (日期: {test_hist_start} 到 {test_hist_end})。")
    # 建议手动测试或在需要时取消注释上面的代码
    print("(触发历史工作流的测试默认注释掉，以避免意外执行)")

    # 在这里可以添加对其他 API 函数的测试调用 