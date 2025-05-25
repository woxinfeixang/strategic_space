# MT5数据清理工具

该工具用于清理MT5数据下载过程中产生的备份文件和临时数据文件，有助于维持数据目录的整洁。

工具包含两个主要文件：
- `cleanup_backups.py`：核心Python脚本，实现文件清理功能
- `cleanup_backups.bat`：Windows批处理脚本，方便执行和自动化

## 功能特点

- 自动识别并清理多种类型文件：
  - 备份文件（`.bak_YYYYMMDD_HHMMSS`格式）
  - 临时文件（`.tmp`、`temp_*`、`*_temp.*`、`.part`、`.temp`格式）
- 灵活的清理策略：
  - 按文件日期清理（删除N天前的文件）
  - 按数量清理（每个原始文件保留最近N个备份）
  - 可同时清理备份文件和临时文件
  - 可单独清理备份文件或临时文件
- 安全操作：
  - 支持预览模式（显示将被删除的文件但不实际删除）
  - 显示文件大小和创建/修改日期
  - 提供详细的执行报告

## 使用方法

### Python脚本直接使用

```bash
# 基本用法
python cleanup_backups.py --keep 2 --days 30 --execute

# 只清理临时文件
python cleanup_backups.py --temp-only --execute

# 只清理备份文件
python cleanup_backups.py --backup-only --keep 1 --execute

# 模拟运行（不实际删除）
python cleanup_backups.py --keep 1 --days 30

# 清理自定义目录
python cleanup_backups.py --dir "E:\Your\Custom\Path" --keep 1 --execute
```

### 命令行参数说明

| 参数 | 说明 |
|------|------|
| `--days N` | 删除N天前的文件 |
| `--keep N` | 为每个文件保留最近N个备份 |
| `--remove-all` | 删除所有备份和临时文件 |
| `--execute` | 执行实际删除（不加此参数则只预览） |
| `--dir PATH` | 指定要清理的目录 |
| `--temp-only` | 只清理临时文件 |
| `--backup-only` | 只清理备份文件 |

### 使用批处理脚本

批处理脚本配置了默认参数，执行以下命令即可运行：

```bash
.\cleanup_backups.bat
```

当前批处理配置为：保留最近1个备份，删除30天前的备份，并清理所有临时文件。

## 自动化清理

可以通过Windows任务计划程序设置定期自动清理：

1. 打开Windows任务计划程序（按Win+R，输入`taskschd.msc`）
2. 点击右侧的"创建基本任务"
3. 输入任务名称，如"MT5数据备份清理"
4. 选择触发器（例如"每周"或"每天"）
5. 选择开始时间和频率
6. 选择"启动程序"操作
7. 程序或脚本选择批处理文件的完整路径：`E:\Programming\strategic space\cleanup_backups.bat`
8. 点击"完成"保存任务

## 文件格式说明

### 备份文件

下载脚本运行时会自动创建备份文件，格式为：`原文件名.bak_YYYYMMDD_HHMMSS`

例如：
- `XAUUSD_m15.csv.bak_20250323_130039`
- `EURUSD_m1.csv.bak_20250323_130119`

### 临时文件

下载过程中可能产生的临时文件，通常以下格式：
- `*_temp.csv`：临时数据文件
- `.tmp`：通用临时文件
- `.part`：未完成下载的文件
- `temp_*`：临时前缀文件

## 注意事项

1. 首次运行时建议使用不带`--execute`的命令查看将被删除的文件
2. 如果不确定清理效果，可以先备份重要数据
3. 可以根据需要修改批处理文件中的参数

## 源代码

### cleanup_backups.py

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理MT5数据下载过程中产生的备份文件
"""
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import re
import shutil


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None


def find_backup_and_temp_files(data_dir):
    """查找备份文件和临时数据文件"""
    files_to_clean = []
    # 备份文件模式
    backup_pattern = re.compile(r'\.bak_\d{8}_\d{6}$')
    # 临时文件模式
    temp_patterns = [
        re.compile(r'\.tmp$'),           # .tmp文件
        re.compile(r'^temp_'),           # temp_开头的文件
        re.compile(r'_temp\.'),          # _temp.的文件
        re.compile(r'\.part$'),          # .part文件（未完成下载）
        re.compile(r'\.temp$')           # .temp文件
    ]

    for root, _, files in os.walk(data_dir):
        for file in files:
            file_path = os.path.join(root, file)
            file_type = None

            # 检查是否为备份文件
            if backup_pattern.search(file):
                file_type = "备份"
                try:
                    # 提取日期时间字符串
                    date_str = backup_pattern.search(file).group(0).replace('.bak_', '')

                    file_date = datetime.strptime(date_str, '%Y%m%d_%H%M%S')
                except Exception as e:
                    print(f"处理备份文件 {file} 时出错: {e}")
                    continue

            # 检查是否为临时文件
            for pattern in temp_patterns:
                if pattern.search(file):
                    file_type = "临时"
                    try:
                        # 使用文件修改时间作为日期
                        file_date = datetime.fromtimestamp(os.path.getmtime(file_path))

                    except Exception as e:
                        print(f"处理临时文件 {file} 时出错: {e}")
                        continue
                    break

            if file_type:
                # 对每个文件保存路径、文件名、类型、备份日期和大小        
                files_to_clean.append({
                    'path': file_path,
                    'filename': file,
                    'type': file_type,
                    'date': file_date,
                    'size': os.path.getsize(file_path) / (1024 * 1024)  # 大小转换为MB      
                })

    # 按日期排序
    files_to_clean.sort(key=lambda x: x['date'], reverse=True)
    return files_to_clean


def group_files_by_original(files_to_clean):
    """按原始文件名分组文件"""
    grouped = {}

    for file_info in files_to_clean:
        if file_info['type'] == "备份":
            # 获取原始文件名(去除.bak_YYYYMMDD_HHMMSS部分)
            original_name = re.sub(r'\.bak_\d{8}_\d{6}$', '', file_info['path'])
            group_key = f"备份_{original_name}"
        else:  # 临时文件
            # 临时文件按目录分组
            dir_name = os.path.dirname(file_info['path'])
            group_key = f"临时_{dir_name}"

        if group_key not in grouped:
            grouped[group_key] = []

        grouped[group_key].append(file_info)

    return grouped


def cleanup_files(data_dir, keep_days=None, keep_count=None, dry_run=False, remove_all=False, 
                 only_backup=False, only_temp=False):
    """清理备份文件和临时文件"""
    if not os.path.exists(data_dir):
        print(f"数据目录 {data_dir} 不存在")
        return

    print(f"扫描目录: {data_dir} 中的备份文件和临时文件...")
    files_to_clean = find_backup_and_temp_files(data_dir)

    if not files_to_clean:
        print("未找到需要清理的文件")
        return

    # 统计各类型文件
    backup_files = [f for f in files_to_clean if f['type'] == "备份"]
    temp_files = [f for f in files_to_clean if f['type'] == "临时"]
    
    # 根据只清理备份或只清理临时的选项过滤
    if only_backup:
        files_to_clean = backup_files
        print("只清理备份文件")
    elif only_temp:
        files_to_clean = temp_files
        print("只清理临时文件")

    print(f"找到 {len(files_to_clean)} 个文件需要清理，总大小 {sum(f['size'] for f in files_to_clean):.2f} MB")
    print(f"  其中 {len(backup_files)} 个备份文件，{len(temp_files)} 个临时文件")     

    # 按原始文件名分组
    grouped_files = group_files_by_original(files_to_clean)
    print(f"共有 {len(grouped_files)} 组文件")

    # 设置截止日期
    cutoff_date = None
    if keep_days is not None:
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        print(f"将删除 {cutoff_date} 之前的文件")

    deleted_count = 0
    deleted_size = 0

    # 处理每组文件
    for group_key, files in grouped_files.items():
        is_backup = group_key.startswith("备份_")
        group_type = "备份" if is_backup else "临时"
        group_name = group_key.split("_", 1)[1]

        # 根据类型过滤
        if only_backup and not is_backup:
            continue
        if only_temp and is_backup:
            continue

        print(f"\n处理 {group_type}文件: {os.path.basename(group_name) if is_backup else group_name}")
        to_delete = []

        if remove_all:
            to_delete = files
        else:
            # 临时文件全部删除
            if not is_backup:
                to_delete = files
            else:
                # 如果指定了keep_count，保留最新的几个备份
                if keep_count is not None and is_backup:
                    # files已按日期排序，保留前keep_count个
                    to_delete = files[keep_count:]

                # 如果指定了keep_days，删除超过天数的
                if cutoff_date is not None:
                    # 更新to_delete列表，确保按日期筛选
                    date_filtered = [f for f in files if f['date'] < cutoff_date]
                    # 合并两个列表，去重
                    to_delete = list({f['path']: f for f in to_delete + date_filtered}.values())

        # 显示要删除的文件
        for file_info in to_delete:
            action = "将删除" if not dry_run else "将模拟删除"
            print(f"  {action}: {os.path.basename(file_info['path'])}  "
                  f"[{file_info['date'].strftime('%Y-%m-%d %H:%M:%S')}] "
                  f"{file_info['size']:.2f} MB")

            if not dry_run:
                try:
                    os.remove(file_info['path'])
                    deleted_count += 1
                    deleted_size += file_info['size']
                except Exception as e:
                    print(f"  删除失败: {e}")

    # 打印总结
    if dry_run:
        print(f"\n预览模式：将删除 {deleted_count} 个文件，总计约 {deleted_size:.2f} MB")
    else:
        print(f"\n已删除 {deleted_count} 个文件，释放空间约 {deleted_size:.2f} MB")

    return deleted_count, deleted_size


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='清理MT5数据备份和临时文件')
    parser.add_argument('--days', type=int, help='删除N天前的文件')
    parser.add_argument('--keep', type=int, help='为每个文件保留最近N个备份')
    parser.add_argument('--remove-all', action='store_true', help='删除所有备份和临时文件')
    parser.add_argument('--execute', action='store_true', 
                        help='执行实际删除（不加此参数则只预览）')
    parser.add_argument('--dir', type=str, help='指定要清理的目录',
                        default=os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument('--temp-only', action='store_true', help='只清理临时文件')
    parser.add_argument('--backup-only', action='store_true', help='只清理备份文件')
    
    args = parser.parse_args()
    
    # 验证参数
    if args.days is not None and args.days <= 0:
        parser.error("--days 必须大于0")
    if args.keep is not None and args.keep <= 0:
        parser.error("--keep 必须大于0")
    if args.temp_only and args.backup_only:
        parser.error("--temp-only 和 --backup-only 不能同时使用")
    
    return args


def main():
    args = parse_args()
    
    # 至少需要一个清理条件
    if not any([args.days, args.keep, args.remove_all]):
        print("警告：未指定清理条件，将使用默认值 --keep 1 --days 30")
        args.keep = 1
        args.days = 30
    
    # 获取清理目录
    data_dir = args.dir
    
    # 执行清理
    cleanup_files(
        data_dir=data_dir,
        keep_days=args.days,
        keep_count=args.keep,
        dry_run=not args.execute,
        remove_all=args.remove_all,
        only_backup=args.backup_only,
        only_temp=args.temp_only
    )


if __name__ == "__main__":
    main()
```

### cleanup_backups.bat

```bat
@echo off
echo MT5数据备份和临时文件清理工具
echo ===================================

rem 设置环境变量
set CONDA_ENV=mt5_env
set SCRIPT_PATH=%~dp0cleanup_backups.py

rem 执行清理脚本
call conda activate %CONDA_ENV%
echo 执行清理操作...
python "%SCRIPT_PATH%" --keep 1 --days 30 --execute

echo 清理完成!
pause