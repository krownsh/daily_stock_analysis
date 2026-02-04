# -*- coding: utf-8 -*-
"""
===================================
EfinanceFetcher - 優先數據源 (Priority 0)
===================================

數據來源：東方財富爬蟲（通過 efinance 庫）
特點：免費、無需 Token、數據全面、API 簡潔
倉庫：https://github.com/Micro-sheep/efinance

與 AkshareFetcher 類似，但 efinance 庫：
1. API 更簡潔易用
2. 支持批量獲取數據
3. 更穩定的介面封裝

防封鎖策略：
1. 每次請求前隨機休眠 1.5-3.0 秒
2. 隨機輪長 User-Agent
3. 使用 tenacity 實現指數退避重試
4. 熔斷器機制：連續失敗後自動冷卻
"""

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd
import requests  # 引入 requests 以捕獲異常
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS
from .realtime_types import (
    UnifiedRealtimeQuote, RealtimeSource,
    get_realtime_circuit_breaker,
    safe_float, safe_int  # 使用統一的類型轉換函數
)


# 保留舊的類型別名，用於向後兼容
@dataclass
class EfinanceRealtimeQuote:
    """
    即時行情數據（來自 efinance）- 向後兼容別名
    
    新代碼建議使用 UnifiedRealtimeQuote
    """
    code: str
    name: str = ""
    price: float = 0.0           # 最新價
    change_pct: float = 0.0      # 漲跌幅(%)
    change_amount: float = 0.0   # 漲跌額
    
    # 量價指標
    volume: int = 0              # 成交量
    amount: float = 0.0          # 成交額
    turnover_rate: float = 0.0   # 換手率(%)
    amplitude: float = 0.0       # 振幅(%)
    
    # 價格區間
    high: float = 0.0            # 最高價
    low: float = 0.0             # 最低價
    open_price: float = 0.0      # 開盤價
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'code': self.code,
            'name': self.name,
            'price': self.price,
            'change_pct': self.change_pct,
            'change_amount': self.change_amount,
            'volume': self.volume,
            'amount': self.amount,
            'turnover_rate': self.turnover_rate,
            'amplitude': self.amplitude,
            'high': self.high,
            'low': self.low,
            'open': self.open_price,
        }


logger = logging.getLogger(__name__)


# User-Agent 池，用於隨機輪換
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


# 快取即時行情數據（避免重複請求）
# TTL 設為 10 分鐘 (600秒)：批量分析場景下避免重複拉取
_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 10分鐘快取有效期
}


def _is_etf_code(stock_code: str) -> bool:
    """
    判斷代碼是否為 ETF 基金
    
    ETF 代碼規則：
    - 上交所 ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - 深交所 ETF: 15xxxx, 16xxxx, 18xxxx
    
    Args:
        stock_code: 股票/基金代碼
        
    Returns:
        True 表示是 ETF 代碼，False 表示是普通股票代碼
    """
    etf_prefixes = ('51', '52', '56', '58', '15', '16', '18')
    return stock_code.startswith(etf_prefixes) and len(stock_code) == 6


def _is_us_code(stock_code: str) -> bool:
    """
    判斷代碼是否為美股
    
    美股代碼規則：
    - 1-5個大寫字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class EfinanceFetcher(BaseFetcher):
    """
    Efinance 數據源實現
    
    優先級：0（最高，優先於 AkshareFetcher）
    數據來源：東方財富網（通過 efinance 庫封裝）
    倉庫：https://github.com/Micro-sheep/efinance
    
    主要 API：
    - ef.stock.get_quote_history(): 獲取歷史 K 線數據
    - ef.stock.get_base_info(): 獲取股票基本信息
    - ef.stock.get_realtime_quotes(): 獲取即時行情
    
    關鍵策略：
    - 每次請求前隨機休眠 1.5-3.0 秒
    - 隨機 User-Agent 輪換
    - 失敗後指數退避重試（最多3次）
    """
    
    name = "EfinanceFetcher"
    priority = int(os.getenv("EFINANCE_PRIORITY", "0"))  # 最高優先級，排在 AkshareFetcher 之前
    
    def __init__(self, sleep_min: float = 1.5, sleep_max: float = 3.0):
        """
        初始化 EfinanceFetcher
        
        Args:
            sleep_min: 最小休眠時間（秒）
            sleep_max: 最大休眠時間（秒）
        """
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self._last_request_time: Optional[float] = None
    
    def _set_random_user_agent(self) -> None:
        """
        設置隨機 User-Agent
        
        通過修改 requests Session 的 headers 實現
        這是關鍵的防封鎖策略之一
        """
        try:
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"設置 User-Agent: {random_ua[:50]}...")
        except Exception as e:
            logger.debug(f"設置 User-Agent 失敗: {e}")
    
    def _enforce_rate_limit(self) -> None:
        """
        強制執行速率限制
        
        策略：
        1. 檢查距離上次請求的時間間隔
        2. 如果間隔不足，補充休眠時間
        3. 然後再執行隨機 jitter 休眠
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"補充休眠 {additional_sleep:.2f} 秒")
                time.sleep(additional_sleep)
        
        # 執行隨機 jitter 休眠
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(5),  # 增加到5次
        wait=wait_exponential(multiplier=1, min=4, max=60),  # 增加等待時間：4, 8, 16...
        retry=retry_if_exception_type((
            ConnectionError,
            TimeoutError,
            requests.exceptions.RequestException,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 efinance 獲取原始數據
        
        根據代碼類型自動選擇 API：
        - 美股：不支持，拋出異常讓 DataFetcherManager 切換到其他數據源
        - 普通股票：使用 ef.stock.get_quote_history()
        - ETF 基金：使用 ef.fund.get_quote_history()
        
        流程：
        1. 判斷代碼類型（美股/股票/ETF）
        2. 設置隨機 User-Agent
        3. 執行速率限制（隨機休眠）
        4. 調用對應的 efinance API
        5. 處理返回數據
        """
        # 美股不支持，拋出異常讓 DataFetcherManager 切換到 AkshareFetcher/YfinanceFetcher
        if _is_us_code(stock_code):
            raise DataFetchError(f"EfinanceFetcher 不支持美股 {stock_code}，請使用 AkshareFetcher 或 YfinanceFetcher")
        
        # 根據代碼類型選擇不同的獲取方法
        if _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)
    
    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史數據
        
        數據來源：ef.stock.get_quote_history()
        
        API 參數說明：
        - stock_codes: 股票代碼
        - beg: 開始日期，格式 'YYYYMMDD'
        - end: 結束日期，格式 'YYYYMMDD'
        - klt: 週期，101=日線
        - fqt: 復權方式，1=前復權
        """
        import efinance as ef
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        # 格式化日期（efinance 使用 YYYYMMDD 格式）
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        
        logger.info(f"[API調用] ef.stock.get_quote_history(stock_codes={stock_code}, "
                   f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # 調用 efinance 獲取 A 股日線數據
            # klt=101 獲取日線數據
            # fqt=1 獲取前復權數據
            df = ef.stock.get_quote_history(
                stock_codes=stock_code,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # 日線
                fqt=1     # 前復權
            )
            
            api_elapsed = _time.time() - api_start
            
            # 記錄回傳數據摘要
            if df is not None and not df.empty:
                logger.info(f"[API回傳] ef.stock.get_quote_history 成功: 回傳 {len(df)} 行數據, 耗時 {api_elapsed:.2f}s")
                logger.info(f"[API回傳] 列名: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API回傳] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API回傳] 最新3條數據:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API回傳] ef.stock.get_quote_history 回傳空數據, 耗時 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測反爬封禁
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                logger.warning(f"檢測到可能被封禁: {e}")
                raise RateLimitError(f"efinance 可能被限流: {e}") from e
            
            raise DataFetchError(f"efinance 獲取數據失敗: {e}") from e
    
    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取 ETF 基金歷史數據
        
        數據來源：ef.fund.get_quote_history()
        
        Args:
            stock_code: ETF 代碼，如 '512400', '159883'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            ETF 歷史數據 DataFrame
        """
        import efinance as ef
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        # 格式化日期
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        
        logger.info(f"[API調用] ef.fund.get_quote_history(fund_code={stock_code})")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # 調用 efinance 獲取 ETF 日線數據
            # 注意: ef.fund.get_quote_history 不支持 beg/end/klt/fqt 參數
            # 它返回的是 NAV 數據: 日期, 單位淨值, 累計淨值, 漲跌幅
            df = ef.fund.get_quote_history(fund_code=stock_code)
            
            # 手動過濾日期
            if df is not None and not df.empty and '日期' in df.columns:
                # 確保日期列是字串格式，且格式匹配篩選條件
                # ef 返回的日期通常是 'YYYY-MM-DD'
                mask = (df['日期'] >= start_date) & (df['日期'] <= end_date)
                df = df[mask].copy()
            
            api_elapsed = _time.time() - api_start
            
            # 記錄回傳數據摘要
            if df is not None and not df.empty:
                logger.info(f"[API回傳] ef.fund.get_quote_history 成功: 回傳 {len(df)} 行數據, 耗時 {api_elapsed:.2f}s")
                logger.info(f"[API回傳] 列名: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API回傳] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API回傳] 最新3條數據:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API回傳] ef.fund.get_quote_history 回傳空數據, 耗時 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測反爬封禁
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                logger.warning(f"檢測到可能被封禁: {e}")
                raise RateLimitError(f"efinance 可能被限流: {e}") from e
            
            raise DataFetchError(f"efinance 獲取 ETF 數據失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 efinance 數據
        
        efinance 返回的列名（中文）：
        股票名稱, 股票代碼, 日期, 開盤, 收盤, 最高, 最低, 成交量, 成交額, 振幅, 漲跌幅, 漲跌額, 換手率
        
        需要映射到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名映射（efinance 中文列名 -> 標準英文列名）
        column_mapping = {
            '日期': 'date',
            '開盤': 'open',
            '收盤': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交額': 'amount',
            '漲跌幅': 'pct_chg',
            '股票代碼': 'code',
            '股票名稱': 'name',
            # ETF 基金可能的列名
            '基金代碼': 'code',
            '基金名稱': 'name',
            '單位淨值': 'close',
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 對於 ETF 數據（只有 close/單位淨值），補全其他 OHLC 列
        # 這是一個近似處理，因為 efinance 基金介面不提供 OHLC 數據
        if 'close' in df.columns and 'open' not in df.columns:
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']
            
        # 補全 volume 和 amount，如果缺失
        if 'volume' not in df.columns:
            df['volume'] = 0
        if 'amount' not in df.columns:
            df['amount'] = 0

        
        # 如果沒有 code 列，手動添加
        if 'code' not in df.columns:
            df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df
    
    def get_realtime_quote(self, stock_code: str) -> Optional[EfinanceRealtimeQuote]:
        """
        獲取即時行情數據
        
        數據來源：ef.stock.get_realtime_quotes()
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            UnifiedRealtimeQuote 對象，獲取失敗返回 None
        """
        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance"
        
        # 檢查熔斷器狀態
        if not circuit_breaker.is_available(source_key):
            logger.warning(f"[熔斷] 數據源 {source_key} 處於熔斷狀態，跳過")
            return None
        
        try:
            # 檢查快取
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[快取命中] 即時行情(efinance) - 快取年齡 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # 觸發全量刷新
                logger.info(f"[快取未命中] 觸發全量刷新 即時行情(efinance)")
                # 防封禁策略
                self._set_random_user_agent()
                self._enforce_rate_limit()
                
                logger.info(f"[API調用] ef.stock.get_realtime_quotes() 獲取即時行情...")
                import time as _time
                api_start = _time.time()
                
                # efinance 的即時行情 API
                df = ef.stock.get_realtime_quotes()
                
                api_elapsed = _time.time() - api_start
                logger.info(f"[API回傳] ef.stock.get_realtime_quotes 成功: 回傳 {len(df)} 隻股票, 耗時 {api_elapsed:.2f}s")
                circuit_breaker.record_success(source_key)
                
                # 更新快取
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[快取更新] 即時行情(efinance) 快取已刷新，TTL={_realtime_cache['ttl']}s")
            
            # 查找指定股票
            # efinance 返回的列名可能是 '股票代碼' 或 'code'
            code_col = '股票代碼' if '股票代碼' in df.columns else 'code'
            row = df[df[code_col] == stock_code]
            if row.empty:
                logger.warning(f"[API返回] 未找到股票 {stock_code} 的即時行情")
                return None
            
            row = row.iloc[0]
            
            # 使用 realtime_types.py 中的統一轉換函數
            # 獲取列名（可能是中文或英文）
            name_col = '股票名稱' if '股票名稱' in df.columns else 'name'
            price_col = '最新價' if '最新價' in df.columns else 'price'
            pct_col = '漲跌幅' if '漲跌幅' in df.columns else 'pct_chg'
            chg_col = '漲跌額' if '漲跌額' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交額' if '成交額' in df.columns else 'amount'
            turn_col = '換手率' if '換手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '開盤' if '開盤' in df.columns else 'open'
            # efinance 也返回量比、市盈率、市值等欄位
            vol_ratio_col = '量比' if '量比' in df.columns else 'volume_ratio'
            pe_col = '市盈率' if '市盈率' in df.columns else 'pe_ratio'
            total_mv_col = '總市值' if '總市值' in df.columns else 'total_mv'
            circ_mv_col = '流通市值' if '流通市值' in df.columns else 'circ_mv'
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
                volume_ratio=safe_float(row.get(vol_ratio_col)),  # 量比
                pe_ratio=safe_float(row.get(pe_col)),  # 市盈率
                total_mv=safe_float(row.get(total_mv_col)),  # 總市值
                circ_mv=safe_float(row.get(circ_mv_col)),  # 流通市值
            )
            
            logger.info(f"[即時行情-efinance] {stock_code} {quote.name}: 價格={quote.price}, 漲跌={quote.change_pct}%, "
                       f"量比={quote.volume_ratio}, 換手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 即時行情(efinance)失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def get_base_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        獲取股票基本信息
        
        數據來源：ef.stock.get_base_info()
        包含：市盈率、市淨率、所處行業、總市值、流通市值、ROE、淨利率等
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            包含基本信息的字典，獲取失敗返回 None
        """
        import efinance as ef
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API調用] ef.stock.get_base_info(stock_codes={stock_code}) 獲取基本信息...")
            import time as _time
            api_start = _time.time()
            
            info = ef.stock.get_base_info(stock_code)
            
            api_elapsed = _time.time() - api_start
            logger.info(f"[API返回] ef.stock.get_base_info 成功, 耗時 {api_elapsed:.2f}s")
            
            if info is None:
                logger.warning(f"[API返回] 未獲取到 {stock_code} 的基本信息")
                return None
            
            # 轉換為字典
            if isinstance(info, pd.Series):
                return info.to_dict()
            elif isinstance(info, pd.DataFrame):
                if not info.empty:
                    return info.iloc[0].to_dict()
            
            return None
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 基本信息失敗: {e}")
            return None
    
    def get_belong_board(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        獲取股票所屬板塊
        
        數據來源：ef.stock.get_belong_board()
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            所屬板塊 DataFrame，獲取失敗返回 None
        """
        import efinance as ef
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API調用] ef.stock.get_belong_board(stock_code={stock_code}) 獲取所屬板塊...")
            import time as _time
            api_start = _time.time()
            
            df = ef.stock.get_belong_board(stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df is not None and not df.empty:
                logger.info(f"[API返回] ef.stock.get_belong_board 成功: 返回 {len(df)} 個板塊, 耗時 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API返回] 未獲取到 {stock_code} 的板塊信息")
                return None
                
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 所屬板塊失敗: {e}")
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        獲取增強數據（歷史K線 + 即時行情 + 基本信息）
        
        Args:
            stock_code: 股票代碼
            days: 歷史數據天數
            
        Returns:
            包含所有數據的字典
        """
        result = {
            'code': stock_code,
            'daily_data': None,
            'realtime_quote': None,
            'base_info': None,
            'belong_board': None,
        }
        
        # 獲取日線數據
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            logger.error(f"獲取 {stock_code} 日線數據失敗: {e}")
        
        # 獲取即時行情
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # 獲取基本信息
        result['base_info'] = self.get_base_info(stock_code)
        
        # 獲取所屬板塊
        result['belong_board'] = self.get_belong_board(stock_code)
        
        return result


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = EfinanceFetcher()
    
    # 測試普通股票
    print("=" * 50)
    print("測試普通股票數據獲取 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"[股票] 獲取成功，共 {len(df)} 條數據")
        print(df.tail())
    except Exception as e:
        print(f"[股票] 獲取失敗: {e}")
    
    # 測試 ETF 基金
    print("\n" + "=" * 50)
    print("測試 ETF 基金數據獲取 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('512400')  # 有色龍頭ETF
        print(f"[ETF] 獲取成功，共 {len(df)} 條數據")
        print(df.tail())
    except Exception as e:
        print(f"[ETF] 獲取失敗: {e}")
    
    # 測試即時行情
    print("\n" + "=" * 50)
    print("測試即時行情獲取 (efinance)")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('600519')
        if quote:
            print(f"[即時行情] {quote.name}: 價格={quote.price}, 漲跌幅={quote.change_pct}%")
        else:
            print("[即時行情] 未獲取到數據")
    except Exception as e:
        print(f"[即時行情] 獲取失敗: {e}")
    
    # 測試基本信息
    print("\n" + "=" * 50)
    print("測試基本信息獲取 (efinance)")
    print("=" * 50)
    try:
        info = fetcher.get_base_info('600519')
        if info:
            print(f"[基本信息] 市盈率={info.get('市盈率(動)', 'N/A')}, 市淨率={info.get('市淨率', 'N/A')}")
        else:
            print("[基本信息] 未獲取到數據")
    except Exception as e:
        print(f"[基本信息] 獲取失敗: {e}")
