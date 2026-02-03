# -*- coding: utf-8 -*-
"""
===================================
PytdxFetcher - 通達信資料來源 (Priority 2)
===================================

數據來源：通達信行情伺服器（pytdx 庫）
特點：免費、無需 Token、直連行情伺服器
優點：即時數據、穩定、無配額限制

關鍵策略：
1. 多伺服器自動切換
2. 連接逾時自動重連
3. 失敗後指數退避重試
"""

import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Generator, List, Tuple

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
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


class PytdxFetcher(BaseFetcher):
    """
    通達信資料來源實現
    
    優先級：2（與 Tushare 同級）
    數據來源：通達信行情伺服器
    
    關鍵策略：
    - 自動選擇最優伺服器
    - 連接失敗自動切換伺服器
    - 失敗後指數退避重試
    
    Pytdx 特點：
    - 免費、無需註冊
    - 直連行情伺服器
    - 支援即時行情和歷史數據
    - 支援股票名稱查詢
    """
    
    name = "PytdxFetcher"
    priority = int(os.getenv("PYTDX_PRIORITY", "2"))
    
    # 預設通達信行情伺服器列表
    DEFAULT_HOSTS = [
        ("119.147.212.81", 7709),  # 深圳
        ("112.74.214.43", 7727),   # 深圳
        ("221.231.141.60", 7709),  # 上海
        ("101.227.73.20", 7709),   # 上海
        ("101.227.77.254", 7709),  # 上海
        ("14.215.128.18", 7709),   # 廣州
        ("59.173.18.140", 7709),   # 武漢
        ("180.153.39.51", 7709),   # 杭州
    ]
    
    def __init__(self, hosts: Optional[List[Tuple[str, int]]] = None):
        """
        初始化 PytdxFetcher
        
        Args:
            hosts: 伺服器列表 [(host, port), ...]，預設使用內置列表
        """
        self._hosts = hosts or self.DEFAULT_HOSTS
        self._api = None
        self._connected = False
        self._current_host_idx = 0
        self._stock_list_cache = None  # 股票列表快取
        self._stock_name_cache = {}    # 股票名稱快取 {code: name}
    
    def _get_pytdx(self):
        """
        延遲加載 pytdx 模組
        
        只在首次使用時導入，避免未安裝時報錯
        """
        try:
            from pytdx.hq import TdxHq_API
            return TdxHq_API
        except ImportError:
            logger.warning("pytdx 未安裝，請運行: pip install pytdx")
            return None
    
    @contextmanager
    def _pytdx_session(self) -> Generator:
        """
        Pytdx 連接上下文管理器
        
        確保：
        1. 進入上下文時自動連接
        2. 退出上下文時自動斷開
        3. 異常時也能正確斷開
        
        使用示例：
            with self._pytdx_session() as api:
                # 在這裡執行數據查詢
        """
        TdxHq_API = self._get_pytdx()
        if TdxHq_API is None:
            raise DataFetchError("pytdx 庫未安裝")
        
        api = TdxHq_API()
        connected = False
        
        try:
            # 嘗試連接伺服器（自動選擇最優）
            for i in range(len(self._hosts)):
                host_idx = (self._current_host_idx + i) % len(self._hosts)
                host, port = self._hosts[host_idx]
                
                try:
                    if api.connect(host, port, time_out=5):
                        connected = True
                        self._current_host_idx = host_idx
                        logger.debug(f"Pytdx 連接成功: {host}:{port}")
                        break
                except Exception as e:
                    logger.debug(f"Pytdx 連接 {host}:{port} 失敗: {e}")
                    continue
            
            if not connected:
                raise DataFetchError("Pytdx 無法連接任何伺服器")
            
            yield api
            
        finally:
            # 確保斷開連接
            try:
                api.disconnect()
                logger.debug("Pytdx 連接已斷開")
            except Exception as e:
                logger.warning(f"Pytdx 斷開連接時出錯: {e}")
    
    def _get_market_code(self, stock_code: str) -> Tuple[int, str]:
        """
        根據股票代碼判斷市場
        
        Pytdx 市場代碼：
        - 0: 深圳
        - 1: 上海
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            (market, code) 元組
        """
        code = stock_code.strip()
        
        # 去除可能的前綴後綴
        code = code.replace('.SH', '').replace('.SZ', '')
        code = code.replace('.sh', '').replace('.sz', '')
        code = code.replace('sh', '').replace('sz', '')
        
        # 根據代碼前綴判斷市場
        # 上海：60xxxx, 68xxxx（科創板）
        # 深圳：00xxxx, 30xxxx（創業板）, 002xxx（中小板）
        if code.startswith(('60', '68')):
            return 1, code  # 上海
        else:
            return 0, code  # 深圳
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從通達信獲取原始數據
        
        使用 get_security_bars() 獲取日線數據
        
        流程：
        1. 檢查是否為美股（不支援）
        2. 使用上下文管理器管理連接
        3. 判斷市場代碼
        4. 調用 API 獲取 K 線數據
        """
        # 美股不支援，拋出異常讓 DataFetcherManager 切換到其他資料來源
        if _is_us_code(stock_code):
            raise DataFetchError(f"PytdxFetcher 不支援美股 {stock_code}，請使用 AkshareFetcher 或 YfinanceFetcher")
        
        market, code = self._get_market_code(stock_code)
        
        # 計算需要獲取的交易日數量（估算）
        from datetime import datetime as dt
        start_dt = dt.strptime(start_date, '%Y-%m-%d')
        end_dt = dt.strptime(end_date, '%Y-%m-%d')
        days = (end_dt - start_dt).days
        count = min(max(days * 5 // 7 + 10, 30), 800)  # 估算交易日，最大 800 條
        
        logger.debug(f"調用 Pytdx get_security_bars(market={market}, code={code}, count={count})")
        
        with self._pytdx_session() as api:
            try:
                # 獲取日 K 線數據
                # category: 9-日線, 0-5分鐘, 1-15分鐘, 2-30分鐘, 3-1小時
                data = api.get_security_bars(
                    category=9,  # 日線
                    market=market,
                    code=code,
                    start=0,  # 從最新開始
                    count=count
                )
                
                if data is None or len(data) == 0:
                    raise DataFetchError(f"Pytdx 未查詢到 {stock_code} 的數據")
                
                # 轉換為 DataFrame
                df = api.to_df(data)
                
                # 過濾日期範圍
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df[(df['datetime'] >= start_date) & (df['datetime'] <= end_date)]
                
                return df
                
            except Exception as e:
                if isinstance(e, DataFetchError):
                    raise
                raise DataFetchError(f"Pytdx 獲取數據失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 Pytdx 數據
        
        Pytdx 返回的列名：
        datetime, open, high, low, close, vol, amount
        
        需要映射到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名映射
        column_mapping = {
            'datetime': 'date',
            'vol': 'volume',
        }
        
        df = df.rename(columns=column_mapping)
        
        # 計算漲跌幅（pytdx 不返回漲跌幅，需要自己計算）
        if 'pct_chg' not in df.columns and 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
        
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
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票名稱，失敗返回 None
        """
        # 先檢查快取
        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                # 獲取股票列表（快取）
                if self._stock_list_cache is None:
                    # 獲取深圳和上海股票列表
                    sz_stocks = api.get_security_list(0, 0)  # 深圳
                    sh_stocks = api.get_security_list(1, 0)  # 上海
                    
                    self._stock_list_cache = {}
                    for stock in (sz_stocks or []) + (sh_stocks or []):
                        self._stock_list_cache[stock['code']] = stock['name']
                
                # 查找股票名稱
                name = self._stock_list_cache.get(code)
                if name:
                    self._stock_name_cache[stock_code] = name
                    return name
                
                # 嘗試使用 get_finance_info
                finance_info = api.get_finance_info(market, code)
                if finance_info and 'name' in finance_info:
                    name = finance_info['name']
                    self._stock_name_cache[stock_code] = name
                    return name
                
        except Exception as e:
            logger.warning(f"Pytdx 獲取股票名稱失敗 {stock_code}: {e}")
        
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[dict]:
        """
        獲取即時行情
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            即時行情數據字典，失敗返回 None
        """
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                data = api.get_security_quotes([(market, code)])
                
                if data and len(data) > 0:
                    quote = data[0]
                    return {
                        'code': stock_code,
                        'name': quote.get('name', ''),
                        'price': quote.get('price', 0),
                        'open': quote.get('open', 0),
                        'high': quote.get('high', 0),
                        'low': quote.get('low', 0),
                        'pre_close': quote.get('last_close', 0),
                        'volume': quote.get('vol', 0),
                        'amount': quote.get('amount', 0),
                        'bid_prices': [quote.get(f'bid{i}', 0) for i in range(1, 6)],
                        'ask_prices': [quote.get(f'ask{i}', 0) for i in range(1, 6)],
                    }
        except Exception as e:
            logger.warning(f"Pytdx 獲取即時行情失敗 {stock_code}: {e}")
        
        return None


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = PytdxFetcher()
    
    try:
        # 測試歷史數據
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"獲取成功，共 {len(df)} 條數據")
        print(df.tail())
        
        # 測試股票名稱
        name = fetcher.get_stock_name('600519')
        print(f"股票名稱: {name}")
        
        # 測試即時行情
        quote = fetcher.get_realtime_quote('600519')
        print(f"即時行情: {quote}")
        
    except Exception as e:
        print(f"獲取失敗: {e}")
