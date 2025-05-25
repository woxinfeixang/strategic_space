import MetaTrader5 as mt5
from datetime import datetime
import pytz

def check_historical_range():
    if not mt5.initialize():
        print("MT5初始化失败，错误代码:", mt5.last_error())
        return
    
    symbols = ["EURUSD", "XAUUSD", "GBPUSD"]
    timeframes = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1
    }

    print("MT5各周期最早可获取数据时间：")
    print("{:<6} {:<8} {:<25} {:<25}".format("周期", "品种", "最早时间(UTC+0)", "北京时间"))
    
    for tf_name, tf in timeframes.items():
        for symbol in symbols:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 1)
            if rates is not None and len(rates) > 0:
                utc_time = datetime.utcfromtimestamp(rates[0][0])
                beijing_time = utc_time.replace(tzinfo=pytz.utc).astimezone(pytz.timezone("Asia/Shanghai"))
                print("{:<6} {:<8} {:<25} {:<25}".format(
                    tf_name, 
                    symbol,
                    utc_time.strftime("%Y-%m-%d %H:%M:%S"),
                    beijing_time.strftime("%Y-%m-%d %H:%M:%S")
                ))
            else:
                print("{:<6} {:<8} 无可用数据".format(tf_name, symbol))
    
    mt5.shutdown()

if __name__ == "__main__":
    check_historical_range()
