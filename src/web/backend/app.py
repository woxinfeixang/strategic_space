import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging # 添加 logging 导入

# 配置 Jinja2 日志级别以抑制 DEBUG 输出
logging.getLogger('jinja2').setLevel(logging.INFO) # 设置 jinja2 logger 级别

# 将项目根目录添加到 sys.path
# E:/Programming/strategic_space/src/web/backend -> E:/Programming/strategic_space/src/web -> E:/Programming/strategic_space/src -> E:/Programming/strategic_space
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# --- 假设的导入 ---
# TODO: 根据实际模块结构和函数名称调整这些导入
try:
    # 假设 economic_calendar 模块下有 provider.py 包含 get_economic_events 函数
    from src.economic_calendar.provider import get_economic_events
except ImportError:
    print("WARN: Could not import get_economic_events from src.economic_calendar.provider")
    async def get_economic_events(*args, **kwargs): # Placeholder
        return [{"event": "Placeholder Event", "time": "Now", "importance": "High"}]

try:
    # 假设 market_price_data 模块下有 provider.py 包含 get_market_prices 函数
    from src.market_price_data.provider import get_market_prices
except ImportError:
    print("WARN: Could not import get_market_prices from src.market_price_data.provider")
    async def get_market_prices(symbol: str, *args, **kwargs): # Placeholder
        return [{"time": "Now", "price": 100.0, "symbol": symbol}]
# --- 结束假设的导入 ---

app = FastAPI(title="Strategic Space Backend API")

# 配置 CORS
# 注意：在开发环境中允许所有源可能不安全，生产环境应配置具体允许的源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源访问 (开发方便，生产环境应收紧)
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有 HTTP 头
)

@app.get("/api/status")
async def get_status():
    """提供后端服务的状态。"""
    return {"status": "running", "message": "Backend is operational"}

# --- 新增 API 端点 ---

@app.get("/api/economic-events")
async def fetch_economic_events(date_from: str | None = None, date_to: str | None = None, importance: int | None = None):
    """
    获取财经日历事件。
    可以通过查询参数进行过滤（可选）。
    """
    try:
        # TODO: 将查询参数传递给实际的 get_economic_events 函数
        events = await get_economic_events() # 使用假设的导入
        return {"data": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch economic events: {e}")

@app.get("/api/market-prices/{symbol}")
async def fetch_market_prices(symbol: str, timeframe: str | None = None, date_from: str | None = None, date_to: str | None = None):
    """
    获取指定交易品种的市场价格数据。
    可以通过查询参数指定时间范围和周期（可选）。
    """
    try:
        # TODO: 将查询参数传递给实际的 get_market_prices 函数
        prices = await get_market_prices(symbol=symbol) # 使用假设的导入
        if not prices:
            raise HTTPException(status_code=404, detail=f"Market prices not found for symbol: {symbol}")
        return {"data": prices}
    except HTTPException as http_exc:
        raise http_exc # 重新抛出已知的 HTTP 异常
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch market prices for {symbol}: {e}")

# --- 结束新增 API 端点 ---


# 如果直接运行此文件，则启动 uvicorn 服务器 (用于开发)
if __name__ == "__main__":
    import uvicorn
    # 运行在 0.0.0.0 上允许从网络访问，端口 5000 与前端代理一致
    # 注意：确保运行此脚本的终端位于 backend 目录，或者 Uvicorn 可以找到 'app:app'
    # 或者从项目根目录运行: uvicorn src.web.backend.app:app --reload
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True) # 推荐使用字符串 "app:app" 以支持 reload 