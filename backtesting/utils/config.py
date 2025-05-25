import yaml
from pathlib import Path

def load_config(config_path: str) -> dict:
    """加载YAML配置文件"""
    # 修正路径构建方式：从项目根目录开始解析
    full_path = Path.cwd() / config_path
    if not full_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {full_path}")
    
    with open(full_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
