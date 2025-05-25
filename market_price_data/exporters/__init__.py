"""
MT5导出器模块

提供将数据导出为MT5兼容格式的功能
"""

from .exporter import export_to_mt5_format

__all__ = [
    'export_to_mt5_format'
] 