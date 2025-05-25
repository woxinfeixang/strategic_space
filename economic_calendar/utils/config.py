import os
import yaml
import logging
from pydantic import ValidationError
from typing import Optional # 导入 Optional
# 假设模型在同目录的 schemas.py 中
from .schemas import WorkflowConfigModel # 导入 Pydantic 模型

logger = logging.getLogger(__name__) # 使用当前模块名作为 logger 名称

def load_config(config_path: str) -> Optional[WorkflowConfigModel]: # 添加类型提示
    """加载并验证 YAML 配置文件"""
    if not os.path.exists(config_path):
        logger.error(f"配置文件未找到: {config_path}")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        if config_dict is None:
            logger.error(f"配置文件为空或格式无效: {config_path}")
            return None

        # 使用 Pydantic 进行验证和解析
        config_model = WorkflowConfigModel(**config_dict)
        logger.info(f"成功加载并验证配置文件: {config_path}")
        # 使用 model_dump() 获取字典表示形式进行日志记录 (Pydantic V2+)
        # 对于 Pydantic V1，使用 .dict()
        try:
             config_dict_log = config_model.model_dump()
        except AttributeError:
             config_dict_log = config_model.dict() # Fallback for Pydantic V1
        logger.debug(f"加载的配置内容 (验证后): {config_dict_log}")
        return config_model
    except yaml.YAMLError as e:
        logger.error(f"解析 YAML 配置文件失败: {config_path} - {e}")
        return None
    except ValidationError as e:
        logger.error(f"配置文件验证失败: {config_path}")
        # Pydantic 的 ValidationError 会提供详细错误信息
        logger.error(f"Validation Errors:\n{e}")
        return None
    except Exception as e:
        logger.error(f"加载配置文件时发生未知错误: {config_path} - {e}")
        return None 