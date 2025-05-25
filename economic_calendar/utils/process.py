import os
import sys
import subprocess
import logging
import time
from .paths import PROJECT_PATHS # 导入项目路径

logger = logging.getLogger(__name__)

def run_command(command: list, expected_output_path: str = None, max_retries: int = 1, retry_delay: int = 3):
    """执行命令行命令，带重试、环境处理和输出验证"""
    command_str = ' '.join(command)
    logger.info(f"准备执行命令 (最多重试 {max_retries} 次): {command_str}")

    project_root = PROJECT_PATHS['root']
    venv_scripts_path = PROJECT_PATHS['venv_scripts']

    for attempt in range(max_retries + 1):
        logger.info(f"尝试次数 {attempt + 1}/{max_retries + 1}")
        try:
            # --- 环境处理 ---
            env = os.environ.copy()
            if not os.path.isdir(venv_scripts_path):
                logger.warning(f"venv Scripts 目录不存在: {venv_scripts_path}，子命令可能失败")

            original_path = env.get('PATH', '')
            path_list = original_path.split(os.pathsep)
            abs_venv_scripts_path = os.path.abspath(venv_scripts_path)
            path_list = [p for p in path_list if os.path.abspath(p) != abs_venv_scripts_path]
            path_list.insert(0, venv_scripts_path)
            # --- 移除 Anaconda 路径的逻辑保持原样，但需注意其通用性 ---
            path_list = [p for p in path_list if not (
                           os.path.join('anaconda3', 'Scripts') in p or
                           os.path.join('anaconda3', 'condabin') in p or
                           os.path.join('Anaconda3', 'Scripts') in p or
                           os.path.join('Anaconda3', 'condabin') in p
                        )]
            new_path = os.pathsep.join(path_list)
            env['PATH'] = new_path
            # --- 环境处理结束 ---

            if command[0] != sys.executable:
                 logger.warning(f"命令的第一个参数不是 sys.executable ({sys.executable}), 而是 {command[0]}。确保这是有意的。")

            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                cwd=project_root, # 在项目根目录执行
                env=env
            )
            logger.info(f"命令执行成功 (尝试 {attempt + 1}): {command_str}")
            if result.stdout:
                 logger.info("命令标准输出:")
                 logger.info(result.stdout.strip())
            if result.stderr:
                 logger.warning("命令标准错误输出:")
                 logger.warning(result.stderr.strip())

            # --- 输出验证 ---
            if expected_output_path:
                output_full_path = os.path.join(project_root, expected_output_path) # 确保是绝对/相对根目录的路径
                logger.info(f"验证预期输出文件: {output_full_path}")
                if os.path.exists(output_full_path) and os.path.getsize(output_full_path) > 0:
                    logger.info("预期输出文件验证成功 (存在且非空)。")
                    return True # 命令成功且输出有效
                else:
                    error_msg = f"预期输出文件验证失败: {output_full_path} 不存在或为空。"
                    logger.error(error_msg)
                    if attempt < max_retries:
                        logger.info(f"将在 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("已达到最大重试次数，输出验证仍失败。")
                        return False
            else:
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"命令执行失败 (尝试 {attempt + 1}): {command_str}")
            logger.error(f"返回码: {e.returncode}")
            logger.error("错误输出:")
            if e.stderr:
                logger.error(e.stderr.strip())
            if e.stdout:
                logger.error("命令标准输出 (可能包含线索):")
                logger.error(e.stdout.strip())
            if attempt < max_retries:
                logger.info(f"将在 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                logger.error("已达到最大重试次数，命令执行仍失败。")
                return False
        except FileNotFoundError:
            logger.error(f"命令或其依赖未找到: {command[0]}。请检查 PATH 设置和 venv 环境。")
            return False
        except Exception as e:
            logger.error(f"执行命令时发生未知错误 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries:
                 logger.info(f"将在 {retry_delay} 秒后重试...")
                 time.sleep(retry_delay)
            else:
                 logger.error("已达到最大重试次数，仍存在未知错误。")
                 return False

    return False # 如果循环结束仍未成功 