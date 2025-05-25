# MT5数据更新系统使用说明

## 系统概述

MT5数据更新系统是一个专为量化交易设计的工具，用于自动从MetaTrader 5平台获取历史数据和实时行情数据。系统采用模块化设计，分为历史数据更新和实时数据更新两个主要组件，可独立或同时运行。

### 主要功能

1. **历史数据管理**
   - 自动下载并更新多种交易品种的历史K线数据
   - 支持多种时间周期（M1, M5, M15, M30, H1, H4, D1）
   - 增量更新，避免重复下载
   - 数据完整性验证

2. **实时数据更新**
   - 实时获取最新行情数据
   - 多线程并行处理多个交易品种
   - 支持计算K线完成度
   - 定期自动更新数据文件

### 支持的交易品种

系统默认支持以下交易品种：
- XAUUSD (黄金)
- XAGUSD (白银)
- EURUSD (欧元美元)
- GBPUSD (英镑美元)
- USDJPY (美元日元)
- USDCHF (美元瑞郎)
- AUDUSD (澳元美元)
- NZDUSD (纽元美元)
- USDCAD (美元加元)

### 支持的时间周期

- M1 (1分钟)
- M5 (5分钟)
- M15 (15分钟)
- M30 (30分钟)
- H1 (1小时)
- H4 (4小时)
- D1 (1天)

## 系统架构

### 目录结构

```
策略空间/
├── data/                  # 数据根目录
│   ├── historical/        # 历史数据目录
│   │   ├── XAUUSD/        # 按品种分类
│   │   │   ├── XAUUSD_m1.csv
│   │   │   ├── XAUUSD_m5.csv
│   │   │   └── ...
│   │   └── ...
│   ├── realtime/          # 实时数据目录
│   │   ├── XAUUSD/
│   │   │   ├── XAUUSD_m1_realtime.csv
│   │   │   ├── XAUUSD_m5_realtime.csv
│   │   │   └── ...
│   │   └── ...
│   └── logs/              # 日志目录
│       ├── history_updater.log
│       └── realtime_updater.log
├── src/                   # 源代码目录
│   ├── python/            # Python模块
│   │   ├── data/          # 数据处理相关
│   │   │   ├── updaters/  # 数据更新器
│   │   │   │   ├── updater.py         # 主启动脚本
│   │   │   │   ├── history_updater.py # 历史数据更新模块
│   │   │   │   └── realtime_updater.py # 实时数据更新模块
│   │
│   ├── mql5/              # MT5相关文件
│   │   ├── expert_advisors/  # EA文件目录
│   │   │   └── MT5DataUpdater_Simple.mq5 # 数据更新EA
│   │   └── scripts/       # 脚本文件目录
│
├── scripts/               # 批处理和辅助脚本
│   ├── install/           # 安装脚本
│   │   ├── install_mt5_ea.bat          # MT5 EA安装脚本
│   │   └── setup_environment.bat       # 环境设置脚本
│   ├── startup/           # 启动脚本
│   │   ├── start_data_service.bat      # 数据服务启动脚本
│   │   └── autostart_data_service.bat  # 服务自动启动脚本
│
└── requirements.txt       # 依赖包列表
```

### 模块说明

- **updater.py**: 主启动脚本，可以选择启动历史数据更新、实时数据更新或同时启动两者
- **history_updater.py**: 历史数据更新模块，负责下载和更新历史K线数据
- **realtime_updater.py**: 实时数据更新模块，负责获取最新行情数据

## 数据文件格式

### 历史数据文件

历史数据以CSV格式存储，文件命名格式为：`SYMBOL_timeframe.csv`，例如：`XAUUSD_m1.csv`

文件包含以下列：
- time: 时间戳（ISO格式）
- open: 开盘价
- high: 最高价
- low: 最低价
- close: 收盘价
- tick_volume: 成交量（Tick数量）
- real_volume: 真实成交量（通常为0，取决于经纪商）
- spread: 点差

示例：
```
time,open,high,low,close,tick_volume,real_volume,spread
2023-01-01 00:00:00,1825.35,1825.40,1825.25,1825.32,125,0,2
2023-01-01 00:01:00,1825.32,1825.45,1825.30,1825.38,143,0,2
...
```

### 实时数据文件

实时数据同样以CSV格式存储，文件命名格式为：`SYMBOL_timeframe_realtime.csv`，例如：`XAUUSD_m1_realtime.csv`

除了与历史数据相同的列外，实时数据文件还包含额外的列：
- is_complete: K线是否已完成（true/false）
- period_progress: K线完成度（0.00-100.00，表示当前K线已经完成的百分比）

示例：
```
time,open,high,low,close,tick_volume,real_volume,spread,is_complete,period_progress
2023-06-15 10:30:00,1950.25,1950.35,1950.20,1950.28,87,0,3,true,100.00
2023-06-15 10:31:00,1950.28,1950.40,1950.28,1950.38,95,0,3,true,100.00
...
2023-06-15 10:45:00,1951.10,1951.15,1951.05,1951.08,42,0,3,false,60.00
```

## 使用指南

### 环境设置

1. 确保已安装MetaTrader 5软件并登录账户
2. 安装所需Python依赖：
   ```
   pip install -r requirements.txt
   ```

### 系统启动

#### 方法1：使用Python脚本

通过主脚本启动系统，可以选择不同的模式：

1. 启动全部模块（历史数据和实时数据更新）：
   ```
   python src/python/data/updaters/updater.py
   ```

2. 仅启动历史数据更新：
   ```
   python src/python/data/updaters/updater.py --mode history
   ```

3. 仅启动实时数据更新：
   ```
   python src/python/data/updaters/updater.py --mode realtime
   ```

4. 指定特定交易品种和时间周期：
   ```
   python src/python/data/updaters/updater.py --symbols XAUUSD,EURUSD --timeframes M1,H1
   ```

#### 方法2：使用MT5 EA

1. 安装EA：
   - 运行 `scripts/install/install_mt5_ea.bat` 脚本
   - 脚本将自动：
     * 检测MT5安装路径
     * 复制EA文件到MT5的Experts目录
     * 创建必要的数据目录
     * 编译EA (如果找到MetaEditor)
   - 确认安装完成后在MT5中找到 `MT5DataUpdater_Simple` EA

2. 配置EA参数：
   - 交易品种：设置要更新的交易品种，多个品种用逗号分隔(例如: "XAUUSD,EURUSD,GBPUSD")
   - 时间周期：设置要更新的时间周期，多个周期用逗号分隔(例如: "M1,M5,H1,D1")
   - 数据路径：保持默认 `../../data` 路径，除非您更改了数据存储目录
   - 更新频率：设置更新间隔（分钟），建议初期设置为1-5分钟
   - 历史K线数量：设置历史数据获取的K线数量，默认1000根

3. 启用自动交易：
   - 在MT5中按 Ctrl+T 或点击 "工具" > "选项" > "专家顾问" 
   - 确保已选中 "允许自动交易" 和 "允许来自外部的DLL导入"
   - 点击右上角的"自动交易"按钮，确保其变为绿色

4. 查看EA运行状态：
   - EA运行时会在图表右上角显示状态信息
   - 查看"专家"选项卡可以看到详细日志
   - 数据文件将保存在项目的data目录下

### 自动启动服务

使用 `scripts/startup/autostart_data_service.bat` 脚本可以自动启动Python服务：

1. 双击运行脚本
2. 脚本会自动检查Python环境和MT5状态
3. 启动历史数据和实时数据更新服务
4. 每60秒监控服务状态，如果服务意外停止会自动重启
5. 服务运行状态可在命令窗口中实时查看

## 数据应用

### 数据加载示例

在Python中加载数据示例：

```python
import pandas as pd

# 加载历史数据
def load_historical_data(symbol, timeframe):
    filepath = f"data/historical/{symbol}/{symbol}_{timeframe.lower()}.csv"
    df = pd.read_csv(filepath)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    return df

# 加载实时数据
def load_realtime_data(symbol, timeframe):
    filepath = f"data/realtime/{symbol}/{symbol}_{timeframe.lower()}_realtime.csv"
    df = pd.read_csv(filepath)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    return df

# 合并历史和实时数据
def load_combined_data(symbol, timeframe):
    # 加载数据
    hist_data = load_historical_data(symbol, timeframe)
    real_data = load_realtime_data(symbol, timeframe)
    
    # 合并数据
    combined = pd.concat([hist_data, real_data])
    # 移除重复数据
    combined = combined.loc[~combined.index.duplicated(keep='last')]
    # 按时间排序
    combined = combined.sort_index()
    
    return combined

# 数据预处理示例
def preprocess_data(df):
    # 计算技术指标
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 计算K线实体和影线
    df['body_size'] = abs(df['close'] - df['open'])
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
    
    # 去除NaN值
    df.dropna(inplace=True)
    
    return df

# 使用示例
symbol = 'XAUUSD'
timeframe = 'm1'

# 加载并处理数据
data = load_combined_data(symbol, timeframe)
processed_data = preprocess_data(data)

# 查看最新数据
latest_data = processed_data.tail(10)
print(latest_data)
```

### 实时交易示例

实时交易循环示例：

```python
import time
import pandas as pd
import datetime

def trading_loop(symbol, timeframe):
    # 获取timeframe对应的更新间隔（秒）
    def get_update_interval(tf):
        tf_dict = {'M1': 5, 'M5': 15, 'M15': 30, 'M30': 60, 
                  'H1': 120, 'H4': 300, 'D1': 600}
        return tf_dict.get(tf.upper(), 60)
    
    # 初始化交易环境
    initialize_trading_environment()
    
    while True:
        try:
            # 加载最新的实时数据
            df = load_realtime_data(symbol, timeframe)
            
            # 获取最后一根K线
            last_bar = df.iloc[-1]
            
            # 检查K线是否完成
            if last_bar['is_complete'] == True:
                # 应用策略逻辑
                signal = apply_strategy(df)
                
                if signal == 'BUY':
                    # 执行买入操作
                    place_order(symbol, 'BUY')
                    print(f"[{datetime.datetime.now()}] 执行买入信号")
                    
                elif signal == 'SELL':
                    # 执行卖出操作
                    place_order(symbol, 'SELL')
                    print(f"[{datetime.datetime.now()}] 执行卖出信号")
                    
                # 更新持仓管理
                manage_positions()
            else:
                # K线未完成时的处理
                # 可以进行部分分析或者提前准备
                prepare_for_next_bar(df, last_bar['period_progress'])
            
            # 计算等待时间：根据K线完成度动态调整
            if 'period_progress' in last_bar and last_bar['period_progress'] > 80:
                # 如果K线接近完成，更频繁检查
                sleep_time = 1
            else:
                # 否则使用标准间隔
                sleep_time = get_update_interval(timeframe)
                
            # 打印状态信息
            print(f"[{datetime.datetime.now()}] 最新K线: {last_bar.name}, 完成度: {last_bar.get('period_progress', 0)}%, 下次更新: {sleep_time}秒后")
                
            # 等待下次更新
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"[{datetime.datetime.now()}] 错误: {str(e)}")
            time.sleep(10)  # 出错时等待10秒再重试
            
# 策略函数示例
def apply_strategy(df):
    # 这里实现你的交易策略
    # 例如：移动平均线交叉策略
    df['sma_fast'] = df['close'].rolling(window=10).mean()
    df['sma_slow'] = df['close'].rolling(window=30).mean()
    
    # 生成信号
    if df['sma_fast'].iloc[-2] < df['sma_slow'].iloc[-2] and df['sma_fast'].iloc[-1] > df['sma_slow'].iloc[-1]:
        return 'BUY'
    elif df['sma_fast'].iloc[-2] > df['sma_slow'].iloc[-2] and df['sma_fast'].iloc[-1] < df['sma_slow'].iloc[-1]:
        return 'SELL'
    
    return 'HOLD'
```

## 常见问题解答

### MT5连接问题

**问题**: 无法连接到MT5平台
**解决方案**: 
1. 确保MT5软件已经启动并登录
2. 检查是否有其他程序已经连接到MT5（MT5一次只允许一个程序连接）
3. 在MT5中确认"允许自动交易"和"允许DLL导入"已启用
4. 尝试重启MT5软件和数据更新服务
5. 检查MT5是否被防火墙阻止

### 数据文件找不到

**问题**: 找不到数据文件
**解决方案**:
1. 检查系统是否已经启动并运行一段时间
2. 确认指定的交易品种和时间周期是否正确
3. 查看日志文件中是否有错误信息
4. 检查文件权限问题，确保程序有写入权限
5. 手动触发数据更新

### EA无法正常工作

**问题**: MT5 EA安装成功但不工作
**解决方案**:
1. 检查MT5的"自动交易"按钮是否已启用(右上角绿色)
2. 查看"专家"选项卡中是否有错误信息
3. 确认EA参数设置正确
4. 尝试重新编译EA
5. 检查EA是否附加到图表上

## 维护与日志

### 日志查看

系统运行日志保存在`data/logs/`目录下：
- `history_updater.log`: 历史数据更新日志
- `realtime_updater.log`: 实时数据更新日志

定期检查日志可以帮助识别潜在问题。

## 联系方式

如有问题或建议，请联系：
- 邮箱：[your-email@example.com]
- GitHub: [https://github.com/yourusername/mt5-data-updater] 