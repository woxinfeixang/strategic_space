#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
回测结果筛选脚本

扫描 backtesting/results 目录下的 JSON 结果文件，
并根据指定的条件筛选出符合要求的策略回测。
"""

import json
import argparse
import logging
from pathlib import Path
import pandas as pd # 用于处理 NaN 和 inf

# --- 日志设置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_result_file(filepath: Path) -> dict:
    """加载单个 JSON 结果文件。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        logger.error(f"无法解析 JSON 文件: {filepath}")
        return None
    except Exception as e:
        logger.error(f"读取结果文件时出错 {filepath}: {e}")
        return None

def filter_results(results_dir: Path, criteria: argparse.Namespace) -> List[dict]:
    """扫描目录，加载结果，并应用筛选条件。"""
    passed_results = []
    if not results_dir.is_dir():
        logger.error(f"结果目录不存在或不是一个目录: {results_dir}")
        return []

    logger.info(f"扫描结果目录: {results_dir}")
    for filepath in results_dir.glob('*.json'):
        logger.debug(f"处理文件: {filepath.name}")
        data = load_result_file(filepath)
        if not data:
            continue

        # 检查基本结构
        if 'strategy_name' not in data or 'results' not in data or 'quantstats_metrics' not in data['results']:
            logger.warning(f"跳过文件 {filepath.name}: 缺少必要的键 (strategy_name, results.quantstats_metrics)")
            continue

        metrics = data['results'].get('quantstats_metrics')
        if not isinstance(metrics, dict) or metrics.get('error'):
            logger.warning(f"跳过文件 {filepath.name}: QuantStats 指标无效或包含错误。")
            continue

        # 应用筛选条件
        passes = True
        # 处理 NaN 和 inf
        def get_metric(metric_name):
            val = metrics.get(metric_name)
            if isinstance(val, str): # Check if it's already string 'nan' or 'inf'
                if val.lower() == 'nan': return float('nan')
                if val.lower() == 'inf': return float('inf')
                if val.lower() == '-inf': return float('-inf')
            # Allow None or numerical types
            return val if isinstance(val, (int, float, type(None))) else None

        min_sharpe = criteria.min_sharpe
        max_drawdown = criteria.max_drawdown
        min_return = criteria.min_return
        min_trades = criteria.min_trades

        sharpe = get_metric('sharpe')
        mdd = get_metric('max_drawdown')
        cagr = get_metric('cagr') # 年化收益率
        total_return = data['results'].get('total_return') # 总收益率
        trades = data['results'].get('total_trades')

        # --- Sharpe Ratio --- 
        if min_sharpe is not None:
            if sharpe is None or pd.isna(sharpe) or sharpe < min_sharpe:
                logger.debug(f"{filepath.name}: 未通过 Sharpe ({sharpe} < {min_sharpe})")
                passes = False

        # --- Max Drawdown --- (通常是负数，比较绝对值)
        if passes and max_drawdown is not None:
            if mdd is None or pd.isna(mdd) or abs(mdd) > abs(max_drawdown):
                logger.debug(f"{filepath.name}: 未通过 Max Drawdown ({mdd} > {max_drawdown})")
                passes = False

        # --- Return (优先用年化，否则用总回报) ---
        if passes and min_return is not None:
            return_to_check = cagr if cagr is not None and not pd.isna(cagr) else total_return
            if return_to_check is None or pd.isna(return_to_check) or return_to_check < min_return:
                 logger.debug(f"{filepath.name}: 未通过 Return ({return_to_check} < {min_return})")
                 passes = False

        # --- Min Trades ---
        if passes and min_trades is not None:
            if trades is None or pd.isna(trades) or trades < min_trades:
                logger.debug(f"{filepath.name}: 未通过 Min Trades ({trades} < {min_trades})")
                passes = False

        if passes:
            logger.info(f"通过筛选: {filepath.name}")
            # 添加文件名和关键指标到结果列表，方便查看
            passed_results.append({
                'filename': filepath.name,
                'strategy_name': data.get('strategy_name'),
                'start_date': data.get('backtest_config', {}).get('start_date'),
                'end_date': data.get('backtest_config', {}).get('end_date'),
                'sharpe': sharpe,
                'max_drawdown': mdd,
                'return': return_to_check,
                'total_trades': trades
            })

    return passed_results

def main():
    parser = argparse.ArgumentParser(description='筛选回测结果文件。')
    parser.add_argument(
        '--results-dir',
        type=str,
        default='backtesting/results',
        help='包含回测结果 JSON 文件的目录路径。'
    )
    # 添加筛选条件的参数
    parser.add_argument('--min-sharpe', type=float, default=None, help='最低夏普比率要求。')
    parser.add_argument('--max-drawdown', type=float, default=None, help='最大回撤容忍度 (例如 0.25 表示 25%)。注意是绝对值比较。')
    parser.add_argument('--min-return', type=float, default=None, help='最低年化收益率 (优先) 或总收益率要求 (例如 0.15 表示 15%)。')
    parser.add_argument('--min-trades', type=int, default=None, help='最少交易次数要求。')

    args = parser.parse_args()

    results_directory = Path(args.results_dir)
    filtered = filter_results(results_directory, args)

    if not filtered:
        logger.info("没有找到符合所有筛选条件的回测结果。")
    else:
        logger.info(f"\n--- 符合筛选条件的回测结果 ({len(filtered)} 个) --- ")
        # 打印总结
        output_df = pd.DataFrame(filtered)
        # 格式化输出
        pd.set_option('display.float_format', '{:.4f}'.format)
        print(output_df.to_string(index=False))
        logger.info("---------------------------------------")

if __name__ == "__main__":
    main() 