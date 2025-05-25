import os
import sys
import shutil
import logging
from .paths import PROJECT_PATHS # 导入项目路径

logger = logging.getLogger(__name__)

def check_environment():
    """检查 Python 解释器和 .venv 结构"""
    logger.info("--- 开始环境检查 ---")
    # 使用 PROJECT_PATHS 获取路径
    venv_python_expected = PROJECT_PATHS['venv_python']
    venv_scripts_path = PROJECT_PATHS['venv_scripts']
    project_root = PROJECT_PATHS['root']

    current_python = sys.executable
    logger.info(f"当前 Python 解释器: {current_python}")
    logger.info(f"期望的 .venv Python 解释器: {venv_python_expected}")

    if os.path.normpath(current_python).lower() != os.path.normpath(venv_python_expected).lower():
        logger.warning("当前 Python 解释器似乎不是项目 .venv 中的解释器。")
        venv_python_found = shutil.which("python", path=os.path.dirname(venv_python_expected))
        if venv_python_found:
            logger.info(f"在 .venv/Scripts 中找到了 python.exe: {venv_python_found}。脚本将尝试使用它执行子命令。")
        else:
            logger.error(f"在 {os.path.dirname(venv_python_expected)} 中未找到 python.exe。请确保 .venv 环境已正确创建和激活。")
            return False
    else:
        logger.info("当前 Python 解释器验证成功 (指向 .venv)。")

    if not os.path.isdir(venv_scripts_path):
        logger.error(f"关键目录 .venv/Scripts 不存在: {venv_scripts_path}。请确保虚拟环境完整。")
        return False
    logger.info(f".venv/Scripts 目录存在: {venv_scripts_path}")
    logger.info("--- 环境检查通过 ---")
    return True 