import os
import sys

def _find_project_root():
    """动态查找项目根目录（包含 .git 或 pyproject.toml 的目录）"""
    current_dir = os.path.dirname(os.path.abspath(__file__)) # utils 目录
    economic_data_sources_dir = os.path.dirname(current_dir) # economic_data_sources 目录
    project_root_candidate = os.path.dirname(economic_data_sources_dir)

    # 可以在这里添加更复杂的逻辑来确认根目录，例如查找特定文件或标记
    # 简单起见，我们假设 economic_data_sources 的父目录就是根目录
    if os.path.exists(os.path.join(project_root_candidate, 'pyproject.toml')) or \
       os.path.exists(os.path.join(project_root_candidate, '.git')):
        print("--- _find_project_root() finished ---") # 添加标记
        return project_root_candidate
    else:
        # 如果没有找到明确的标记，提供一个基于脚本位置的回退，但可能不准确
        print("Warning: Could not reliably determine project root based on markers (.git/pyproject.toml). Falling back based on script location.")
        return project_root_candidate

print("--- Defining PROJECT_ROOT... ---")
PROJECT_ROOT = _find_project_root()
print(f"--- PROJECT_ROOT defined: {PROJECT_ROOT} ---")

print("--- Defining other paths... ---")
ECONOMIC_DATA_SOURCES_DIR = os.path.join(PROJECT_ROOT, 'economic_data_sources')
TASKS_DIR = os.path.join(ECONOMIC_DATA_SOURCES_DIR, 'tasks')
UTILS_DIR = os.path.join(ECONOMIC_DATA_SOURCES_DIR, 'utils')
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
print("--- Basic paths defined. Defining PROJECT_PATHS dictionary... ---")

# 将计算出的路径存储在字典中，方便使用
PROJECT_PATHS = {
    'root': PROJECT_ROOT,
    'economic_data_sources': ECONOMIC_DATA_SOURCES_DIR,
    'tasks': TASKS_DIR,
    'utils': UTILS_DIR,
    'config_dir': CONFIG_DIR,
    'data_dir': DATA_DIR,
    'log_dir': LOG_DIR,
    'venv_scripts': os.path.join(PROJECT_ROOT, '.venv', 'Scripts'),
    'venv_python': os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe'),
    'config_file': os.path.join(PROJECT_ROOT, 'economic_calendar', 'config', 'processing.yaml'),
    # 可以根据需要添加更多具体路径
    'history_raw_dir': os.path.join(DATA_DIR, 'calendar', 'raw', 'history'),
    'history_processed_dir': os.path.join(DATA_DIR, 'calendar', 'processed', 'history'),
    'history_filtered_dir': os.path.join(DATA_DIR, 'calendar', 'filtered', 'history'),
    'live_raw_dir': os.path.join(DATA_DIR, 'calendar', 'raw', 'live'),
    'live_processed_dir': os.path.join(DATA_DIR, 'calendar', 'processed', 'live'),
    'live_filtered_dir': os.path.join(DATA_DIR, 'calendar', 'filtered', 'live'),
}
print("--- PROJECT_PATHS dictionary defined. ---")

# (可选) 确保日志目录存在
print("--- Checking/creating LOG_DIR... ---")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        print(f"--- LOG_DIR created: {LOG_DIR} ---")
    except OSError as e:
        print(f"Error creating log directory {LOG_DIR}: {e}")
else:
    print(f"--- LOG_DIR already exists: {LOG_DIR} ---")

print("--- paths.py execution finished. ---")

if __name__ == '__main__':
    # 测试输出
    print("Project Paths:")
    for key, value in PROJECT_PATHS.items():
        print(f"  {key}: {value}") 