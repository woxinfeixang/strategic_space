import pandas as pd
import os
import logging
from functools import lru_cache
import pytz # 确保导入 pytz

# 配置日志记录器
logger = logging.getLogger(__name__)

class HistoricalDataProvider:
    """
    从本地 CSV 文件加载和提供历史市场数据。
    """
    def __init__(self, data_root_dir="data/historical"):
        """
        初始化 HistoricalDataProvider。

        Args:
            data_root_dir (str): 存放历史数据的根目录。
                                 预期结构: data_root_dir/{SYMBOL}/{SYMBOL}_{TIMEFRAME}.csv
        """
        self.data_root_dir = data_root_dir
        if not os.path.isdir(self.data_root_dir):
            logger.error(f"指定的历史数据根目录不存在: {self.data_root_dir}")
            raise FileNotFoundError(f"历史数据根目录未找到: {self.data_root_dir}")
        logger.info(f"HistoricalDataProvider 初始化，数据根目录: {self.data_root_dir}")

    @lru_cache(maxsize=128) # 缓存已加载的数据文件以提高效率
    def _load_data(self, symbol, timeframe):
        """
        (内部方法) 加载指定品种和时间周期的数据。
        使用 LRU 缓存避免重复加载。

        Args:
            symbol (str): 交易品种 (例如 'EURUSD')。
            timeframe (str): 时间周期 (例如 'M30', 'H1')。

        Returns:
            pd.DataFrame: 包含 OHLCV 数据的 DataFrame，索引为 UTC 时间戳。
                          如果文件不存在或加载失败则返回 None。
        """
        file_path = os.path.join(self.data_root_dir, symbol.upper(), f"{symbol.upper()}_{timeframe.lower()}.csv")
        logger.debug(f"尝试加载历史数据文件: {file_path}")

        if not os.path.exists(file_path):
            logger.warning(f"历史数据文件未找到: {file_path}")
            return None

        try:
            # 假设 CSV 文件中的时间列名为 'time' 或 'timestamp'
            # 并且时间格式是可被 pandas 识别的 (例如 'YYYY-MM-DD HH:MM:SS')
            # 重要：需要根据实际 CSV 文件确定时间列名和格式
            # 假设第一列是时间戳
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)

            # 检查索引是否为 DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                logger.error(f"文件 {file_path} 的索引未能成功解析为日期时间。请检查 CSV 格式或时间列。")
                # 尝试手动转换常见列名
                common_time_cols = ['time', 'timestamp', 'datetime', 'Date Time']
                time_col_found = None
                for col in common_time_cols:
                    if col in df.columns:
                        try:
                            df.index = pd.to_datetime(df[col], errors='coerce')
                            df = df.drop(columns=[col]) # 移除原来的时间列
                            if isinstance(df.index, pd.DatetimeIndex):
                                time_col_found = col
                                logger.info(f"使用列 '{col}' 作为时间索引成功转换。")
                                break
                        except Exception as e_conv:
                            logger.warning(f"尝试使用列 '{col}' 作为时间索引转换失败: {e_conv}")
                if not time_col_found:
                     logger.error(f"在 {file_path} 中找不到或无法转换合适的时间列作为索引。")
                     return None


            # --- 时区处理 ---
            # 1. 如果索引没有时区信息 (naive)，假设它是 UTC 或特定时区 (需要配置或约定)
            if df.index.tz is None:
                logger.warning(f"文件 {file_path} 的时间戳索引缺少时区信息。假设为 UTC 并进行本地化。")
                try:
                    df = df.tz_localize('UTC')
                except Exception as e_tz:
                    logger.error(f"将 {file_path} 的时间索引本地化为 UTC 时出错: {e_tz}。请确保数据时间戳是唯一的。")
                    return None
            # 2. 如果索引已有其他时区，统一转换为 UTC
            elif df.index.tz != pytz.UTC:
                logger.info(f"文件 {file_path} 的时间戳时区为 {df.index.tz}，将转换为 UTC。")
                try:
                    df = df.tz_convert('UTC')
                except Exception as e_conv_tz:
                    logger.error(f"将 {file_path} 的时间索引从 {df.index.tz} 转换为 UTC 时出错: {e_conv_tz}")
                    return None

            # 确保数据按时间升序排列
            df = df.sort_index()

            # 重命名列以匹配常用约定 (ohlc 或 OHLC) - 可选
            # 假设原始列名可能是 'Open', 'High', 'Low', 'Close', 'Volume'
            rename_map = {
                'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
                'Tick Volume': 'volume', 'Volume': 'volume', # 根据实际情况调整
                # 添加其他可能的列名映射
            }
            # 只重命名存在的列
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            logger.info(f"成功加载并处理了 {len(df)} 条数据从 {file_path}")
            return df

        except Exception as e:
            logger.error(f"加载或处理文件 {file_path} 时发生错误: {e}", exc_info=True)
            return None

    def get_historical_data(self, symbol, start_time, bars, timeframe):
        """
        获取指定时间点之后的一定数量的历史 K 线数据。

        Args:
            symbol (str): 交易品种。
            start_time (pd.Timestamp): 数据获取的起始时间点 (应为 timezone-aware, UTC)。
            bars (int): 需要获取的 K 线数量。
            timeframe (str): 时间周期 (例如 'M30')。

        Returns:
            pd.DataFrame: 包含所需 K 线数据的 DataFrame 切片，索引为 UTC 时间戳。
                          如果无法获取数据则返回 None 或空 DataFrame。
        """
        df = self._load_data(symbol, timeframe)
        if df is None or df.empty:
            return pd.DataFrame() # 返回空 DataFrame

        # 确保 start_time 是 timezone-aware (UTC)
        if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) is None:
             logger.warning(f"get_historical_data 接收到的 start_time ({start_time}) 缺少时区信息，将假设为 UTC。")
             start_time = start_time.tz_localize('UTC')
        elif start_time.tzinfo != pytz.UTC:
             start_time = start_time.tz_convert('UTC')


        # 查找 start_time 在索引中的位置或之后的位置
        # 'right' 包含 start_time 本身 (如果精确匹配)
        # 'left'  则不包含 start_time，取其后的第一个
        # 我们需要 start_time 之后的 N 根 K 线
        try:
            # 使用 searchsorted 找到插入位置
            start_idx = df.index.searchsorted(start_time, side='left') # 'left' 找到第一个 >= start_time 的位置

            # 确保索引有效
            if start_idx >= len(df.index):
                 logger.warning(f"请求的 start_time ({start_time}) 在 {symbol} {timeframe} 数据范围之后。")
                 return pd.DataFrame()

            # 计算结束索引
            end_idx = start_idx + bars

            # 获取数据切片 (注意 pandas 切片是 end_idx 不包含在内)
            data_slice = df.iloc[start_idx:end_idx]

            # 验证获取的数据量 (可能因为数据末尾不足 bars)
            if len(data_slice) < bars:
                logger.warning(f"获取 {symbol} {timeframe} 数据从 {start_time} 开始的 {bars} 根K线时，实际只获得 {len(data_slice)} 根 (可能已到数据末尾)。")

            return data_slice

        except Exception as e:
             logger.error(f"在为 {symbol} {timeframe} 从 {start_time} 提取 {bars} 根数据时出错: {e}", exc_info=True)
             return pd.DataFrame()


    def get_full_data(self, symbol, timeframe):
         """
         获取指定品种和周期的全部历史数据。

         Args:
             symbol (str): 交易品种。
             timeframe (str): 时间周期。

         Returns:
             pd.DataFrame: 完整的历史数据 DataFrame，索引为 UTC 时间戳。
                           如果无法获取数据则返回 None 或空 DataFrame。
         """
         df = self._load_data(symbol, timeframe)
         return df if df is not None else pd.DataFrame()

    def iter_bars(self, symbol, timeframe):
        """
        提供一个迭代器，逐根返回历史 K 线数据 (以字典形式)。

        Args:
            symbol (str): 交易品种。
            timeframe (str): 时间周期。

        Yields:
            dict: 包含单根 K 线数据的字典 (例如 {'time': Timestamp, 'open': float, ...})。
        """
        df = self._load_data(symbol, timeframe)
        if df is not None and not df.empty:
            required_cols = {'open', 'high', 'low', 'close'}
            if not required_cols.issubset(df.columns):
                 logger.error(f"数据文件 {symbol}_{timeframe}.csv 缺少必要列 (需要 'open', 'high', 'low', 'close')，无法迭代 K 线。")
                 return # 或者 raise Error

            # 转换为字典列表进行迭代，这样更通用
            # df.iterrows() 效率较低，但对于典型回测数据量通常可接受
            for timestamp, row in df.iterrows():
                 bar_data = row.to_dict()
                 bar_data['time'] = timestamp # 确保时间戳在字典中且键名为 'time'
                 # 可以选择性地移除 NaN 值，如果需要
                 # bar_data = {k: v for k, v in bar_data.items() if pd.notna(v)}
                 yield bar_data
        else:
            logger.warning(f"无法为 {symbol} {timeframe} 提供 K 线迭代器，数据加载失败或为空。")
            # 确保即使没有数据，调用者也能迭代一个空序列
            return # 等同于 yield from []

class MT5DataProvider(HistoricalDataProvider):
    """MT5历史数据提供器实现"""
    def __init__(self, data_root_dir="data/mt5_historical"):
        super().__init__(data_root_dir)
        self.data_format = {
            'time': 'datetime64[ns]',
            'open': 'float64',
            'high': 'float64', 
            'low': 'float64',
            'close': 'float64',
            'volume': 'int64'
        }

    def _load_data(self, symbol, timeframe):
        """重写加载方法处理MT5数据格式"""
        df = super()._load_data(symbol, timeframe)
        if df is not None:
            # MT5数据特定处理逻辑
            df = df.rename(columns={
                'Time': 'time',
                'Open': 'open',
                'High': 'high',
                'Low': 'low', 
                'Close': 'close',
                'Volume': 'volume'
            })
        return df

# --- 示例用法 ---
if __name__ == '__main__':
    # 配置基本日志以便在直接运行时看到输出
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 实例化 Provider
    try:
        provider = HistoricalDataProvider(data_root_dir='../data/historical') # 假设从 data 目录外运行
    except FileNotFoundError:
         logger.warning("在示例用法中，未找到 '../data/historical' 目录，尝试当前目录下的 'data/historical'")
         try:
             provider = HistoricalDataProvider(data_root_dir='data/historical')
         except FileNotFoundError as e:
             logger.error(f"无法初始化 HistoricalDataProvider: {e}")
             provider = None

    if provider:
        # 示例 1: 获取 EURUSD M30 的完整数据
        print("\n--- 示例 1: 获取 EURUSD M30 完整数据 ---")
        eurusd_m30 = provider.get_full_data('EURUSD', 'M30')
        if not eurusd_m30.empty:
            print(f"成功加载 EURUSD M30 数据 {eurusd_m30.shape[0]} 行。")
            print("数据前 5 行:")
            print(eurusd_m30.head())
            print("\n数据后 5 行:")
            print(eurusd_m30.tail())
            print(f"时间索引时区: {eurusd_m30.index.tz}")
        else:
            print("未能加载 EURUSD M30 数据。")

        # 示例 2: 获取特定时间点后的 K 线数据
        print("\n--- 示例 2: 获取特定时间点后的 K 线 ---")
        # 构造一个带时区的 UTC 时间戳
        start_dt = pd.Timestamp('2023-10-26 10:00:00', tz='UTC')
        bars_to_get = 5
        eurusd_slice = provider.get_historical_data('EURUSD', start_dt, bars=bars_to_get, timeframe='M30')
        if not eurusd_slice.empty:
             print(f"成功获取 EURUSD M30 从 {start_dt} 开始的 {len(eurusd_slice)} 根 K 线 (请求 {bars_to_get}):")
             print(eurusd_slice)
        else:
             print(f"未能获取 EURUSD M30 从 {start_dt} 开始的 {bars_to_get} 根 K 线。")


        # 示例 3: 迭代 K 线
        print("\n--- 示例 3: 迭代 GBPUSD M30 K 线 (前 3 根) ---")
        count = 0
        try:
             for bar in provider.iter_bars('GBPUSD', 'M30'):
                 print(bar)
                 count += 1
                 if count >= 3:
                     break
             if count == 0:
                  print("未能迭代 GBPUSD M30 K 线 (数据可能不存在或为空)。")
        except Exception as e_iter:
             print(f"迭代 GBPUSD M30 时出错: {e_iter}")

        # 示例 4: 测试文件不存在的情况
        print("\n--- 示例 4: 测试不存在的品种/周期 ---")
        non_existent = provider.get_full_data('XYZABC', 'H4')
        if non_existent.empty:
            print("成功处理不存在的数据情况 (返回空 DataFrame)。")
        else:
            print("错误：对于不存在的数据，未按预期返回空 DataFrame。")
