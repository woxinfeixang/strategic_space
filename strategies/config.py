# strategies/config.py
# 默认配置 for strategies 模块
# 实际运行时，这些值可以被项目根目录的全局配置覆盖

DEFAULT_CONFIG = {
    # --- 事件驱动空间策略 特定参数 ---
    'EventDrivenSpaceStrategy': {
        'strategy_params': {
            'event_importance_threshold': 2, # 最低事件重要性 (例如 1, 2, 3 星)
            # 博弈空间定义参数 (示例值)
            'space_definition': {
                # 以下为 event_driven_space_strategy.py 中使用的参数示例
                 'forward_bars': 6, # 事件后观察多少根 K 线来定义初始空间 (e.g., 6 * 30min = 3 hours)
                 'boundary_percentile': 95, # 使用 High/Low 的百分位数定义边界 (这个参数在当前代码中未直接使用，文档描述是最高/最低价)
                # 以下为 space_calculator.py build_event_space 使用的参数示例
                'time_window': {
                    'pre_event': '2h',  # 计算空间使用事件前多久的数据
                    'post_event': '4h' # 空间有效时间持续到事件后多久
                },
                'space_params': {
                    'fib_levels': [0.236, 0.382, 0.5, 0.618], # 用于计算支撑/阻力
                    'volatility_threshold': 0.8 # (示例，当前代码未使用)
                }
            },
            # 空间结束条件参数 (示例值)
            'end_conditions': {
                'strong_breakout_bars': 3, # 强突破确认 K 线数
                'oscillation_bars': 10,   # 边界震荡判断 K 线数
                'oscillation_threshold': 0.1, # 震荡判断时允许超出边界的比例
                'retrace_confirm_bars': 2   # 回撤确认 K 线数
            }
            # ... 其他 EventDrivenSpaceStrategy 特定参数
        }
    },

    # --- MT5 执行引擎 特定参数 ---
    'MT5ExecutionEngine': {
        'deviation_points': 10, # 市价单默认滑点 (单位: points)
        'magic_number': 12345,  # 策略订单的默认魔术数字
        'symbol_map': {
            # 示例: 将标准名称映射到 MT5 特定名称 (如果不同)
            # "BTC/USD": "BTCUSD",
            # "EUR/USD": "EURUSD"
        },
        # MT5 终端路径, 登录名, 密码, 服务器 通常从全局配置或环境变量获取，
        # 这里可以留空或设为 None，表示依赖外部传入。
        'terminal_path': None,
        'login': None,
        'password': None,
        'server': None,
    },

    # --- Sandbox 执行引擎 特定参数 ---
    'SandboxExecutionEngine': {
        'initial_cash': 100000, # 模拟账户初始资金
        'commission_per_trade': 0.0 # 每次交易的固定佣金 (示例)
    },

    # --- 策略调度器 (Orchestrator) 相关 ---
    'StrategyOrchestrator': {
        'enabled_strategies': {
            # 控制哪些策略会被加载和运行, True 表示启用
            'EventDrivenSpaceStrategy': True,
            # 'AnotherStrategy': False,
        },
        'run_interval_seconds': 300 # 调度器运行周期间隔 (例如 5 分钟)
    }

    # --- 通用数据提供者相关 (如果需要模块级默认值) ---
    # 'DataProvider': { ... }
}

# Helper function to potentially merge with global config later
def get_strategy_config(global_config: dict = None) -> dict:
    """
    获取策略模块的配置。
    (可选)如果提供了全局配置,可以尝试合并或覆盖默认值。
    当前实现仅返回默认配置。
    """
    # TODO: 实现更复杂的合并逻辑,例如 deep merge
    # merged_config = DEFAULT_CONFIG.copy()
    # if global_config:
    #     # Simple update (overwrites top-level keys)
    #     merged_config.update(global_config.get('strategies', {}))
    # return merged_config
    return DEFAULT_CONFIG

# 方便直接导入使用
if __name__ == '__main__':
    # 打印默认配置示例
    import json
    print(json.dumps(get_strategy_config(), indent=4)) 