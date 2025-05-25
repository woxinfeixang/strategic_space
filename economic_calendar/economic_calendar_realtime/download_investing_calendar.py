import os
import csv
import sqlite3
import re
import json
from datetime import datetime
import asyncio
from typing import List, Dict, Any, Set, Optional
import logging
import sys
from pathlib import Path
from omegaconf import OmegaConf, DictConfig

# 定义项目根目录
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
        print(f"--- Added {PROJECT_ROOT} to sys.path ---")
except IndexError:
    print("ERROR: Could not determine project root directory.")
    sys.exit(1)

# 从core模块导入共享工具函数
from core.utils import load_app_config, get_absolute_path, setup_logging

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# --- 修改：移除 basicConfig，使用共享配置设置日志 ---
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

config: Optional[DictConfig] = None
logger = logging.getLogger('CalendarDownloader_PreInit') # Initial placeholder

try:
    # 加载配置
    config = load_app_config('economic_calendar/config/processing.yaml')
    
    # 从配置获取日志文件名
    log_filename = OmegaConf.select(config, 'logging.downloader_log_filename', default='calendar_downloader_fallback.log')
    
    # 设置日志
    logger = setup_logging(
        log_config=config.logging,
        log_filename=log_filename,
        logger_name='CalendarDownloader'
    )
    logger.info("下载脚本日志已使用 core.utils.setup_logging 配置")
except Exception as e:
    print(f"ERROR: Failed to load config or setup logging for downloader: {e}", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('CalendarDownloader_Fallback')
    logger.error("Downloader config/logging setup failed!", exc_info=True)
    # Exit if setup fails?
    # sys.exit(1)

def save_to_csv(data: List[Dict[str, Any]], config: DictConfig, fieldnames_order: List[str] | None = None):
    """将数据保存为 CSV 文件，路径和文件名来自配置"""
    if not data or not isinstance(data, list) or not isinstance(data[0], dict):
        logger.warning("无效数据，无法保存为CSV。")
        return
    try:
        output_dir_path = get_absolute_path(config, "economic_calendar.paths.raw_live_dir")
        if not output_dir_path:
            logger.error("无法从配置解析原始实时数据目录路径，无法保存 CSV。")
            return
        output_filename = OmegaConf.select(config, "economic_calendar.files.raw_live_csv", default="upcoming.csv")
        filepath = output_dir_path / output_filename
        os.makedirs(output_dir_path, exist_ok=True)

        # --- 设置固定列名映射，确保与参考文件一致 ---
        column_mapping = {
            "日期": "Date",
            "星期": "Weekday",
            "时间": "Time",
            "货币": "Currency",
            "重要性": "Importance",
            "事件": "Event",
            "实际值": "Actual",
            "预测值": "Forecast",
            "前值": "Previous"
        }

        standardized_data = []
        # 为每条记录添加星期信息
        for row in data:
            new_row = {}
            for key, value in row.items():
                standardized_key = column_mapping.get(key, key)
                new_row[standardized_key] = value
                
            # 如果有日期字段，计算并添加星期字段
            if "Date" in new_row:
                try:
                    date_obj = datetime.strptime(new_row["Date"], "%Y-%m-%d")
                    weekday_mapping = {
                        0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 
                        4: "星期五", 5: "星期六", 6: "星期日"
                    }
                    new_row["Weekday"] = weekday_mapping[date_obj.weekday()]
                except Exception as e:
                    logger.error(f"计算星期失败: {e}")
                    new_row["Weekday"] = ""
            
            standardized_data.append(new_row)

        data = standardized_data

        # 确保列顺序与参考文件一致
        fieldnames = ["Date", "Weekday", "Time", "Currency", "Importance", "Event", "Actual", "Forecast", "Previous"]

        # 写入 CSV
        encoding = OmegaConf.select(config, "economic_calendar.export.csv_encoding", default="utf-8")
        with open(filepath, "w", newline="", encoding=encoding) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"数据已成功保存为CSV文件（列名已标准化）：{filepath}")
    except KeyError as e:
        logger.error(f"访问 CSV 保存配置时出错，缺少键: {e}")
    except IOError as e:
        logger.error(f"写入 CSV 文件时出错: {e}")
    except Exception as e:
        logger.error(f"保存 CSV 时发生未知错误: {e}", exc_info=True)

async def scrape_investing_calendar(url: str, config: DictConfig) -> List[Dict[str, Any]]:
    """使用 Playwright 异步抓取 Investing.com 经济日历数据，参数来自配置。"""
    data = []
    pw_cfg = config.get('economic_calendar', {}).get('playwright', {}) # 获取 Playwright 配置
    
    # 设置更短的超时时间，便于调试
    timeout = 45 * 1000  # 增加到45秒
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

    print("===== 开始初始化 Playwright =====")
    logger.debug("准备启动Playwright浏览器")
    
    try:
        async with async_playwright() as p:
            print("===== Playwright 已初始化 =====")
            logger.debug("启动Chromium浏览器")
            
            # 设置更多浏览器参数绕过反爬虫检测
            browser = await p.chromium.launch(
                headless=False,  # 有头模式
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                ]
            )
            print("===== 浏览器已启动 =====")
            
            # 创建上下文，设置各种浏览器特性
            browser_context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                has_touch=False,
                java_script_enabled=True,
                is_mobile=False,
            )
            
            # 修改webdriver属性，隐藏自动化特征
            await browser_context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            """)
            
            page = await browser_context.new_page()
            
            try:
                logger.info(f"导航到 URL: {url} (超时: {timeout / 1000}秒)")
                print(f"===== 开始访问 {url} =====")
                
                await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                print("页面基本DOM加载完成")
                
                # 模拟随机人类行为
                await page.mouse.move(200, 300)  # 移动鼠标
                await page.mouse.wheel(delta_x=0, delta_y=300)  # 滚动页面
                await asyncio.sleep(1)  # 短暂等待
                await page.mouse.wheel(delta_x=0, delta_y=200)  # 再次滚动
                
                # 等待一些交互元素加载完成
                try:
                    # 尝试点击可能的cookie同意按钮
                    cookie_button = page.locator("button:has-text('Accept')").first
                    if await cookie_button.count() > 0:
                        await cookie_button.click()
                        print("已点击cookie接受按钮")
                except Exception as e:
                    print(f"处理cookie弹窗失败: {e}")
                
                # 确保页面完全加载
                await asyncio.sleep(5)
                print("页面加载完成，等待表格数据...")

                print("开始提取表格数据...")
                table_selector = "table#economicCalendarData"
                print(f"===== 等待表格元素 {table_selector} =====")
                # 增加等待时间
                await page.wait_for_selector(table_selector, state="visible", timeout=40000)
                print("表格已找到")
                
                # 额外等待确保表格内容完全加载
                await asyncio.sleep(2)

                # 使用 Playwright 定位器提取数据
                rows = page.locator(f"{table_selector} tbody tr.js-event-item")
                count = await rows.count()
                print(f"找到 {count} 行数据，开始遍历...")

                # --- 修改：获取脚本运行当天的日期 --- 
                today_date_str = datetime.now().strftime("%Y-%m-%d")

                for i in range(count):
                    print(f"处理第 {i+1}/{count} 行...")
                    row = rows.nth(i)
                    try:
                        # 提取各个单元格数据，增加超时并处理元素不存在或不可见的情况
                        time_text = await row.locator("td.first.left.time").inner_text(timeout=2000)

                        currency_element = row.locator("td.left.flagCur.noWrap")
                        currency_text = await currency_element.inner_text(timeout=2000) if await currency_element.count() > 0 else "N/A"

                        importance_element = row.locator("td.sentiment")
                        importance_title = "N/A"
                        importance_level = 0
                        if await importance_element.count() > 0:
                            importance_title = await importance_element.get_attribute("title", timeout=2000) or "N/A"
                            # 提取星星数量
                            importance_level = await importance_element.locator("i.grayFullBullishIcon").count()
                        
                        # --- 修改：移除重要性文本格式化，后面直接用 level ---

                        # 事件可能在 <a> 标签内或直接在 <td> 内
                        event_link = row.locator("td.left.event a")
                        if await event_link.count() > 0:
                            event_text = await event_link.inner_text(timeout=2000)
                        else:
                            event_text = await row.locator("td.left.event").inner_text(timeout=2000)

                        # 只保留原始事件文本，不做任何修改
                        event_text = event_text.strip()

                        # 提取实际值、预测值、前值
                        actual_text = await row.locator("td.act").inner_text(timeout=2000)
                        forecast_text = await row.locator("td.fore").inner_text(timeout=2000)
                        previous_text = await row.locator("td.prev").inner_text(timeout=2000)

                        # --- 修改：移除错误的 next_year 计算逻辑 ---

                        data.append({
                            "日期": today_date_str,  # 使用脚本运行当天的日期
                            "时间": time_text.strip(),
                            "货币": currency_text.strip(),
                            "重要性": importance_level, # 直接使用数字
                            "事件": event_text.strip(),
                            "实际值": actual_text.strip() if actual_text else "",
                            "预测值": forecast_text.strip() if forecast_text else "",
                            "前值": previous_text.strip() if previous_text else "",
                        })

                        if (i + 1) % 5 == 0:  # 每5行输出一次进度
                            print(f"已处理 {i+1}/{count} 行...")

                    except PlaywrightTimeoutError:
                        print(f"处理第 {i+1} 行时元素查找超时，跳过该行。")
                    except Exception as row_e:
                        print(f"处理第 {i+1} 行时发生错误: {row_e}")
                        # 可以选择记录错误行的数据或仅跳过
                        # print(f"错误行 HTML (部分): {await row.inner_html(timeout=1000)[:200]}")

                print(f"数据提取完成，共 {len(data)} 条。")

                # 直接使用提取的数据，不需要添加额外的日期字段
                if data:
                    print("开始将提取的数据保存到 CSV...")
                    save_to_csv(data, config=config) # 调用保存到 CSV
                else:
                    print("未提取到数据，跳过保存步骤。")
                # --- 保存步骤结束 ---

            except PlaywrightTimeoutError:
                logger.error(f"导航到 {url} 超时 ({timeout / 1000} 秒)")
                print(f"===== 访问 {url} 超时 =====")
                
                # 尝试保存页面截图和源代码以便调试
                try:
                    print("保存页面截图和源代码以便调试...")
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = f"debug_screenshot_{timestamp}.png"
                    await page.screenshot(path=screenshot_path)
                    print(f"已保存页面截图: {screenshot_path}")
                    
                    html_path = f"debug_source_{timestamp}.html"
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    print(f"已保存页面源代码: {html_path}")
                except Exception as e:
                    print(f"保存调试信息失败: {e}")
                    
            except Exception as e:
                logger.error(f"Playwright 操作失败: {e}", exc_info=True)
                print(f"===== 操作失败: {e} =====")
            finally:
                print("关闭浏览器资源...")
                await browser.close()
                print("抓取函数执行完毕。")

    except Exception as outer_e:
        logger.error(f"Playwright初始化失败: {outer_e}", exc_info=True)
        print(f"===== Playwright初始化失败: {outer_e} =====")

    return data

async def main():
    """主入口点，加载配置并执行抓取和保存"""
    config = load_app_config("economic_calendar/config/processing.yaml")
    if not config:
        logger.error("无法加载应用配置，脚本终止。")
        sys.exit(1)
    logger.info("应用配置加载成功。")

    # 从配置获取 URL，提供默认值
    target_url = OmegaConf.select(config, "economic_calendar.download.target_url", default="https://cn.investing.com/economic-calendar/")
    logger.info(f"目标 URL: {target_url}")

    # 确保原始数据目录存在
    raw_live_dir = get_absolute_path(config, "economic_calendar.paths.raw_live_dir")
    if raw_live_dir:
        os.makedirs(raw_live_dir, exist_ok=True)
        logger.info(f"确保原始数据目录存在: {raw_live_dir}")

    extracted_data = await scrape_investing_calendar(target_url, config) # 传递 config

    if extracted_data:
        # 保存到 CSV
        save_to_csv(extracted_data, config=config)
    else:
        logger.warning("未能提取到任何数据。")

if __name__ == "__main__":
    # 注意：如果 main() 内部加载配置后会重新配置日志，这里的配置会被覆盖
    print("===== 脚本开始执行 =====")
    asyncio.run(main())
    print("===== 脚本执行结束 =====")
