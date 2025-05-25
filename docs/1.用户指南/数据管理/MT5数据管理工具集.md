# MT5数据管理工具集

本文档详细说明了项目中用于MT5数据管理的各种工具，包括数据下载、清理和检查工具。这些工具共同构成了一个完整的MT5数据管理解决方案。

## 目录

- [数据下载工具](#数据下载工具)
  - [大时间周期数据下载](#大时间周期数据下载)
  - [小时间周期数据下载](#小时间周期数据下载)
- [数据清理工具](#数据清理工具)
- [数据检查工具](#数据检查工具)
- [配置与设置](#配置与设置)
- [自动化数据管理](#自动化数据管理)

## 数据下载工具

项目包含两个专门的数据下载工具，针对不同时间周期采用不同的下载策略，以确保数据完整性和下载效率。

### 大时间周期数据下载

**文件名**: `download_mt5_data_from_2015_with_segments.py`

**功能特点**:
- 专门用于下载M30及更大时间周期的历史数据
- 采用分段下载策略，默认每段90天
- 支持从2015年开始的完整历史数据
- 自动合并数据段，生成连续的历史数据文件
- 处理的时间周期包括：M30、H1、H4、D1

**使用方法**:
```bash
# 基本用法
python download_mt5_data_from_2015_with_segments.py

# 指定开始日期
python download_mt5_data_from_2015_with_segments.py --start-date 2018-01-01

# 指定结束日期
python download_mt5_data_from_2015_with_segments.py --end-date 2023-12-31

# 调整段大小
python download_mt5_data_from_2015_with_segments.py --segment-days 60

# 强制重新下载
python download_mt5_data_from_2015_with_segments.py --force-redownload
```

**参数说明**:
- `--start-date`: 指定数据下载的起始日期，默认为2015-01-01
- `--end-date`: 指定数据下载的结束日期，默认为当前日期
- `--segment-days`: 指定每个下载段的天数，默认为90天
- `--force-redownload`: 强制重新下载所有数据，覆盖现有文件
- `--symbols`: 指定要下载的交易品种，用逗号分隔

### 小时间周期数据下载

**文件名**: `download_mt5_data_small_tf.py`

**功能特点**:
- 专门用于下载M1、M5、M15等小时间周期数据
- 采用按日分段下载策略，避免因数据量大导致的下载失败
- 针对不同时间周期设置了优化的起始日期
- 自动合并每日数据，生成连续的历史数据文件
- 处理的时间周期包括：M1、M5、M15

**使用方法**:
```bash
# 基本用法
python download_mt5_data_small_tf.py

# 指定M1数据起始日期
python download_mt5_data_small_tf.py --m1-start-date 2025-01-01

# 指定M5数据起始日期
python download_mt5_data_small_tf.py --m5-start-date 2024-01-01

# 指定M15数据起始日期
python download_mt5_data_small_tf.py --m15-start-date 2023-01-01

# 跳过M1数据下载
python download_mt5_data_small_tf.py --skip-m1

# 强制重新下载
python download_mt5_data_small_tf.py --force-redownload
```

**参数说明**:
- `--m1-start-date`: 指定M1数据下载的起始日期，默认为2025-01-30
- `--m5-start-date`: 指定M5数据下载的起始日期，默认为2024-07-01
- `--m15-start-date`: 指定M15数据下载的起始日期，默认为2023-02-01
- `--end-date`: 指定数据下载的结束日期，默认为当前日期
- `--skip-m1`: 跳过下载M1数据
- `--force-redownload`: 强制重新下载所有数据，覆盖现有文件
- `--symbols`: 指定要下载的交易品种，用逗号分隔

## 数据清理工具

**文件名**: `cleanup_backups.py` 和 `cleanup_backups.bat`

数据清理工具用于管理MT5数据下载过程中产生的备份文件和临时数据文件，有助于维持数据目录的整洁。详细说明请参考 [数据清理工具说明](README_数据清理工具.md)。

**功能特点**:
- 自动识别多种类型的备份和临时文件
- 灵活的清理策略：按日期清理或按数量保留
- 支持预览模式，在执行实际删除前查看将被删除的文件
- 提供Windows批处理脚本，便于定期自动执行

**使用方法**:
```bash
# 基本用法 - 保留每个文件最近2个备份，删除30天前的文件
python cleanup_backups.py --keep 2 --days 30 --execute

# 只清理临时文件
python cleanup_backups.py --temp-only --execute

# 只清理备份文件
python cleanup_backups.py --backup-only --keep 1 --execute

# 使用批处理脚本执行默认清理
.\cleanup_backups.bat
```

## 数据检查工具

项目包含两个数据检查工具，用于验证MT5数据的可用性和完整性。

### 通用数据可用性检查

**文件名**: `check_mt5_data_availability.py`

**功能特点**:
- 检查各个时间周期数据的可用性
- 报告每个品种和时间周期的最早可用数据日期
- 检查数据的连续性和完整性
- 支持检查的时间周期：M5、M15、M30、H1、H4、D1

**使用方法**:
```bash
python check_mt5_data_availability.py
```

### M1数据可用性检查

**文件名**: `check_m1_availability.py`

**功能特点**:
- 专门用于检查M1时间周期数据的可用性
- 详细报告M1数据的最早和最新日期
- 提供数据点数量和分布统计
- 识别数据中的空缺和异常

**使用方法**:
```bash
python check_m1_availability.py
```

## 配置与设置

所有数据管理工具使用共同的配置文件系统：

**主配置文件**: `config.json`

配置文件包含以下关键设置：
- MT5终端路径
- 数据保存目录
- 默认交易品种列表
- 时间周期设置

**示例配置**:
```json
{
  "mt5": {
    "terminal_path": "C:/Program Files/MetaTrader 5",
    "login": 12345678,
    "password": "password",
    "server": "BrokerServerName"
  },
  "paths": {
    "data_dir": "./data",
    "log_dir": "./logs"
  },
  "symbols": ["EURUSD", "GBPUSD", "XAUUSD"]
}
```

## 自动化数据管理

为了实现数据管理的自动化，可以使用Windows任务计划程序设置定期执行以下任务：

1. **定期下载最新数据**:
   - 创建批处理文件，组合调用下载脚本
   - 设置每日或每周定时执行

2. **定期清理备份文件**:
   - 使用`cleanup_backups.bat`脚本
   - 配置每周或每月定时执行

3. **数据完整性检查**:
   - 创建批处理文件，调用检查脚本
   - 配置每周执行，检查数据完整性

**示例批处理文件** (`update_data.bat`):
```bat
@echo off
echo 开始更新MT5数据 - %date% %time%

call conda activate mt5_env

echo 下载大时间周期数据...
python download_mt5_data_from_2015_with_segments.py --start-date 2023-01-01

echo 下载小时间周期数据...
python download_mt5_data_small_tf.py

echo 清理临时和备份文件...
python cleanup_backups.py --keep 2 --days 30 --execute

echo 检查数据完整性...
python check_mt5_data_availability.py > data_check_%date:~0,4%%date:~5,2%%date:~8,2%.log

echo 数据更新完成 - %date% %time%
pause
``` 