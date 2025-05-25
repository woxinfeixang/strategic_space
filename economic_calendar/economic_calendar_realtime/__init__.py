"""
实时财经日历下载模块
"""

from .download_investing_calendar import scrape_investing_calendar
from .download_investing_calendar import main as download_calendar
# from .download_investing_calendar import save_to_csv

__all__ = ["scrape_investing_calendar", "download_calendar"]
