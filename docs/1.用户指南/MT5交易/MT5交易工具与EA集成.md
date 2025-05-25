# MT5交易工具与EA集成

本文档详细说明了项目中用于MT5交易的各种工具和EA，包括交易启用、状态检查、EA安装和使用指南。

## 目录

- [交易功能工具](#交易功能工具)
  - [交易功能启用](#交易功能启用)
  - [交易状态检查](#交易状态检查)
  - [MT5信息获取](#mt5信息获取)
- [EA及MQL5组件](#ea及mql5组件)
  - [蜡烛图形态交易EA](#蜡烛图形态交易ea)
  - [经济事件交易EA](#经济事件交易ea)
  - [经济数据处理器](#经济数据处理器)
- [安装与配置](#安装与配置)
  - [EA安装过程](#ea安装过程)
  - [交易参数配置](#交易参数配置)
- [交易策略说明](#交易策略说明)
- [风险管理](#风险管理)

## 交易功能工具

项目包含一系列Python工具，用于管理MT5的交易功能、检查交易状态及获取MT5平台信息。

### 交易功能启用

**文件名**: `enable_mt5_trading.py`

**功能特点**:
- 启用MT5平台的自动交易功能
- 配置交易账户参数和权限
- 设置默认交易规则和限制
- 支持不同交易模式(实盘/模拟)的切换

**使用方法**:
```bash
# 基本用法 - 使用配置文件中的设置
python enable_mt5_trading.py

# 指定账户模式
python enable_mt5_trading.py --mode demo  # 模拟账户
python enable_mt5_trading.py --mode real  # 实盘账户

# 启用详细日志
python enable_mt5_trading.py --verbose
```

**参数说明**:
- `--mode`: 指定账户模式，可选值为`demo`或`real`，默认为`demo`
- `--verbose`: 启用详细日志输出，显示更多调试信息
- `--config`: 指定自定义配置文件路径

### 交易状态检查

**文件名**: `check_trading.py`

**功能特点**:
- 检查MT5交易功能是否正常启用
- 验证交易账户状态和权限
- 检查交易策略和订单执行情况
- 提供交易功能的诊断报告

**使用方法**:
```bash
# 基本用法
python check_trading.py

# 详细模式
python check_trading.py --verbose

# 导出报告
python check_trading.py --export-report
```

**输出示例**:
```
MT5交易状态检查报告:
- 连接状态: 已连接
- 交易允许: 是
- 账户类型: 模拟账户
- 账户余额: 10000.00 USD
- 活跃订单数: 2
- 挂单数: 1
- 交易功能测试: 通过
```

### MT5信息获取

**文件名**: `mt5_info.py`

**功能特点**:
- 获取MT5平台的详细信息
- 显示账户信息和交易统计
- 查看服务器状态和连接情况
- 获取可交易品种和交易规则

**使用方法**:
```bash
# 基本用法
python mt5_info.py

# 获取特定品种信息
python mt5_info.py --symbol EURUSD

# 获取账户详情
python mt5_info.py --account-info

# 查看最近交易历史
python mt5_info.py --history
```

**输出示例**:
```
MT5终端信息:
- 版本: 5.00 build 1950
- 路径: C:\Program Files\MetaTrader 5
- 连接状态: 已连接到 BrokerServerName

账户信息:
- 账号: 12345678
- 姓名: Demo User
- 杠杆: 1:100
- 余额: 10000.00 USD
- 净值: 10125.50 USD
- 可用保证金: 9875.25 USD
- 保证金水平: 95.23%
```

## EA及MQL5组件

项目包含多个MT5专家顾问(EA)和MQL5组件，用于实现不同的交易策略和功能。

### 蜡烛图形态交易EA

**文件名**: `mt5/CandlePatternTrader.mq5`

**功能特点**:
- 自动识别多种蜡烛图形态
- 支持18种经典蜡烛图形态，包括锤头、吞没、星线等
- 根据形态发出交易信号并自动执行
- 集成风险管理和资金管理规则
- 支持多时间周期分析和交易确认

**形态种类**:
- 锤子线(Hammer)和上吊线(Hanging Man)
- 吞没形态(Engulfing)
- 启明星和黄昏星(Morning/Evening Star)
- 十字星(Doji)
- 刺透形态和乌云盖顶(Piercing Line/Dark Cloud Cover)
- 三兵和三鸦(Three Soldiers/Crows)
- 孕线形态(Harami)

**使用说明**:
- 安装EA到MT5平台
- 配置参数，包括风险设置、形态选择和交易规则
- 附加到图表并启用自动交易

### 经济事件交易EA

**文件名**: `mt5/EconomicEventEA.mq5`

**功能特点**:
- 基于经济数据发布自动交易
- 整合经济日历数据，跟踪重要经济事件
- 在事件发布前后实施不同的交易策略
- 支持波动率预测和头寸管理
- 可配置多种事件反应模式

**支持的事件类型**:
- 利率决议
- 非农就业数据
- GDP数据
- 通胀数据(CPI/PPI)
- 零售销售数据
- PMI数据
- 央行声明

**使用说明**:
- 安装EA到MT5平台
- 配置经济事件筛选和重要性级别
- 设置事件反应参数和风险控制
- 附加到图表并启用自动交易

### 经济数据处理器

**文件名**: `mt5/economic_data_handler.mqh`

**功能特点**:
- MQL5头文件，提供经济数据解析和处理功能
- 为EA提供经济事件数据访问接口
- 支持从文件和网络导入经济日历数据
- 提供事件筛选、排序和优先级计算
- 集成数据缓存和更新机制

**关键功能**:
```cpp
// 加载经济事件数据
bool LoadEconomicEvents(string filename);

// 获取未来事件
int GetUpcomingEvents(datetime from_time, datetime to_time);

// 按重要性筛选事件
int FilterEventsByImportance(int importance_level);

// 按国家/货币筛选事件
int FilterEventsByCurrency(string currency);

// 获取特定事件详情
bool GetEventDetails(int index, EventInfo& event_info);
```

## 安装与配置

### EA安装过程

项目提供了自动化的EA安装脚本，简化了安装过程。

**安装脚本**: `mt5/install_ea.bat`

**安装步骤**:
1. 确保MT5平台已经安装并至少运行过一次
2. 运行安装脚本，它将自动:
   - 找到MT5终端的安装路径
   - 复制EA和相关文件到正确目录
   - 设置必要的权限
3. 重启MT5平台，EA将出现在导航器窗口

**手动安装方法**:
1. 打开MT5平台
2. 按下`Ctrl+N`打开导航器窗口
3. 右键点击"Expert Advisors"，选择"Open Data Folder"
4. 进入MQL5\Experts目录
5. 复制项目中的.mq5文件到此目录
6. 复制.mqh文件到MQL5\Include目录
7. 在MT5中按F4打开MetaEditor
8. 编译所有EA文件

### 交易参数配置

EA的参数可以通过以下两种方式配置:

1. **MT5界面配置**:
   - 将EA拖放到图表上
   - 在弹出的参数窗口中设置参数
   - 保存配置为预设(可选)

2. **配置文件配置**:
   - 在项目配置目录中创建EA配置文件
   - 使用安装脚本自动应用配置
   - 支持多个交易策略配置切换

**参数配置示例**:
```json
{
  "CandlePatternTrader": {
    "RiskPercent": 2.0,
    "MaxSpread": 10,
    "PatternTypes": [1, 2, 3, 5, 8],
    "MinConfirmation": 2,
    "UseStopLoss": true,
    "StopLossPoints": 100,
    "UseTakeProfit": true,
    "TakeProfitPoints": 300
  },
  "EconomicEventEA": {
    "EventImportance": 3,
    "PreEventMinutes": 30,
    "PostEventMinutes": 60,
    "TradeMode": 2,
    "RiskPercent": 1.0,
    "CloseBeforeEvent": true
  }
}
```

## 交易策略说明

项目实现的交易策略基于以下原则和方法:

### 蜡烛图形态策略

1. **形态识别原则**:
   - 根据蜡烛图的开盘价、收盘价、最高价和最低价识别形态
   - 考虑形态出现的市场环境和趋势上下文
   - 使用确认信号增强形态的可靠性

2. **交易规则**:
   - 在趋势与形态一致时进场
   - 利用形态特性设置止损和获利点
   - 根据形态强度和市场波动性调整仓位大小

3. **风险管理**:
   - 每笔交易风险控制在账户的1-2%
   - 形态失效时立即出场
   - 使用移动止损跟踪有利走势

### 经济事件策略

1. **事件前策略**:
   - 在重要经济数据发布前减少或关闭现有头寸
   - 根据预期波动性调整交易参数
   - 避免在高波动性事件前新建头寸

2. **事件后策略**:
   - 根据数据与预期的差异确定方向
   - 使用突破策略捕捉大幅走势
   - 等待市场稳定后再考虑新头寸

3. **事件筛选**:
   - 仅交易高影响力事件(3星级别)
   - 针对特定货币对选择相关事件
   - 考虑事件的历史波动性表现

## 风险管理

项目实现了全面的风险管理系统，包括:

1. **资金管理**:
   - 按账户百分比风险控制(0.5%-2%)
   - 根据波动性动态调整仓位大小
   - 设置最大日损失和最大月损失限制

2. **止损策略**:
   - 根据市场环境设置固定或动态止损
   - 使用移动止损保护盈利
   - 在关键技术位置设置止损点

3. **头寸管理**:
   - 控制单个品种的最大敞口
   - 限制总体市场敞口
   - 实施相关性管理避免重复风险

4. **风险参数配置**:
```json
{
  "RiskManagement": {
    "MaxRiskPerTrade": 2.0,
    "MaxDailyLoss": 5.0,
    "MaxWeeklyLoss": 10.0,
    "MaxOpenPositions": 5,
    "CorrelationLimit": 0.7,
    "UseEquityProtection": true,
    "EquityProtectionLevel": 90.0
  }
}
``` 