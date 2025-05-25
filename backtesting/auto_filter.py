#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
自动筛选回测结果并报告最优策略。

扫描 backtesting/results 目录下的 JSON 结果文件，
根据预设的标准进行筛选和排名，并打印报告。
"""

import json
import logging
from pathlib import Path
import pandas as pd
from typing import List, Optional, Dict, Any

# --- 预设筛选标准 --- (可以根据需要调整)
HARD_THRESHOLD = {
    "max_drawdown": 0.25,  # 最大回撤容忍度 (绝对值)
    "min_trades": 30       # 最少交易次数
}

RANKING_PRIORITY = [
    ("sharpe", False),        # 夏普比率 (降序, False 代表降序)
    ("return", False),        # 年化/总回报率 (降序)
    ("sortino", False),       # 索提诺比率 (降序)
    ("profit_factor", False)  # 盈亏比 (降序)
    # 可以添加更多排名指标和顺序 (True 代表升序)
]

# --- 日志设置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS_DIR = Path('backtesting') / 'results'

def load_result_file(filepath: Path) -> Optional[dict]:
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

def analyze_and_rank_results(results_dir: Path) -> Optional[Dict[str, Any]]:
    """扫描、筛选、排名并返回分析结果。"""
    all_results_data = []
    if not results_dir.is_dir():
        logger.error(f"结果目录不存在或不是一个目录: {results_dir}")
        return None

    logger.info(f"开始分析结果目录: {results_dir}")
    file_count = 0
    valid_file_count = 0
    passed_threshold_count = 0

    for filepath in results_dir.glob('*.json'):
        file_count += 1
        logger.debug(f"处理文件: {filepath.name}")
        data = load_result_file(filepath)
        if not data:
            continue

        # 验证数据结构
        if 'strategy_name' not in data or 'results' not in data or 'quantstats_metrics' not in data['results']:
            logger.warning(f"跳过文件 {filepath.name}: 缺少必要的键。")
            continue

        metrics = data['results'].get('quantstats_metrics')
        if not isinstance(metrics, dict) or metrics.get('error'):
            logger.warning(f"跳过文件 {filepath.name}: QuantStats 指标无效或包含错误。")
            continue
            
        valid_file_count += 1

        # 提取并转换指标 (处理 NaN/inf)
        def get_metric(metric_name):
            val = metrics.get(metric_name)
            if isinstance(val, str):
                if val.lower() == 'nan': return float('nan')
                if val.lower() == 'inf': return float('inf')
                if val.lower() == '-inf': return float('-inf')
            return val if isinstance(val, (int, float, type(None))) else None

        sharpe = get_metric('sharpe')
        mdd = get_metric('max_drawdown')
        cagr = get_metric('cagr')
        total_return = data['results'].get('total_return')
        trades = data['results'].get('total_trades')
        profit_factor = get_metric('profit_factor')
        sortino = get_metric('sortino')
        calmar = get_metric('calmar')
        expectancy = data['results'].get('expectancy_per_trade')
        return_to_check = cagr if cagr is not None and not pd.isna(cagr) else total_return

        # 应用硬性门槛
        passes_threshold = True
        if HARD_THRESHOLD["max_drawdown"] is not None:
            if mdd is None or pd.isna(mdd) or abs(mdd) > HARD_THRESHOLD["max_drawdown"]:
                logger.debug(f"{filepath.name}: 未通过 Max Drawdown 门槛 ({mdd} > {HARD_THRESHOLD['max_drawdown']})")
                passes_threshold = False

        if passes_threshold and HARD_THRESHOLD["min_trades"] is not None:
            if trades is None or pd.isna(trades) or trades < HARD_THRESHOLD["min_trades"]:
                logger.debug(f"{filepath.name}: 未通过 Min Trades 门槛 ({trades} < {HARD_THRESHOLD['min_trades']})")
                passes_threshold = False

        if passes_threshold:
            passed_threshold_count += 1
            all_results_data.append({
                'Filename': filepath.name,
                'Strategy': data.get('strategy_name'),
                'Start Date': data.get('backtest_config', {}).get('start_date'),
                'End Date': data.get('backtest_config', {}).get('end_date'),
                'sharpe': sharpe,
                'sortino': sortino,
                'calmar': calmar,
                'max_drawdown': mdd,
                'return': return_to_check,
                'profit_factor': profit_factor,
                'expectancy': expectancy,
                'total_trades': trades,
                # Store raw metrics dict for potential secondary sorting or info
                # '_metrics': metrics 
            })
        else:
             logger.info(f"策略 {data.get('strategy_name')} ({filepath.name}) 未通过硬性门槛。")

    logger.info(f"扫描完成: 共 {file_count} 个文件, {valid_file_count} 个有效结果, {passed_threshold_count} 个通过硬性门槛。")

    if not all_results_data:
        logger.warning("没有找到符合硬性门槛的回测结果。")
        return None

    # 执行排名
    # Pandas DataFrame 排序更方便处理 NaN 和多列
    results_df = pd.DataFrame(all_results_data)
    
    # 创建用于排序的列，处理 None/NaN (例如替换为极小值或极大值以保证排序正确)
    sort_columns = []
    ascending_flags = []
    for col, ascending in RANKING_PRIORITY:
        sort_columns.append(col)
        ascending_flags.append(ascending)
        # Handle potential NaN values for sorting - replace with worst possible value
        if ascending: # If ascending, NaN should be last
            results_df[col] = results_df[col].fillna(float('inf'))
        else: # If descending, NaN should be last
            results_df[col] = results_df[col].fillna(float('-inf')) 

    logger.info(f"根据优先级进行排名: {RANKING_PRIORITY}")
    ranked_df = results_df.sort_values(by=sort_columns, ascending=ascending_flags)
    
    # 将用于排序的 NaN 填充值恢复，以便显示
    ranked_df = ranked_df.replace([float('inf'), float('-inf')], pd.NA)

    # 获取最优策略
    best_strategy_info = ranked_df.iloc[0].to_dict() if not ranked_df.empty else None

    return {
        "ranked_results": ranked_df,
        "best_strategy": best_strategy_info,
        "thresholds": HARD_THRESHOLD,
        "ranking_priority": RANKING_PRIORITY
    }

def print_analysis_report(analysis: Optional[Dict[str, Any]]):
    """打印分析报告到控制台。"""
    if analysis is None:
        logger.info("无分析结果可供报告。")
        return

    print("\n" + "="*80)
    print(" AI 回测结果自动筛选与评估报告")
    print("="*80)

    print("\n1. 筛选标准:")
    print("  - 硬性门槛:")
    for key, value in analysis['thresholds'].items():
        print(f"    - {key}: {'<=' if 'max' in key else '>='} {value}")
    print("  - 排名优先级 (降序):", end=" ")
    print(", ".join([f"{col} ({'ASC' if asc else 'DESC'})" for col, asc in analysis['ranking_priority']]))

    print("\n2. 通过门槛并排名后的策略:")
    ranked_df = analysis['ranked_results']
    if ranked_df.empty:
        print("  没有策略通过硬性门槛。")
    else:
        # 选择要显示的列
        display_columns = [
            'Strategy', 'Sharpe', 'Sortino', 'Calmar', 'Max Drawdown',
            'Return (CAGR/Total)', 'Profit Factor', 'Expectancy', 'Total Trades', 'Filename'
        ]
        # 确保列存在，处理大小写和可能的缺失
        cols_to_show = []
        for col_name in display_columns:
             # Find case-insensitive match
             match = next((c for c in ranked_df.columns if c.lower() == col_name.lower()), None)
             if match:
                  cols_to_show.append(match)
                  
        # 格式化输出
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.float_format', '{:.4f}'.format)
        print(ranked_df[cols_to_show].to_string(index=False))

    print("\n3. 最优策略选择:")
    best = analysis['best_strategy']
    if best:
        print(f"  - 最优策略: {best.get('Strategy')}")
        print(f"  - 结果文件: {best.get('Filename')}")
        print(f"  - 选择理由: 该策略在满足所有硬性门槛的前提下，根据预设优先级排名最高。")
        print(f"    - 主要排名指标 (Sharpe): {best.get('sharpe'):.4f}")
    else:
        print("  未能选出最优策略 (没有策略通过门槛)。")

    print("="*80)

def main():
    analysis_results = analyze_and_rank_results(RESULTS_DIR)
    print_analysis_report(analysis_results)

if __name__ == "__main__":
    main() 