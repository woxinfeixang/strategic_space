# MT5量化交易系统使用手册

## 系统简介

战略空间MT5量化交易系统是一套完整的量化交易解决方案，基于MetaTrader 5交易平台和Python分析技术。系统通过多层架构设计，实现了从数据采集、分析处理到策略执行的全流程自动化，使交易者能够便捷地开发、测试和部署量化交易策略。

## 系统核心功能

### 1. 数据管理功能

- **多源数据获取**：支持MT5行情、财经日历、外部API等多种数据源
- **历史数据管理**：自动化收集、存储和更新历史数据
- **数据处理工具**：提供清洗、标准化和特征提取等功能
- **高效数据存储**：优化的SQLite数据库模式，支持快速查询

### 2. 策略开发功能

- **策略框架**：提供EA开发框架，简化策略开发流程
- **指标库**：内置多种技术分析指标和自定义指标
- **事件驱动**：支持基于财经日历的事件驱动交易
- **Python集成**：允许使用Python进行复杂策略开发

### 3. 回测与优化功能

- **高精度回测**：支持基于真实滑点和点差的精确回测
- **参数优化**：多维参数空间优化，寻找最优策略参数
- **性能评估**：全面的策略性能统计和风险评估
- **可视化分析**：交易结果的图形化展示和分析

### 4. 实盘交易功能

- **自动交易**：支持策略自动执行交易指令
- **风险控制**：内置止损、止盈和资金管理机制
- **多账户管理**：支持多账户并行交易和管理
- **交易监控**：实时监控交易执行和账户状态

## 系统架构概览

系统采用分层架构设计，主要分为以下几层：

1. **交互层**：负责与MT5平台交互，处理数据获取和交易执行
2. **数据层**：管理数据存储和访问，提供统一数据接口
3. **分析层**：实现各类分析算法和指标计算
4. **策略层**：管理交易策略的开发和执行
5. **服务层**：提供API和用户界面服务

## 系统使用指南

### 环境设置

1. **基础要求**：
   - Windows 10/11 操作系统
   - MetaTrader 5 平台（最新版）
   - Python 3.8 或更高版本

2. **安装步骤**：
   ```bash
   # 1. 克隆或下载项目
   # 2. 安装依赖包
   pip install -r requirements.txt
   # 3. 运行环境设置脚本
   scripts\install\setup_environment.bat
   ```

### 数据管理操作

1. **更新历史数据**：
   ```bash
   python src\python\cli\update_history.py --symbols EURUSD,GBPUSD --timeframe H1
   ```

2. **更新财经日历**：
   ```bash
   python src\python\cli\update_calendar.py --days 30
   ```

3. **检查数据完整性**：
   ```bash
   python src\python\cli\verify_data.py --symbols EURUSD --start 2022-01-01 --end 2022-12-31
   ```

### 策略开发流程

1. **创建新策略**：
   - 复制 `src\ea\strategies\template.py` 为新文件
   - 实现策略逻辑和信号生成函数
   - 设置策略参数和风险管理规则

2. **策略测试**：
   ```bash
   python src\python\cli\backtest.py --strategy YourStrategy --config config\backtest_config.json
   ```

3. **策略优化**：
   ```bash
   python src\python\cli\optimize.py --strategy YourStrategy --params "param1=1:10:1,param2=0.1:0.5:0.1"
   ```

### 实盘部署步骤

1. **准备策略EA**：
   ```bash
   python src\python\cli\build_ea.py --strategy YourStrategy --output YourStrategy.mq5
   ```

2. **安装至MT5**：
   ```bash
   scripts\install\install_ea.bat YourStrategy
   ```

3. **启动交易监控**：
   ```bash
   python src\python\cli\monitor.py --strategy YourStrategy --alert email
   ```

## 常见问题解答

### Q: 如何解决数据不同步问题？
A: 运行 `python src\python\cli\sync_data.py` 进行数据同步检查和修复。

### Q: 策略回测与实盘结果不一致？
A: 检查回测配置中的滑点和点差设置，确保与实盘环境一致。

### Q: 如何为策略添加自定义指标？
A: 在 `src\models\indicators.py` 中添加指标实现，然后在策略中导入使用。

### Q: 系统支持哪些风险管理方法？
A: 支持固定手数、比例风险、动态调整等多种资金管理方式，可在策略配置中设置。

## 高级功能

### 事件驱动交易

系统支持基于财经日历的事件驱动交易，可通过以下步骤设置：

1. 配置事件过滤器：
   ```python
   event_filter = {"importance": [3], "countries": ["US"], "currencies": ["USD"]}
   ```

2. 注册事件处理器：
   ```python
   self.register_event_handler("Non-Farm Payrolls", self.handle_nfp_event)
   ```

3. 实现事件响应逻辑：
   ```python
   def handle_nfp_event(self, event):
       # 实现事件响应逻辑
       pass
   ```

### 机器学习集成

系统支持集成机器学习模型进行交易决策：

1. 准备训练数据：
   ```python
   from src.python.data.processors.ml_processor import prepare_training_data
   X, y = prepare_training_data("EURUSD", "D1", features=["rsi", "macd", "bollinger"])
   ```

2. 训练和保存模型：
   ```python
   from src.python.models.ml_models import train_classifier
   model = train_classifier(X, y, model_type="random_forest")
   model.save("models/eurusd_daily_model.pkl")
   ```

3. 在策略中使用模型：
   ```python
   from src.python.models.ml_models import load_model
   self.model = load_model("models/eurusd_daily_model.pkl")
   prediction = self.model.predict(current_features)
   ```

## 附录

### 系统目录结构
主要目录和功能说明，请参见项目根目录下的结构图。

### 常用命令参考
详细的命令行参数和选项说明，请参见 `docs/命令行工具参考.md`。

### 性能优化技巧
提高系统运行效率和回测速度的方法，请参见 `docs/性能优化指南.md`。 