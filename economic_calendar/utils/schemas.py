from pydantic import BaseModel, Field, DirectoryPath, FilePath
from typing import List, Dict, Optional, Any
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- 基础模型 ---

class PathsConfig(BaseModel):
    # 历史数据相关路径 (相对于项目根目录)
    history_html_dir: str                 # 原始 HTML 输入目录
    history_processed_dir: str          # 处理后（合并/去重）数据目录
    history_db_path: str                  # 处理后数据库路径
    processed_csv_name: str             # 处理后（合并/去重）CSV文件名
    history_filtered_dir: str           # 筛选后数据目录
    filtered_output_name: str           # 筛选后 CSV 文件名

    # 实时数据相关路径 (相对于项目根目录)
    raw_live_csv: str
    filtered_live_output_dir: str
    filtered_live_output_name: str
    realtime_db_path: str               # 实时数据库路径

    # (可选) 其他路径
    log_dir: str = "logs"

class ScriptConfig(BaseModel):
    path: str
    args: List[str] = []

class ScriptsConfig(BaseModel):
    process_calendar: ScriptConfig
    filter_main: ScriptConfig
    download_investing_calendar: ScriptConfig

# --- 修改 RetriesConfig --- 
class RetriesConfig(BaseModel):
    download_realtime: int = 1
    process_history: int = 1
    filter_history_data: int = 1 # 区分历史筛选重试
    filter_realtime_data: int = 1 # 区分实时筛选重试
    delay_seconds: int = 3

class MT5ProfileConfig(BaseModel):
    """单一套 MT5 配置文件的模型"""
    server: str
    login: int
    password: str
    executable_path: Optional[FilePath] = None # 路径验证
    directory: DirectoryPath # 路径验证，确保是目录
    timeout: int = 30

# --- 新增 FilteringDefaults --- 
class FilteringDefaults(BaseModel):
    # 定义 filter_main.py 可能接受的参数及其类型
    # 注意：这里的字段名应与 filter_main.py 的命令行参数名（去掉 --）匹配，以便后续构造参数列表
    min_importance: Optional[int] = None
    with_keywords: Optional[bool] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    target_currencies: Optional[List[str]] = None # <--- 重命名字段以匹配 main.py 的 --target-currencies
    # target_dates: Optional[List[str]] = None
    add_market_open: Optional[bool] = None
    export_format: str = "csv"
    # 不应包含 log_level，由各脚本自行管理

# --- 顶层配置模型 (更新) ---

class WorkflowConfigModel(BaseModel):
    paths: PathsConfig
    scripts: ScriptsConfig
    retries: Optional[RetriesConfig] = Field(default_factory=RetriesConfig)
    filtering_history: Optional[FilteringDefaults] = Field(default_factory=FilteringDefaults) # 历史筛选默认值
    filtering_realtime: Optional[FilteringDefaults] = Field(default_factory=FilteringDefaults) # 实时筛选默认值
    keywords: Optional[List[str]] = None # <--- 新增：用于关键词过滤的列表

    # --- 新增：支持多套 MT5 配置 ---
    mt5_profiles: Optional[Dict[str, MT5ProfileConfig]] = None
    active_mt5_profile: Optional[str] = None

    # Pydantic v2 的配置
    model_config = SettingsConfigDict(extra='ignore')

# --- 用于加载和验证配置的函数 (如果需要) --- 
# def load_config(config_path: str = "config/workflow_config.yaml") -> WorkflowConfigModel:
#     # ... (加载和验证逻辑) ...
#     pass

# --- 新增 MT5Config --- 
# class MT5Config(BaseModel):
#     pass # 或者直接删除

# 移除之前关于方案A/B/C 的注释，因为我们已确定使用方案 B 的变体 