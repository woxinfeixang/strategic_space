import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json
from datetime import datetime
import logging # 添加 logging

# 假设 trades_analyzer 和 plotter_instance 会被 BacktestEngine 提供
# 或者 BacktestEngine 直接提供 trades DataFrame 和 equity DataFrame

logger = logging.getLogger(__name__) # 初始化 logger

class BacktestAnalyzer:
    """
    负责分析回测结果、计算性能指标并生成可视化报告。
    修改为接收更通用的输入：包含基本结果的字典、交易列表 DataFrame、资金曲线 DataFrame。
    """
    # def __init__(self, results: dict, trades_analyzer, plotter_instance): # 旧接口
    def __init__(self, results: dict, trades_df: Optional[pd.DataFrame] = None, equity_curve_df: Optional[pd.DataFrame] = None):
        """
        初始化分析器。

        Args:
            results (dict): 从 BacktestEngine.run() 返回的基本结果字典。
                           应包含 'strategy_name', 'instrument', 'final_portfolio_value' 等。
            trades_df (Optional[pd.DataFrame]): 包含模拟交易记录的 DataFrame。
                                            预期列: 'timestamp', 'symbol', 'action' (BUY/SELL), 
                                                  'quantity', 'price', 'commission', 'pnl', 'return' (ratio)。
            equity_curve_df (Optional[pd.DataFrame]): 包含资金曲线的 DataFrame。
                                                  预期索引为时间戳 (UTC)，包含 'Equity' 列。
        """
        self.results = results
        self.trades_df = trades_df if trades_df is not None else pd.DataFrame()
        self.equity_curve_df = equity_curve_df if equity_curve_df is not None else pd.DataFrame()

        # 从 results 或 trades_df/equity_curve_df 推断信息
        self.strategy_name = results.get('strategy_name', 'UnknownStrategy')
        # 尝试从交易记录推断品种，如果 results 中没有
        if 'instrument' in results:
            self.instrument = results.get('instrument', 'UnknownInstrument')
        elif not self.trades_df.empty and 'symbol' in self.trades_df.columns:
            unique_symbols = self.trades_df['symbol'].unique()
            self.instrument = ", ".join(unique_symbols) if len(unique_symbols) > 0 else 'Multi/Unknown'
        else:
             self.instrument = 'UnknownInstrument'

        # 确保 equity_curve_df 索引是 DatetimeIndex
        if not isinstance(self.equity_curve_df.index, pd.DatetimeIndex) and not self.equity_curve_df.empty:
             logger.warning("Equity curve DataFrame index is not a DatetimeIndex. Plotting might fail.")


    def _calculate_metrics(self) -> dict:
        """
        计算性能指标。
        """
        metrics = self.results.copy() # 从引擎结果开始

        # 从 trades_df 计算交易相关指标
        if not self.trades_df.empty:
            all_trades = len(self.trades_df)
            # 假设 DataFrame 有 'pnl' 列
            if 'pnl' in self.trades_df.columns:
                profitable_trades = self.trades_df[self.trades_df['pnl'] > 0]
                unprofitable_trades = self.trades_df[self.trades_df['pnl'] < 0]
                profitable_count = len(profitable_trades)
                unprofitable_count = len(unprofitable_trades)

                metrics['total_trades'] = all_trades
                metrics['profitable_trades'] = profitable_count
                metrics['unprofitable_trades'] = unprofitable_count
                metrics['win_rate_percentage'] = (profitable_count / all_trades * 100) if all_trades > 0 else 0

                # 假设 DataFrame 有 'return' 列 (百分比或小数)
                if 'return' in self.trades_df.columns:
                    # 确保 return 列是数值类型
                    self.trades_df['return'] = pd.to_numeric(self.trades_df['return'], errors='coerce')
                    returns = self.trades_df['return'].dropna()
                    if not returns.empty:
                        metrics['average_trade_return_percentage'] = returns.mean() * 100 # 假设 return 是小数
                        metrics['std_dev_trade_return_percentage'] = returns.std() * 100
                        gross_profit_ret = returns[returns > 0].sum()
                        gross_loss_ret = abs(returns[returns < 0].sum())
                        metrics['profit_factor'] = (gross_profit_ret / gross_loss_ret) if gross_loss_ret > 0 else float('inf')
                    else:
                         metrics['average_trade_return_percentage'] = 0
                         metrics['std_dev_trade_return_percentage'] = 0
                         metrics['profit_factor'] = 0
                else:
                     logger.warning("Trades DataFrame 缺少 'return' 列，无法计算收益率相关指标。")

                metrics['total_net_pnl'] = self.trades_df['pnl'].sum()
                metrics['average_pnl_per_trade'] = metrics['total_net_pnl'] / all_trades if all_trades > 0 else 0
                metrics['average_winning_trade_pnl'] = profitable_trades['pnl'].mean() if profitable_count > 0 else 0
                metrics['average_losing_trade_pnl'] = unprofitable_trades['pnl'].mean() if unprofitable_count > 0 else 0
                if metrics['average_losing_trade_pnl'] != 0:
                    metrics['win_loss_ratio'] = abs(metrics['average_winning_trade_pnl'] / metrics['average_losing_trade_pnl'])
                else:
                     metrics['win_loss_ratio'] = float('inf') if metrics['average_winning_trade_pnl'] > 0 else 0

            else:
                 logger.warning("Trades DataFrame 缺少 'pnl' 列，无法计算 PnL 相关指标。")
        else:
             logger.info("没有交易记录可供分析。")
             metrics['total_trades'] = 0

        # 从 equity_curve_df 计算资金曲线相关指标
        if not self.equity_curve_df.empty and 'Equity' in self.equity_curve_df.columns:
            equity = self.equity_curve_df['Equity']
            metrics['final_portfolio_value'] = equity.iloc[-1]
            # 计算最大回撤
            rolling_max = equity.cummax()
            drawdown = (equity - rolling_max) / rolling_max
            max_drawdown_pct = abs(drawdown.min()) * 100
            metrics['max_drawdown_percentage'] = max_drawdown_pct

            # 计算年化收益率和夏普比率 (需要更复杂的计算，可能需要日收益率)
            # TODO: 实现更精确的 Sharpe Ratio 和 Annualized Return 计算
            # 这里只是占位符或简化计算
            returns_pct = equity.pct_change().dropna()
            if not returns_pct.empty:
                 # 假设无风险利率为0，简化 Sharpe 计算
                 sharpe_ratio_simple = returns_pct.mean() / returns_pct.std() if returns_pct.std() != 0 else 0
                 # 假设年化因子 (需要根据数据频率调整，例如日频是 252)
                 annualization_factor = 252 # 假设是日频资金曲线
                 metrics['sharpe_ratio_simple'] = sharpe_ratio_simple * (annualization_factor ** 0.5)
                 # 简单年化收益
                 total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
                 years = (equity.index[-1] - equity.index[0]).days / 365.25
                 if years > 0:
                      metrics['annualized_return_simple_percentage'] = ((1 + total_return) ** (1/years) - 1) * 100
                 else:
                      metrics['annualized_return_simple_percentage'] = total_return * 100 # 如果时间太短，不年化


        # 格式化指标
        metrics_formatted = {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                metrics_formatted[key] = round(value, 4)
            else:
                 metrics_formatted[key] = value # 保留非数值类型

        return metrics_formatted

    def _plot_equity_curve(self) -> go.Figure:
        """
        使用 Plotly 绘制资金曲线。
        """
        fig = go.Figure()
        if not self.equity_curve_df.empty and 'Equity' in self.equity_curve_df.columns:
            fig.add_trace(go.Scatter(x=self.equity_curve_df.index, y=self.equity_curve_df['Equity'], mode='lines', name='Equity Curve'))
            fig.update_layout(
                title=f"Equity Curve - {self.strategy_name} ({self.instrument})",
                xaxis_title="Date",
                yaxis_title="Portfolio Value",
                hovermode="x unified"
            )
        else:
             fig.update_layout(title="Equity Curve (No data available)")
        return fig

    def _plot_drawdown(self) -> go.Figure:
        """
        使用 Plotly 绘制 Drawdown 曲线。
        """
        fig = go.Figure()
        if not self.equity_curve_df.empty and 'Equity' in self.equity_curve_df.columns:
            # Calculate Drawdown
            equity = self.equity_curve_df['Equity']
            rolling_max = equity.cummax()
            drawdown = (equity - rolling_max) / rolling_max * 100 # Percentage
            drawdown = drawdown.fillna(0) # Fill NaN at the beginning

            fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, mode='lines', name='Drawdown (%)', fill='tozeroy', line_color='red'))
            fig.update_layout(
                title=f"Drawdown (%) - {self.strategy_name} ({self.instrument})",
                xaxis_title="Date",
                yaxis_title="Drawdown (%)",
                 yaxis_range=[min(-0.5, drawdown.min() * 1.1), 5] # 动态调整Y轴范围
            )
        else:
            fig.update_layout(title="Drawdown (No data available)")
        return fig

    # TODO: 添加绘制交易点位的图表 (需要 K 线数据)

    def generate_report(self, output_dir: str, kline_data: Optional[Dict[str, pd.DataFrame]] = None) -> str:
        """
        生成包含指标和图表的回测报告 (HTML 格式)。

        Args:
            output_dir (str): 保存报告的目录。
            kline_data (Optional[Dict[str, pd.DataFrame]]): 可选的 K 线数据，用于绘制交易点位。
                                                         键为 symbol，值为包含 OHLC 的 DataFrame。

        Returns:
            str: 生成的 HTML 报告文件的完整路径或错误信息。
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"创建报告输出目录失败: {output_dir}, 错误: {e}")
            return f"Error: Cannot create output directory {output_dir}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"backtest_{self.strategy_name}_{self.instrument.replace(', ', '_')}_{timestamp}.html"
        report_path = os.path.join(output_dir, report_filename)

        # 1. 计算所有指标
        all_metrics = self._calculate_metrics()

        # 2. 创建图表
        fig_equity = self._plot_equity_curve()
        fig_drawdown = self._plot_drawdown()
        # fig_trades = self._plot_trades(kline_data) # TODO

        # 3. 构建 HTML 报告
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Backtest Report: {self.strategy_name} ({self.instrument})</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; }}
                h1, h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: auto; max-width: 800px; margin-bottom: 20px; font-size: 0.9em; }}
                th, td {{ border: 1px solid #ddd; padding: 6px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .plotly-graph-div {{ margin-bottom: 30px; width: 95%; max-width: 1000px; }}
            </style>
            <script src='https://cdn.plot.ly/plotly-latest.min.js'></script>
        </head>
        <body>
            <h1>Backtest Report</h1>
            <h2>Strategy: {self.strategy_name}</h2>
            <h2>Instrument(s): {self.instrument}</h2>
            <p>Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            
            <h2>Performance Metrics</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
        """
        sorted_metrics = sorted(all_metrics.items())
        for key, value in sorted_metrics:
            # Format metric names nicely
            metric_name = key.replace('_', ' ').title()
            # Add percentage sign where appropriate
            if 'percentage' in key.lower():
                 metric_name = metric_name.replace(' Percentage', ' (%)')
            html_content += f"<tr><td>{metric_name}</td><td>{value}</td></tr>\n"

        html_content += """
            </table>

            <h2>Charts</h2>
            <div id='equity_curve_plot'></div>
            <div id='drawdown_plot'></div>
            <!-- <div id='trades_plot'></div> TODO -->
            
            <script>
                var figEquityJson = {fig_equity.to_json()};
                var figDrawdownJson = {fig_drawdown.to_json()};
                // var figTradesJson = {fig_trades.to_json()}; TODO
                
                Plotly.newPlot('equity_curve_plot', figEquityJson.data, figEquityJson.layout);
                Plotly.newPlot('drawdown_plot', figDrawdownJson.data, figDrawdownJson.layout);
                // Plotly.newPlot('trades_plot', figTradesJson.data, figTradesJson.layout); TODO
            </script>
            
        </body>
        </html>
        """

        # 4. 保存 HTML 文件
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Successfully generated report: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Error writing report file {report_path}: {e}")
            return f"Error: {e}" 