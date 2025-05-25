# MT5数据更新EA使用指南

## 概述

MT5数据更新EA是一个MetaTrader 5专家顾问程序，用于自动收集和更新金融市场数据。该EA通过与本地Python服务通信，实现数据的定时获取和存储，无需手动操作即可保持数据的实时更新。

简化版EA（MT5DataUpdater_Simple）具有以下特点：
- 基于文件通信，无需复杂的网络配置
- 支持多品种、多时间周期数据收集
- 可配置的更新频率和交易时段
- 支持Tick级别的实时数据更新

## 安装步骤

### 前置条件

1. 已安装MetaTrader 5平台
2. 已安装Python 3.6+（推荐3.8或更高版本）
3. 基本的Windows操作知识

### 安装过程

1. **运行安装脚本**
   - 打开`mt5`文件夹
   - 双击运行`install_mt5_data_updater_simple.bat`
   - 安装脚本会自动完成以下操作：
     - 复制EA文件到MT5目录
     - 复制必要的Python服务文件
     - 尝试编译EA文件

2. **手动安装Python依赖**
   - 打开命令提示符或PowerShell
   - 运行以下命令安装必要的依赖：
     ```
     pip install pandas
     ```

3. **在MT5中添加EA**
   - 启动MetaTrader 5平台
   - 打开任意货币对图表（建议使用常见的交易品种，如EURUSD）
   - 在"导航器"窗口中找到"专家顾问"→"MT5DataUpdater_Simple"
   - 将EA拖拽到图表上，或双击EA名称

4. **配置EA参数**
   - 在EA添加对话框中，设置以下参数：
     - `Symbols`: 要收集的交易品种，以逗号分隔（例如：`EURUSD,USDJPY,GBPUSD`）
     - `Timeframes`: 要收集的时间周期，以逗号分隔（例如：`M1,M5,M15,H1,H4,D1`）
     - `DataPath`: 数据保存路径（默认：`./data/historical`）
     - `UpdateFrequencyMinutes`: 更新频率（分钟）
     - `EnableTickUpdate`: 是否启用Tick实时更新
     - `EnableLogging`: 是否启用详细日志
     - `TradingHourStart`/`TradingHourEnd`: 交易时段（可选）
     - `OnlyUpdateDuringTradingHours`: 是否仅在交易时段更新

5. **启动服务**
   - 运行`mt5/autostart_data_service.bat`启动后台服务
   - 该脚本会启动两个服务窗口：
     - MT5文件监视服务：负责监听EA发送的命令
     - MT5数据管理服务：负责处理数据下载和存储
   - 请确保这两个窗口都保持运行状态

## 使用方法

### 基本操作

1. **确认服务正常运行**
   - EA添加到图表后，查看"专家"选项卡中的日志
   - 应该能看到"MT5数据更新器初始化成功"的信息
   - `autostart_data_service.bat`窗口中会定期显示服务状态检查信息

2. **允许EA进行自动更新**
   - 点击MT5工具栏上的"自动交易"按钮，确保其处于启用状态
   - 在EA属性中允许"允许实时交易"

3. **查看数据更新状态**
   - EA日志会显示数据更新的状态和进度
   - 成功更新后，可以在指定的`DataPath`路径下找到下载的数据文件

### 常见问题解决

1. **EA无法初始化**
   - 检查MT5是否已启用"允许程序交易"
   - 确认MT5对文件系统有读写权限
   - 查看MT5日志是否有错误信息

2. **服务未响应命令**
   - 确认两个服务窗口都在运行
   - 检查命令文件路径是否正确
   - 重启后台服务脚本

3. **数据未更新**
   - 检查EA参数配置是否正确
   - 确认交易品种名称拼写正确
   - 验证时间周期格式是否符合要求
   - 查看日志中是否有错误信息

## 高级配置

### 自定义数据路径

可以修改`DataPath`参数来指定数据保存位置。该路径可以是相对于MT5终端目录的相对路径，也可以是绝对路径。例如：

- 相对路径：`./data/historical`（保存在MT5终端目录下的data/historical文件夹）
- 绝对路径：`D:/MarketData/MT5`（保存在指定的绝对路径）

### 交易时段设置

通过设置`TradingHourStart`和`TradingHourEnd`参数，可以指定EA只在特定时间段内更新数据：

- 设置为`0`和`24`表示全天更新
- 设置为`8`和`17`表示只在上午8点到下午5点更新
- 启用`OnlyUpdateDuringTradingHours`选项使时间段设置生效

### 批量更新多个品种

要批量更新大量交易品种，只需在`Symbols`参数中列出所有需要的品种，以逗号分隔，例如：
```
EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD,USDCHF,NZDUSD,EURJPY,EURGBP
```

### 优化性能

- 减少同时更新的品种数量可以提高更新速度
- 增加`UpdateFrequencyMinutes`值可以减少系统资源占用
- 如只需特定时间周期数据，可以在`Timeframes`中只列出需要的时间周期

## 技术说明

- EA通过文件系统与Python服务通信，命令文件位于MT5终端目录的`MQL5/Files/mt5_updater_command.txt`
- Python服务接收命令并处理数据下载、转换和存储
- 数据以CSV格式保存，可在其他分析工具中使用
- 服务每60秒自动检查状态，如果发现服务停止会尝试重启

## 故障排除

如遇问题，请检查以下文件中的错误信息：
- EA日志：MT5平台中的"专家"选项卡
- 服务错误日志：`error_watcher.log`和`error_manager.log`（位于启动服务的目录）

如需手动重启服务，请关闭所有服务窗口并重新运行`autostart_data_service.bat`。 