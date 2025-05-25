# 战略空间交易系统数据目录结构

本文档描述了战略空间(Strategic Space)交易系统的数据目录结构及各级目录的用途。

## 目录结构概览

```
data/
├── backups/               # 数据备份
├── cache/                 # 临时缓存数据  
├── calendar/              # 财经日历数据
│   ├── filtered/          # 筛选后的财经日历数据
│   │   ├── history/       # 筛选后的历史财经数据
│   │   └── live/          # 筛选后的实时财经数据
│   ├── processed/         # 处理后的财经日历数据
│   │   ├── history/       # 处理后的历史财经数据(CSV文件和数据库)
│   │   └── live/          # 处理后的实时财经数据(中间CSV文件)
│   └── raw/               # 原始财经日历数据
│       ├── history/       # 原始历史HTML文件
│       └── live/          # 原始实时HTML文件
├── historical/            # 历史市场数据
│   ├── AUDJPY/            # 澳元/日元历史数据
│   ├── AUDUSD/            # 澳元/美元历史数据
│   ├── DE40/              # 德国DAX40指数历史数据
│   ├── EURJPY/            # 欧元/日元历史数据
│   ├── EURUSD/            # 欧元/美元历史数据
│   ├── GBPJPY/            # 英镑/日元历史数据
│   ├── GBPUSD/            # 英镑/美元历史数据
│   ├── NZDUSD/            # 纽元/美元历史数据
│   ├── USDCAD/            # 美元/加元历史数据
│   ├── USDCHF/            # 美元/瑞郎历史数据
│   ├── USDJPY/            # 美元/日元历史数据
│   ├── USTEC/             # 美国科技100指数历史数据
│   ├── XAGUSD/            # 白银/美元历史数据
│   ├── XAUUSD/            # 黄金/美元历史数据
│   ├── XBRUSD/            # 布伦特原油/美元历史数据
│   └── XTIUSD/            # WTI原油/美元历史数据
├── logs/                  # 日志文件
└── realtime/              # 实时市场数据
    ├── AUDUSD/            # 澳元/美元实时数据
    ├── EURUSD/            # 欧元/美元实时数据
    ├── GBPUSD/            # 英镑/美元实时数据
    ├── NZDUSD/            # 纽元/美元实时数据
    ├── USDCAD/            # 美元/加元实时数据
    ├── USDCHF/            # 美元/瑞郎实时数据
    ├── USDJPY/            # 美元/日元实时数据
    ├── XAGUSD/            # 白银/美元实时数据
    └── XAUUSD/            # 黄金/美元实时数据
```

## 财经日历数据处理流程

### 历史数据处理流程（三阶段）
1. **原始数据**：HTML文件
   - 存储位置：`calendar/raw/history/`
   - 文件格式：`Investing.com (Economic_Calendar_YYYYMMDD - YYYYMMDD).html`

2. **处理阶段**：解析HTML并转换为结构化数据
   - 存储位置：`calendar/processed/history/`
   - 输出格式：按月CSV文件(`economic_calendar_YYYY_MM.csv`)和数据库(`economic_calendar.db`)

3. **筛选阶段**：按重要性等筛选处理后的数据
   - 存储位置：`calendar/filtered/history/`
   - 输出格式：筛选后的CSV文件和数据库

### 实时数据处理流程（三阶段）
1. **原始数据**：实时抓取的HTML文件
   - 存储位置：`calendar/raw/live/`
   - 文件名（可配置）：`realtime_calendar.html` （示例）

2. **处理阶段**：解析实时HTML并转换为结构化数据
   - 存储位置：`calendar/processed/live/`
   - 输出格式（可配置）：中间CSV文件 `processed_live.csv` （示例）

3. **筛选阶段**：筛选处理后的中间CSV数据
   - 存储位置：`calendar/filtered/live/`
   - 输出格式：筛选后的CSV文件 `filtered_live.csv`

## 目录用途详解

### calendar/ - 财经日历数据
此目录包含财经日历相关的所有数据。

- **raw/**: 存储原始财经日历数据
  - **history/**: 原始历史财经日历HTML文件
  - **live/**: 实时抓取的原始财经日历HTML文件

- **processed/**: 存储处理后的财经日历数据
  - **history/**: 从HTML解析处理后的历史数据，包括按月CSV文件和数据库
  - **live/**: 从实时HTML解析处理后的中间CSV数据

- **filtered/**: 存储筛选后的财经日历数据
  - **history/**: 从processed/history目录筛选出的历史数据
  - **live/**: 从processed/live目录筛选出的实时数据

### historical/ - 历史市场数据
此目录按交易品种组织历史行情数据。每个子目录包含对应交易品种的不同时间周期数据文件。

- 每个交易品种目录(如EURUSD/)包含多个时间周期的CSV文件:
  - **{品种}_m1.csv**: 1分钟周期数据
  - **{品种}_m5.csv**: 5分钟周期数据
  - **{品种}_m15.csv**: 15分钟周期数据
  - **{品种}_m30.csv**: 30分钟周期数据
  - **{品种}_h1.csv**: 1小时周期数据
  - **{品种}_h4.csv**: 4小时周期数据
  - **{品种}_d1.csv**: 日线周期数据

### realtime/ - 实时市场数据
此目录按交易品种组织实时行情数据。结构类似于historical/目录，但包含的是实时更新的数据。

- 每个交易品种目录包含多个时间周期的实时CSV文件:
  - **{品种}_m1_realtime.csv**: 1分钟实时数据
  - **{品种}_m5_realtime.csv**: 5分钟实时数据
  - 等等

### 其他目录

- **backups/**: 重要数据的备份
- **cache/**: 临时缓存数据，可定期清理
- **logs/**: 系统运行日志

## 文件命名约定

1. 历史数据文件: `{品种}_{时间周期}.csv`
   - 例: EURUSD_m5.csv 表示欧元/美元5分钟周期数据

2. 实时数据文件: `{品种}_{时间周期}_realtime.csv`
   - 例: EURUSD_m5_realtime.csv 表示欧元/美元5分钟实时数据

3. 财经日历数据文件:
   - 历史原始数据: `Investing.com (Economic_Calendar_YYYYMMDD - YYYYMMDD).html`
   - 处理后历史数据: `economic_calendar_{年份}_{月份}.csv`
   - 实时原始HTML: `realtime_calendar.html` （文件名可在配置中修改）
   - 处理后实时CSV（中间文件）: `processed_live.csv` （文件名可在配置中修改）
   - 筛选后实时CSV: `filtered_live.csv` （前缀可在配置中修改）

## 数据库文件

系统使用SQLite数据库存储财经日历数据:
- `calendar/filtered/history/economic_calendar.db`: 筛选后的历史数据和实时数据合并后的数据库（最终存储）

## 备注

- 所有数据文件应使用UTF-8编码
- CSV文件通常包含标题行
- 历史数据通常按时间升序排列
- 定期检查并清理缓存和日志目录 