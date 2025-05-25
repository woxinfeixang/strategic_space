# MT5数据管理器使用手册

## 简介

MT5数据管理器是一个功能强大的工具，用于自动化MetaTrader 5(MT5)交易平台的数据获取和管理。该工具整合了历史数据下载和实时数据更新的功能，支持多种交易品种和时间周期，是构建稳定可靠的交易系统的基础组件。

## 主要功能

1. **多品种数据管理**：支持同时管理多个交易品种(如EURUSD, USDJPY等)的数据
2. **多时间周期支持**：支持从M1(1分钟)到MN1(月线)的所有标准MT5时间周期
3. **定时自动更新**：可设置定时任务，按指定间隔自动更新数据
4. **实时数据更新**：通过与MT5的集成，支持实时数据更新
5. **历史数据管理**：自动合并和维护历史数据文件
6. **灵活配置**：支持通过配置文件自定义行为

## 安装依赖

使用MT5数据管理器需要安装以下Python库：

```bash
pip install MetaTrader5 pandas schedule
```

同时需要安装MetaTrader 5交易平台，并确保已经设置好账户。

## 使用方法

### 基本使用

```python
from mt5_data_updater.MT5DataManager import get_instance

# 使用默认配置获取MT5数据管理器实例
manager = get_instance()

# 连接MT5
if manager.connect():
    # 执行一次全量更新
    manager.update_all_data(force_update=True)
    
    # 断开连接
    manager.disconnect()
```

### 运行数据管理服务

```python
from mt5_data_updater.MT5DataManager import get_instance

# 获取数据管理器实例
manager = get_instance()

# 启动数据管理服务(包括定时更新和实时更新)
if manager.run():
    try:
        # 保持程序运行
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # 程序中断时清理资源
        manager.cleanup()
```

### 命令行使用

MT5数据管理器也可以通过命令行直接使用：

```bash
# 执行一次全量更新
python -m mt5_data_updater.MT5DataManager --update

# 启动数据管理服务
python -m mt5_data_updater.MT5DataManager --run

# 使用自定义配置文件
python -m mt5_data_updater.MT5DataManager --config path/to/config.json --run

# 测试模式
python -m mt5_data_updater.MT5DataManager --test
```

## 配置选项

MT5数据管理器支持通过配置文件(JSON或INI格式)自定义行为，主要配置选项包括：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| symbols | 交易品种，逗号分隔 | EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD |
| timeframes | 时间周期，逗号分隔 | M1,M5,M15,M30,H1,H4,D1,W1 |
| data_path | 数据存储路径 | ./data |
| update_frequency_minutes | 定时更新间隔(分钟) | 5 |
| mt5_path | MT5安装路径 | C:/Program Files/MetaTrader 5/terminal64.exe |
| realtime_update | 是否启用实时更新 | true |
| scheduled_update | 是否启用定时更新 | true |

配置文件示例(config.json)：

```json
{
    "symbols": "EURUSD,USDJPY,GBPUSD",
    "timeframes": "M5,M15,H1,D1",
    "data_path": "E:/Trading/data",
    "update_frequency_minutes": "10",
    "mt5_path": "D:/Program Files/MetaTrader 5/terminal64.exe",
    "realtime_update": true,
    "scheduled_update": true
}
```

## 数据文件结构

MT5数据管理器将数据保存为CSV格式，文件结构如下：

```
data/
├── EURUSD/
│   ├── M1.csv           # 历史数据文件
│   ├── M1_realtime.csv  # 实时数据文件(最新100根K线)
│   ├── M5.csv
│   ├── M5_realtime.csv
│   └── ...
├── USDJPY/
│   ├── M1.csv
│   ├── M1_realtime.csv
│   └── ...
└── ...
```

CSV文件包含以下列：
- time: 时间戳
- open: 开盘价
- high: 最高价
- low: 最低价
- close: 收盘价
- tick_volume: 交易量
- spread: 点差
- real_volume: 真实交易量
- is_complete: 是否为完整K线

## 实时数据更新与MT5集成

要实现实时数据更新，需要在MT5的Expert Advisor(EA)中调用MT5数据管理器的process_tick方法。以下是一个简单的EA示例：

```cpp
//+------------------------------------------------------------------+
//|                                           RealTimeDataUpdater.mq5 |
//+------------------------------------------------------------------+
#property copyright "Copyright 2023"
#property link      "https://www.example.com"
#property version   "1.00"

#include <Python.h>

//--- 输入参数
input string PythonPath = "python";
input string DataManagerModule = "mt5_data_updater.MT5DataManager";

//--- 全局变量
PyObject *pModule = NULL;
PyObject *pManager = NULL;
PyObject *pProcessTickFunc = NULL;
bool pythonInitialized = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // 初始化Python解释器
    Py_Initialize();
    if (!Py_IsInitialized())
    {
        Print("Python初始化失败");
        return INIT_FAILED;
    }
    
    pythonInitialized = true;
    
    // 导入MT5DataManager模块
    PyObject *pName = PyUnicode_DecodeFSDefault(DataManagerModule);
    pModule = PyImport_Import(pName);
    Py_DECREF(pName);
    
    if (pModule == NULL)
    {
        Print("无法导入模块: ", DataManagerModule);
        return INIT_FAILED;
    }
    
    // 获取MT5DataManager实例
    PyObject *pGetInstanceFunc = PyObject_GetAttrString(pModule, "get_instance");
    if (pGetInstanceFunc && PyCallable_Check(pGetInstanceFunc))
    {
        pManager = PyObject_CallObject(pGetInstanceFunc, NULL);
        Py_DECREF(pGetInstanceFunc);
    }
    else
    {
        Print("无法获取get_instance函数");
        return INIT_FAILED;
    }
    
    // 获取process_tick方法
    if (pManager != NULL)
    {
        pProcessTickFunc = PyObject_GetAttrString(pManager, "process_tick");
        if (!pProcessTickFunc || !PyCallable_Check(pProcessTickFunc))
        {
            Print("无法获取process_tick方法");
            return INIT_FAILED;
        }
    }
    else
    {
        Print("无法获取MT5DataManager实例");
        return INIT_FAILED;
    }
    
    Print("MT5实时数据更新器初始化成功");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    // 清理Python对象
    if (pProcessTickFunc != NULL)
    {
        Py_DECREF(pProcessTickFunc);
    }
    
    if (pManager != NULL)
    {
        // 调用cleanup方法
        PyObject *pCleanupFunc = PyObject_GetAttrString(pManager, "cleanup");
        if (pCleanupFunc && PyCallable_Check(pCleanupFunc))
        {
            PyObject_CallObject(pCleanupFunc, NULL);
            Py_DECREF(pCleanupFunc);
        }
        
        Py_DECREF(pManager);
    }
    
    if (pModule != NULL)
    {
        Py_DECREF(pModule);
    }
    
    // 结束Python解释器
    if (pythonInitialized)
    {
        Py_Finalize();
    }
    
    Print("MT5实时数据更新器已关闭");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    if (pProcessTickFunc == NULL || pManager == NULL)
    {
        return;
    }
    
    // 获取当前品种
    string symbol = Symbol();
    
    // 创建参数
    PyObject *pArgs = PyTuple_New(1);
    PyObject *pSymbol = PyUnicode_DecodeFSDefault(symbol);
    PyTuple_SetItem(pArgs, 0, pSymbol);
    
    // 调用process_tick方法
    PyObject *pResult = PyObject_CallObject(pProcessTickFunc, pArgs);
    Py_DECREF(pArgs);
    
    if (pResult != NULL)
    {
        Py_DECREF(pResult);
    }
}
```

将此EA添加到MT5中，它将在每个价格变动时调用MT5数据管理器的process_tick方法，从而实现实时数据更新。

## 常见问题

1. **无法连接到MT5**
   - 确保MT5已经打开并登录
   - 检查MT5路径配置是否正确
   - 确认账户具有交易权限

2. **数据更新失败**
   - 检查网络连接是否稳定
   - 确认交易品种是否添加到市场观察列表
   - 查看日志文件了解详细错误信息

3. **数据文件格式问题**
   - 如果手动修改了数据文件，请确保保持正确的CSV格式
   - 时间列必须使用标准日期时间格式

4. **性能优化**
   - 减少监控品种或时间周期数量
   - 增加更新频率间隔
   - 针对高频时间周期(如M1)和低频时间周期(如D1)设置不同的更新频率

## 日志记录

MT5数据管理器会将运行日志保存到`mt5_data_manager.log`文件中，包含连接状态、更新操作和错误信息。可以通过查看此日志文件排查问题。

## 高级应用

### 自定义数据处理

可以继承MT5DataManager类，重写特定方法来实现自定义数据处理逻辑：

```python
from mt5_data_updater.MT5DataManager import MT5DataManager

class CustomDataManager(MT5DataManager):
    def update_data(self, symbol, tf_name, timeframe, force_update=False):
        # 在更新数据前执行自定义处理
        print(f"准备更新数据: {symbol} {tf_name}")
        
        # 调用父类方法
        result = super().update_data(symbol, tf_name, timeframe, force_update)
        
        # 在更新数据后执行自定义处理
        if result:
            print(f"数据更新成功: {symbol} {tf_name}")
            # 执行额外的数据处理...
        
        return result
```

### 集成到大型交易系统

MT5数据管理器可以作为大型交易系统的一个组件，为策略回测和实时交易提供数据服务：

```python
from mt5_data_updater.MT5DataManager import get_instance
import pandas as pd

class TradingSystem:
    def __init__(self):
        # 获取MT5数据管理器实例
        self.data_manager = get_instance()
        self.data_manager.connect()
        
        # 确保数据是最新的
        self.data_manager.update_all_data()
    
    def load_historical_data(self, symbol, timeframe, start_date, end_date):
        # 从数据文件加载历史数据
        history_file = f"{self.data_manager.data_path}/{symbol}/{timeframe}.csv"
        
        df = pd.read_csv(history_file)
        df['time'] = pd.to_datetime(df['time'])
        
        # 筛选日期范围
        mask = (df['time'] >= start_date) & (df['time'] <= end_date)
        return df.loc[mask]
    
    def get_realtime_data(self, symbol, timeframe):
        # 获取实时数据
        realtime_file = f"{self.data_manager.data_path}/{symbol}/{timeframe}_realtime.csv"
        return pd.read_csv(realtime_file)
    
    def run_strategy(self, symbol, timeframe, params):
        # 获取数据
        data = self.get_realtime_data(symbol, timeframe)
        
        # 运行策略逻辑
        # ...
        
        # 返回交易信号
        return signals
    
    def cleanup(self):
        self.data_manager.cleanup()
```

## 更新与维护

MT5数据管理器会定期维护和更新。请关注项目仓库获取最新版本和更新信息。

## 技术支持

如有问题或需要技术支持，请通过以下方式联系：

- 提交GitHub Issue
- 发送邮件至support@example.com

## 许可证

MT5数据管理器使用MIT许可证开源。 