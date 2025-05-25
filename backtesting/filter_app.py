#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Gradio 应用：可视化筛选回测结果。
"""

import gradio as gr
import json
import logging
from pathlib import Path
import pandas as pd
from typing import List, Optional

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

def filter_results_backend(
    min_sharpe: Optional[float],
    max_drawdown: Optional[float],
    min_return: Optional[float],
    min_trades: Optional[int]
) -> pd.DataFrame:
    """执行筛选逻辑并返回 DataFrame。"""
    passed_results_list = []
    if not RESULTS_DIR.is_dir():
        logger.error(f"结果目录不存在或不是一个目录: {RESULTS_DIR}")
        return pd.DataFrame(passed_results_list) # 返回空 DataFrame

    logger.info(f"扫描结果目录: {RESULTS_DIR}")
    file_count = 0
    for filepath in RESULTS_DIR.glob('*.json'):
        file_count += 1
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
        def get_metric(metric_name):
            val = metrics.get(metric_name)
            if isinstance(val, str): # Check if it's already string 'nan' or 'inf'
                if val.lower() == 'nan': return float('nan')
                if val.lower() == 'inf': return float('inf')
                if val.lower() == '-inf': return float('-inf')
            return val if isinstance(val, (int, float, type(None))) else None

        sharpe = get_metric('sharpe')
        mdd = get_metric('max_drawdown')
        cagr = get_metric('cagr') # 年化收益率
        total_return = data['results'].get('total_return') # 总收益率
        trades = data['results'].get('total_trades')
        profit_factor = get_metric('profit_factor')
        sortino = get_metric('sortino')
        calmar = get_metric('calmar')
        expectancy = data['results'].get('expectancy_per_trade')

        # --- Sharpe Ratio --- 
        if min_sharpe is not None:
            if sharpe is None or pd.isna(sharpe) or sharpe < min_sharpe:
                passes = False

        # --- Max Drawdown --- (通常是负数，比较绝对值)
        if passes and max_drawdown is not None:
             # Ensure max_drawdown input is positive for comparison
             max_drawdown_abs = abs(max_drawdown)
             if mdd is None or pd.isna(mdd) or abs(mdd) > max_drawdown_abs:
                 passes = False

        # --- Return (优先用年化，否则用总回报) ---
        if passes and min_return is not None:
            return_to_check = cagr if cagr is not None and not pd.isna(cagr) else total_return
            if return_to_check is None or pd.isna(return_to_check) or return_to_check < min_return:
                 passes = False

        # --- Min Trades ---
        if passes and min_trades is not None:
            if trades is None or pd.isna(trades) or trades < min_trades:
                passes = False

        if passes:
            logger.info(f"通过筛选: {filepath.name}")
            passed_results_list.append({
                'Filename': filepath.name,
                'Strategy': data.get('strategy_name'),
                'Start Date': data.get('backtest_config', {}).get('start_date'),
                'End Date': data.get('backtest_config', {}).get('end_date'),
                'Sharpe': sharpe,
                'Sortino': sortino,
                'Calmar': calmar,
                'Max Drawdown': mdd,
                'Return (CAGR/Total)': return_to_check,
                'Profit Factor': profit_factor,
                'Expectancy': expectancy,
                'Total Trades': trades
            })

    logger.info(f"扫描完成，共处理 {file_count} 个文件，找到 {len(passed_results_list)} 个符合条件的结果。")
    return pd.DataFrame(passed_results_list)

# --- 创建 Gradio 界面 ---
def create_gradio_interface():
    with gr.Blocks(title="回测结果筛选器") as interface:
        gr.Markdown("## 回测结果筛选器")
        gr.Markdown(f"扫描 `{RESULTS_DIR}` 目录下的 JSON 文件并根据以下条件进行筛选。留空表示不应用该条件。")

        with gr.Row():
            with gr.Column(scale=1):
                min_sharpe_input = gr.Number(label="最低夏普比率 (Min Sharpe)", value=None)
                max_drawdown_input = gr.Number(label="最大回撤容忍度 (Max Drawdown, 输入正值如 0.20)", value=None)
                min_return_input = gr.Number(label="最低回报率 (Min Return, 年化/总回报, 如 0.10)", value=None)
                min_trades_input = gr.Number(label="最少交易次数 (Min Trades)", value=None, minimum=0, step=1)
                filter_button = gr.Button("开始筛选", variant="primary")
            with gr.Column(scale=3):
                output_table = gr.DataFrame(label="筛选结果")

        filter_button.click(
            fn=filter_results_backend,
            inputs=[min_sharpe_input, max_drawdown_input, min_return_input, min_trades_input],
            outputs=output_table
        )
    return interface

# --- 主程序入口 ---
if __name__ == "__main__":
    app_interface = create_gradio_interface()
    # 启动 Gradio 应用
    # share=True 可以创建一个临时的公开链接，方便分享
    app_interface.launch(server_name="0.0.0.0") # 监听所有网络接口，方便虚拟机或 Docker 访问 