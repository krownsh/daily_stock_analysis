# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 備用資料來源 1 (Priority 2)
===================================

數據來源：Tushare Pro API（挖地兔）
特點：需要 Token、有請求配額限制
優點：數據質量高、介面穩定

流控策略：
1. 實現"每分鐘調用計數器"
2. 超過免費配額（80次/分）時，強制休眠到下一分鐘
3. 使用 tenacity 實現指數退避重試
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS
from src.config import get_config
import os

logger = logging.getLogger(__name__)


def _is_us_code(stock_code: str) -> bool:
    """
    判斷代碼是否為美股
    
    美股代碼規則：
    - 1-5個大寫字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro 資料來源實現
    
    優先級：2
    數據來源：Tushare Pro API
    
    關鍵策略：
    - 每分鐘調用計數器，防止超出配額
    - 超過 80 次/分鐘時強制等待
    - 失敗後指數退避重試
    
    配額說明（Tushare 免費用戶）：
    - 每分鐘最多 80 次請求
    - 每天最多 500 次請求
    """
    
    name = "TushareFetcher"
    priority = int(os.getenv("TUSHARE_PRIORITY", "2"))  # 預設優先級，會在 __init__ 中根據配置動態調整

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        初始化 TushareFetcher

        Args:
            rate_limit_per_minute: 每分鐘最大請求數（預設80，Tushare免額度）
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self._call_count = 0  # 當前分鐘內的調用次數
        self._minute_start: Optional[float] = None  # 當前計數週期開始時間
        self._api: Optional[object] = None  # Tushare API 實例

        # 嘗試初始化 API
        self._init_api()

        # 根據 API 初始化結果動態調整優先級
        self.priority = self._determine_priority()
    
    def _init_api(self) -> None:
        """
        初始化 Tushare API
        
        如果 Token 未配置，此資料來源將不可用
        """
        config = get_config()
        
        if not config.tushare_token:
            logger.warning("Tushare Token 未配置，此資料來源不可用")
            return
        
        try:
            import tushare as ts
            
            # 設置 Token
            ts.set_token(config.tushare_token)
            
            # 獲取 API 實例
            self._api = ts.pro_api()
            
            logger.info("Tushare API 初始化成功")
            
        except Exception as e:
            logger.error(f"Tushare API 初始化失敗: {e}")
            self._api = None

    def _determine_priority(self) -> int:
        """
        根據 Token 配置和 API 初始化狀態確定優先級

        策略：
        - Token 配置且 API 初始化成功：優先級 -1（絕對最高，優於 efinance）
        - 其他情況：優先級 2（預設）

        Returns:
            優先級數字（0=最高，數字越大優先級越低）
        """
        config = get_config()

        if config.tushare_token and self._api is not None:
            # Token 配置且 API 初始化成功，提升為最高優先級
            logger.info("✅ 檢測到 TUSHARE_TOKEN 且 API 初始化成功，Tushare 資料來源優先級提升為最高 (Priority -1)")
            return -1

        # Token 未配置或 API 初始化失敗，保持預設優先級
        return 2

    def is_available(self) -> bool:
        """
        檢查資料來源是否可用

        Returns:
            True 表示可用，False 表示不可用
        """
        return self._api is not None

    def _check_rate_limit(self) -> None:
        """
        檢查並執行速率限制
        
        流控策略：
        1. 檢查是否進入新的一分鐘
        2. 如果是，重置計數器
        3. 如果當前分鐘調用次數超過限制，強制休眠
        """
        current_time = time.time()
        
        # 檢查是否需要重置計數器（新的一分鐘）
        if self._minute_start is None:
            self._minute_start = current_time
            self._call_count = 0
        elif current_time - self._minute_start >= 60:
            # 已經過了一分鐘，重置計數器
            self._minute_start = current_time
            self._call_count = 0
            logger.debug("速率限制計數器已重置")
        
        # 檢查是否超過配額
        if self._call_count >= self.rate_limit_per_minute:
            # 計算需要等待的時間（到下一分鐘）
            elapsed = current_time - self._minute_start
            sleep_time = max(0, 60 - elapsed) + 1  # +1 秒緩衝
            
            logger.warning(
                f"Tushare 達到速率限制 ({self._call_count}/{self.rate_limit_per_minute} 次/分鐘)，"
                f"等待 {sleep_time:.1f} 秒..."
            )
            
            time.sleep(sleep_time)
            
            # 重置計數器
            self._minute_start = time.time()
            self._call_count = 0
        
        # 增加調用計數
        self._call_count += 1
        logger.debug(f"Tushare 當前分鐘調用次數: {self._call_count}/{self.rate_limit_per_minute}")
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        轉換股票代碼為 Tushare 格式
        
        Tushare 要求的格式：
        - 滬市：600519.SH
        - 深市：000001.SZ
        
        Args:
            stock_code: 原始代碼，如 '600519', '000001'
            
        Returns:
            Tushare 格式代碼，如 '600519.SH', '000001.SZ'
        """
        code = stock_code.strip()
        
        # 已經包含後綴的情況
        if '.' in code:
            return code.upper()
        
        # 根據代碼前綴判斷市場
        # 滬市：600xxx, 601xxx, 603xxx, 688xxx (科創板)
        # 深市：000xxx, 002xxx, 300xxx (創業板)
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SH"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            # 預設嘗試深市
            logger.warning(f"無法確定股票 {code} 的市場，預設使用深市")
            return f"{code}.SZ"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 Tushare 獲取原始數據
        
        使用 daily() 介面獲取日線數據
        
        流程：
        1. 檢查 API 是否可用
        2. 檢查是否為美股（不支援）
        3. 執行速率限制檢查
        4. 轉換股票代碼格式
        5. 調用 API 獲取數據
        """
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，請檢查 Token 配置")
        
        # 美股不支援，拋出異常讓 DataFetcherManager 切換到其他資料來源
        if _is_us_code(stock_code):
            raise DataFetchError(f"TushareFetcher 不支援美股 {stock_code}，請使用 AkshareFetcher 或 YfinanceFetcher")
        
        # 速率限制檢查
        self._check_rate_limit()
        
        # 轉換代碼格式
        ts_code = self._convert_stock_code(stock_code)
        
        # 轉換日期格式（Tushare 要求 YYYYMMDD）
        ts_start = start_date.replace('-', '')
        ts_end = end_date.replace('-', '')
        
        logger.debug(f"調用 Tushare daily({ts_code}, {ts_start}, {ts_end})")
        
        try:
            # 調用 daily 介面獲取日線數據
            df = self._api.daily(
                ts_code=ts_code,
                start_date=ts_start,
                end_date=ts_end,
            )
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測配額超限
            if any(keyword in error_msg for keyword in ['quota', '配額', 'limit', '權限']):
                logger.warning(f"Tushare 配額可能超限: {e}")
                raise RateLimitError(f"Tushare 配額超限: {e}") from e
            
            raise DataFetchError(f"Tushare 獲取數據失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 Tushare 數據
        
        Tushare daily 返回的列名：
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        需要映射到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名映射
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
            # open, high, low, close, amount, pct_chg 列名相同
        }
        
        df = df.rename(columns=column_mapping)
        
        # 轉換日期格式（YYYYMMDD -> YYYY-MM-DD）
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        
        # 成交量單位轉換（Tushare 的 vol 單位是手，需要轉換為股）
        if 'volume' in df.columns:
            df['volume'] = df['volume'] * 100
        
        # 成交額單位轉換（Tushare 的 amount 單位是千元，轉換為元）
        if 'amount' in df.columns:
            df['amount'] = df['amount'] * 1000
        
        # 添加股票代碼列
        df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        獲取股票名稱
        
        使用 Tushare 的 stock_basic 介面獲取股票基本訊息
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票名稱，失敗返回 None
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，無法獲取股票名稱")
            return None
        
        # 檢查快取
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 初始化快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            # 速率限制檢查
            self._check_rate_limit()
            
            # 轉換代碼格式
            ts_code = self._convert_stock_code(stock_code)
            
            # 調用 stock_basic 介面
            df = self._api.stock_basic(
                ts_code=ts_code,
                fields='ts_code,name'
            )
            
            if df is not None and not df.empty:
                name = df.iloc[0]['name']
                self._stock_name_cache[stock_code] = name
                logger.debug(f"Tushare 獲取股票名稱成功: {stock_code} -> {name}")
                return name
            
        except Exception as e:
            logger.warning(f"Tushare 獲取股票名稱失敗 {stock_code}: {e}")
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        獲取股票列表
        
        使用 Tushare 的 stock_basic 介面獲取全部股票列表
        
        Returns:
            包含 code, name 列的 DataFrame，失敗返回 None
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，無法獲取股票列表")
            return None
        
        try:
            # 速率限制檢查
            self._check_rate_limit()
            
            # 調用 stock_basic 介面獲取所有股票
            df = self._api.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,name,industry,area,market'
            )
            
            if df is not None and not df.empty:
                # 轉換 ts_code 為標準代碼格式
                df['code'] = df['ts_code'].apply(lambda x: x.split('.')[0])
                
                # 更新快取
                if not hasattr(self, '_stock_name_cache'):
                    self._stock_name_cache = {}
                for _, row in df.iterrows():
                    self._stock_name_cache[row['code']] = row['name']
                
                logger.info(f"Tushare 獲取股票列表成功: {len(df)} 條")
                return df[['code', 'name', 'industry', 'area', 'market']]
            
        except Exception as e:
            logger.warning(f"Tushare 獲取股票列表失敗: {e}")
        
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[dict]:
        """
        獲取即時行情

        策略：
        1. 優先嘗試 Pro 介面（需要2000積分）：數據全，穩定性高
        2. 失敗降級到舊版介面：門檻低，數據較少

        Args:
            stock_code: 股票代碼

        Returns:
            UnifiedRealtimeQuote 物件，失敗返回 None
        """
        if self._api is None:
            return None

        from .realtime_types import (
            UnifiedRealtimeQuote, RealtimeSource,
            safe_float, safe_int
        )

        # 速率限制檢查
        self._check_rate_limit()

        # 嘗試 Pro 介面
        try:
            ts_code = self._convert_stock_code(stock_code)
            # 嘗試調用 Pro 即時介面 (需要積分)
            df = self._api.quotation(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                logger.debug(f"Tushare Pro 即時行情獲取成功: {stock_code}")

                return UnifiedRealtimeQuote(
                    code=stock_code,
                    name=str(row.get('name', '')),
                    source=RealtimeSource.TUSHARE,
                    price=safe_float(row.get('price')),
                    change_pct=safe_float(row.get('pct_chg')),  # Pro 介面通常直接返回漲跌幅
                    change_amount=safe_float(row.get('change')),
                    volume=safe_int(row.get('vol')),
                    amount=safe_float(row.get('amount')),
                    high=safe_float(row.get('high')),
                    low=safe_float(row.get('low')),
                    open_price=safe_float(row.get('open')),
                    pre_close=safe_float(row.get('pre_close')),
                    turnover_rate=safe_float(row.get('turnover_ratio')), # Pro 介面可能有換手率
                    pe_ratio=safe_float(row.get('pe')),
                    pb_ratio=safe_float(row.get('pb')),
                    total_mv=safe_float(row.get('total_mv')),
                )
        except Exception as e:
            # 僅記錄調試日誌，不報錯，繼續嘗試降級
            logger.debug(f"Tushare Pro 即時行情不可用 (可能是積分不足): {e}")

        # 降級：嘗試舊版介面
        try:
            import tushare as ts

            # Tushare 舊版介面使用 6 位代碼
            code_6 = stock_code.split('.')[0] if '.' in stock_code else stock_code

            # 特殊處理指數代碼：舊版介面需要前綴 (sh000001, sz399001)
            # 簡單的指數判斷邏輯
            if code_6 == '000001':  # 上證指數
                symbol = 'sh000001'
            elif code_6 == '399001': # 深證成指
                symbol = 'sz399001'
            elif code_6 == '399006': # 創業板指
                symbol = 'sz399006'
            elif code_6 == '000300': # 滬深300
                symbol = 'sh000300'
            else:
                symbol = code_6

            # 調用舊版即時介面 (ts.get_realtime_quotes)
            df = ts.get_realtime_quotes(symbol)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # 計算漲跌幅
            price = safe_float(row['price'])
            pre_close = safe_float(row['pre_close'])
            change_pct = 0.0
            change_amount = 0.0

            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100

            # 構建統一物件
            return UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row['name']),
                source=RealtimeSource.TUSHARE,
                price=price,
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=safe_int(row['volume']) // 100,  # 轉換為手
                amount=safe_float(row['amount']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                open_price=safe_float(row['open']),
                pre_close=pre_close,
            )

        except Exception as e:
            logger.warning(f"Tushare (舊版) 獲取即時行情失敗 {stock_code}: {e}")
            return None

    def get_main_indices(self) -> Optional[List[dict]]:
        """
        獲取主要指數即時行情 (Tushare Pro)
        """
        if self._api is None:
            return None

        from .realtime_types import safe_float

        # 指數映射：Tushare代碼 -> 名稱
        indices_map = {
            '000001.SH': '上證指數',
            '399001.SZ': '深證成指',
            '399006.SZ': '創業板指',
            '000688.SH': '科創50',
            '000016.SH': '上證50',
            '000300.SH': '滬深300',
        }

        try:
            self._check_rate_limit()

            # Tushare index_daily 獲取歷史數據，即時數據需用其他介面或估算
            # 由於 Tushare 免費用戶可能無法獲取指數即時行情，這裡作為備選
            # 使用 index_daily 獲取最近交易日數據

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - pd.Timedelta(days=5)).strftime('%Y%m%d')

            results = []

            # 批量獲取所有指數數據
            for ts_code, name in indices_map.items():
                try:
                    df = self._api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        row = df.iloc[0] # 最新一天

                        current = safe_float(row['close'])
                        prev_close = safe_float(row['pre_close'])

                        results.append({
                            'code': ts_code.split('.')[0], # 兼容 sh000001 格式需轉換，這裡保持純數字
                            'name': name,
                            'current': current,
                            'change': safe_float(row['change']),
                            'change_pct': safe_float(row['pct_chg']),
                            'open': safe_float(row['open']),
                            'high': safe_float(row['high']),
                            'low': safe_float(row['low']),
                            'prev_close': prev_close,
                            'volume': safe_float(row['vol']),
                            'amount': safe_float(row['amount']) * 1000, # 千元轉元
                            'amplitude': 0.0 # Tushare index_daily 不直接返回振幅
                        })
                except Exception as e:
                    logger.debug(f"Tushare 獲取指數 {name} 失敗: {e}")
                    continue

            if results:
                return results
            else:
                logger.warning("[Tushare] 未獲取到指數行情數據")

        except Exception as e:
            logger.error(f"[Tushare] 獲取指數行情失敗: {e}")

        return None

    def get_market_stats(self) -> Optional[dict]:
        """
        獲取市場漲跌統計 (Tushare Pro)
        """
        if self._api is None:
            return None

        try:
            self._check_rate_limit()

            # 獲取最近交易日 (獲取過去20天，確保有足夠歷史)
            start_date = (datetime.now() - pd.Timedelta(days=20)).strftime('%Y%m%d')
            trade_cal = self._api.trade_cal(exchange='', start_date=start_date, end_date=datetime.now().strftime('%Y%m%d'), is_open='1')

            if trade_cal is None or trade_cal.empty:
                return None

            # 確保按日期升序排列 (Tushare有時返回降序)
            trade_cal = trade_cal.sort_values('cal_date')

            # 嘗試獲取最新一天的數據
            last_date = trade_cal.iloc[-1]['cal_date']
            logger.info(f"[Tushare] Calendar suggests last trading date: {last_date}")

            # 注意：每日指標介面 daily 可能數據量較大
            # 如果是在盤中調用，當天的數據可能還未生成，導致返回空或極少數據
            df = self._api.daily(trade_date=last_date)

            current_len = len(df) if df is not None else 0
            logger.info(f"[Tushare] Initial fetch for {last_date} returned {current_len} records")

            # 如果數據過少（<100條），說明當天數據未就緒，嘗試使用前一交易日
            if df is None or len(df) < 100:
                if len(trade_cal) > 1:
                    prev_date = trade_cal.iloc[-2]['cal_date']
                    logger.warning(f"Data for {last_date} is incomplete (count={current_len}), falling back to {prev_date}")
                    last_date = prev_date
                    df = self._api.daily(trade_date=last_date)
                else:
                    logger.warning(f"[Tushare] {last_date} 數據不足且無可用歷史交易日")

            logger.info(f"Calculating stats using data from date: {last_date}")

            if df is not None and not df.empty:
                logger.info(f"[Tushare] 使用交易日 {last_date} 進行市場統計分析")
                up_count = len(df[df['pct_chg'] > 0])
                down_count = len(df[df['pct_chg'] < 0])
                flat_count = len(df[df['pct_chg'] == 0])

                # 漲停跌停估算 (9.9%閾值)
                limit_up = len(df[df['pct_chg'] >= 9.9])
                limit_down = len(df[df['pct_chg'] <= -9.9])

                total_amount = df['amount'].sum() * 1000 / 1e8 # 千元 -> 元 -> 億元

                return {
                    'up_count': up_count,
                    'down_count': down_count,
                    'flat_count': flat_count,
                    'limit_up_count': limit_up,
                    'limit_down_count': limit_down,
                    'total_amount': total_amount
                }
            else:
                logger.warning("[Tushare] 獲取市場統計數據為空")

        except Exception as e:
            logger.error(f"[Tushare] 獲取市場統計失敗: {e}")

        return None

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[list, list]]:
        """
        獲取板塊漲跌榜 (Tushare Pro)
        """
        # Tushare 獲取板塊數據較複雜，暫時返回 None，讓 AkShare 處理
        return None


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = TushareFetcher()
    
    try:
        # 測試歷史數據
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"獲取成功，共 {len(df)} 條數據")
        print(df.tail())
        
        # 測試股票名稱
        name = fetcher.get_stock_name('600519')
        print(f"股票名稱: {name}")
        
    except Exception as e:
        print(f"獲取失敗: {e}")
