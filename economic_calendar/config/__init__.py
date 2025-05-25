"""
配置模块
提供配置加载和管理功能
"""

# 从keywords模块导出关键配置
from .keywords import (
    IMPORTANT_KEYWORDS,
    USD_IMPORTANT_KEYWORDS,
    EUR_IMPORTANT_KEYWORDS,
    GBP_IMPORTANT_KEYWORDS,
    JPY_IMPORTANT_KEYWORDS,
    AUD_IMPORTANT_KEYWORDS,
    CAD_IMPORTANT_KEYWORDS,
    CHF_IMPORTANT_KEYWORDS,
    CNY_IMPORTANT_KEYWORDS,
    CURRENCY_IMPORTANT_KEYWORDS,
    IMPORTANT_EVENT_KEYWORDS,
    IMPORTANT_SPEAKERS,
    CURRENCY_KEYWORDS,
    CRITICAL_EVENTS,
    US_MARKET_OPEN_TIME,
    US_MARKET_OPEN_WINDOW,
    HIGH_IMPACT_KEYWORDS,
)

# 定义公共接口
__all__ = [
    'IMPORTANT_KEYWORDS',
    'USD_IMPORTANT_KEYWORDS',
    'EUR_IMPORTANT_KEYWORDS',
    'GBP_IMPORTANT_KEYWORDS',
    'JPY_IMPORTANT_KEYWORDS',
    'AUD_IMPORTANT_KEYWORDS',
    'CAD_IMPORTANT_KEYWORDS',
    'CHF_IMPORTANT_KEYWORDS',
    'CNY_IMPORTANT_KEYWORDS',
    'CURRENCY_IMPORTANT_KEYWORDS',
    'IMPORTANT_EVENT_KEYWORDS',
    'IMPORTANT_SPEAKERS',
    'CURRENCY_KEYWORDS',
    'CRITICAL_EVENTS',
    'US_MARKET_OPEN_TIME',
    'US_MARKET_OPEN_WINDOW',
    'HIGH_IMPACT_KEYWORDS',
]

import os
import yaml
import logging

logger = logging.getLogger('economic_data_sources.config')

def load_config(config_path):
    """
    加载YAML配置文件
    
    参数:
        config_path (str): 配置文件路径
        
    返回:
        dict: 配置字典，如果加载失败则返回空字典
    """
    try:
        # 首先尝试直接加载指定的配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logger.info(f"已加载配置: {config_path}")
            return config or {}
    except Exception as e:
        logger.error(f"加载指定配置失败: {config_path}, 错误: {e}")
        
        # 如果指定的配置文件加载失败，尝试从模块目录加载
        try:
            # 获取模块目录路径
            module_dir = os.path.dirname(os.path.abspath(__file__))
            module_config_path = os.path.join(module_dir, 'workflow_config.yaml')
            
            logger.info(f"尝试从模块目录加载配置: {module_config_path}")
            with open(module_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"已从模块目录加载配置: {module_config_path}")
                return config or {}
        except Exception as inner_e:
            logger.error(f"从模块目录加载配置也失败: {inner_e}")
            return {} 