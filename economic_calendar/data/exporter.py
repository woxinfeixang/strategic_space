"""
数据导出模块
提供导出功能，将经济日历数据导出为不同格式
"""
import os
import csv
import json
import logging
from datetime import datetime
import pandas as pd
import sqlite3

# 设置日志记录器
logger = logging.getLogger('economic_calendar.data.exporter')

# --- 标准列格式定义 ---
STANDARD_COLUMNS = ['Date', 'Weekday', 'Time', 'Currency', 'Importance', 'Event', 'Actual', 'Forecast', 'Previous']

def format_importance_to_stars(imp_num):
    """将数字重要性转换为 N星 字符串"""
    if pd.isna(imp_num):
        return "" # 处理空值
    try:
        num = int(imp_num)
        if num > 0:
            return f"{num}星"
        else:
            return "" # 0 星显示为空字符串
    except (ValueError, TypeError):
        # 如果已经是 'N星' 格式或其他非数字，尝试直接返回
        if isinstance(imp_num, str) and '星' in imp_num:
             return imp_num
        return str(imp_num) # 其他情况返回原始字符串

def get_weekday_from_date(date_str):
    """从 YYYY-MM-DD 格式的日期字符串获取中文星期"""
    if not date_str or not isinstance(date_str, str):
        return ""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        # 返回中文星期几
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return weekdays[date_obj.weekday()]
    except ValueError:
        return "" # 日期格式错误返回空

def export_to_csv(df: pd.DataFrame, output_file: str, encoding='utf-8-sig'):
    """
    导出事件数据到CSV文件

    参数:
        df (pd.DataFrame): 要导出的 Pandas DataFrame。
        output_file (str): 输出文件路径。
        encoding (str): 文件编码, 默认 utf-8-sig 保证 Excel 打开不乱码。

    返回:
        bool: 是否成功
    """
    if df is None or df.empty:
        logger.warning("输入的 DataFrame 为空，无法导出为 CSV")
        return False

    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"创建目录: {output_dir}")

        # 确保列顺序和存在性，并设置空值表示
        # 检查 DataFrame 是否包含所有标准列，不包含则添加并填充空字符串
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        # 选择标准列并按指定顺序排列
        df_to_export = df[STANDARD_COLUMNS]

        # 直接使用处理后的 DataFrame 导出，并指定 na_rep
        df_to_export.to_csv(output_file, index=False, encoding=encoding, na_rep='')

        logger.info(f"成功导出 {len(df_to_export)} 条事件到 {output_file}")
        return True

    except Exception as e:
        logger.error(f"导出CSV文件失败: {e}", exc_info=True)
        return False

def export_to_json(df: pd.DataFrame, output_file: str):
    """
    导出事件数据到JSON文件

    参数:
        df (pd.DataFrame): 要导出的 Pandas DataFrame。
        output_file (str): 输出文件路径。

    返回:
        bool: 是否成功
    """
    if df is None or df.empty:
        logger.warning("输入的 DataFrame 为空，无法导出为 JSON")
        return False

    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"创建目录: {output_dir}")

        # 将 DataFrame 转换为字典列表再导出
        records = df.to_dict(orient='records')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        logger.info(f"成功导出 {len(df)} 条事件到 {output_file}")
        return True

    except Exception as e:
        logger.error(f"导出JSON文件失败: {e}", exc_info=True)
        return False

def export_to_mt5(df: pd.DataFrame, output_file: str):
    """
    导出事件数据到符合标准格式的 CSV 文件 (GBK 和 UTF-8)

    参数:
        df (pd.DataFrame): 要导出的 Pandas DataFrame (应包含原始数据)。
        output_file (str): 输出文件路径 (不含 _utf8 后缀)。

    返回:
        bool: 是否成功
    """
    if df is None or df.empty:
        logger.warning("输入 DataFrame 为空，无法导出为 MT5 格式")
        return False

    try:
        # --- 1. 复制 DataFrame 以避免修改原始数据 ---
        df_processed = df.copy()

        # --- 2. 重命名列 (将可能的中文或旧名称映射到标准英文名) ---
        # 注意: 这里假设输入的 df 列名是中文
        column_mapping = {
            '日期': 'Date',
            '星期': 'Weekday', # 如果输入已有星期列
            '时间': 'Time',
            '货币': 'Currency',
            '重要性': 'Importance',
            '事件': 'Event',
            '实际值': 'Actual',
            '预测值': 'Forecast',
            '前值': 'Previous'
        }
        df_processed.rename(columns={k: v for k, v in column_mapping.items() if k in df_processed.columns}, inplace=True)


        # --- 3. 数据转换与补全 ---
        if 'Date' in df_processed.columns:
            df_processed['Weekday'] = df_processed['Date'].apply(get_weekday_from_date)
        else:
            logger.warning("DataFrame 中缺少 Date 列，无法计算 Weekday")
            if 'Weekday' not in df_processed.columns:
                 df_processed['Weekday'] = ""

        if 'Importance' in df_processed.columns:
            df_processed['Importance'] = df_processed['Importance'].apply(format_importance_to_stars)
        else:
             logger.warning("DataFrame 中缺少 Importance 列，无法格式化")

        for col in STANDARD_COLUMNS:
            if col not in df_processed.columns:
                df_processed[col] = ""

        # --- 4. 调整列顺序和选择 ---
        try:
            df_standard = df_processed[STANDARD_COLUMNS]
        except KeyError as e:
             logger.error(f"无法按标准列名选择列: {e}。当前 DataFrame 列: {df_processed.columns.tolist()}")
             return False

        # --- 5. 导出 CSV ---
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"创建目录: {output_dir}")

        base, ext = os.path.splitext(output_file)
        if base.endswith('_utf8'):
            base = base[:-5]
        utf8_file = f"{base}_utf8{ext}"
        gbk_file = f"{base}{ext}"

        try:
            df_standard.to_csv(utf8_file, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
            logger.info(f"成功导出 {len(df_standard)} 条事件到 (UTF-8): {utf8_file}")
        except Exception as e_utf8:
            logger.error(f"导出 UTF-8 CSV 文件失败: {e_utf8}")

        try:
            df_standard.to_csv(gbk_file, index=False, encoding='gbk', errors='ignore', quoting=csv.QUOTE_MINIMAL)
            logger.info(f"成功导出 {len(df_standard)} 条事件到 (GBK): {gbk_file}")
        except Exception as e_gbk:
            logger.error(f"导出 GBK CSV 文件失败: {e_gbk}")
            return False

        return True

    except Exception as e:
        logger.error(f"导出 MT5 格式文件时发生意外错误: {e}", exc_info=True)
        return False

def export_to_sqlite(df: pd.DataFrame, output_db_file: str, table_name: str = "events"):
    """
    导出 Pandas DataFrame 到 SQLite 数据库文件。

    参数:
        df (pd.DataFrame): 要导出的 Pandas DataFrame。
        output_db_file (str): 输出的 SQLite 数据库文件路径。
        table_name (str): 数据库中的表名。默认为 "events"。

    返回:
        bool: 是否成功导出。
    """
    if df is None or df.empty:
        logger.warning(f"输入 DataFrame 为空，无法导出到 SQLite 表 '{table_name}'")
        return False

    conn = None
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_db_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"创建数据库目录: {output_dir}")

        conn = sqlite3.connect(output_db_file)
        logger.info(f"连接到 SQLite 数据库: {output_db_file}")

        # 导出 DataFrame 到 SQLite 表，如果表存在则替换
        df.to_sql(table_name, conn, if_exists='replace', index=False)

        logger.info(f"成功导出 {len(df)} 条记录到 SQLite 数据库 '{output_db_file}' 的表 '{table_name}'")
        return True

    except sqlite3.Error as e:
        logger.error(f"导出到 SQLite 时发生数据库错误: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"导出到 SQLite 时发生意外错误: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logger.info("已关闭 SQLite 数据库连接") 