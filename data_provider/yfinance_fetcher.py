# -*- coding: utf-8 -*-
"""
===================================
YfinanceFetcher - 兜底資料來源 (Priority 4)
===================================

數據來源：Yahoo Finance（通過 yfinance 庫）
特點：國際資料來源、可能有延遲或缺失
定位：當所有國內資料來源都失敗時的最後保障

關鍵策略：
1. 自動將 A 股代碼轉換為 yfinance 格式（.SS / .SZ）
2. 處理 Yahoo Finance 的數據格式差異
3. 失敗後指數退避重試
"""

import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource
import os

logger = logging.getLogger(__name__)


class YfinanceFetcher(BaseFetcher):
    """
    Yahoo Finance 資料來源實現
    
    優先級：4（最低，作為兜底）
    數據來源：Yahoo Finance
    
    關鍵策略：
    - 自動轉換股票代碼格式
    - 處理時區和數據格式差異
    - 失敗後指數退避重試
    
    注意事項：
    - A 股數據可能有延遲
    - 某些股票可能無數據
    - 數據精度可能與國內源略有差異
    """
    
    name = "YfinanceFetcher"
    priority = int(os.getenv("YFINANCE_PRIORITY", "4"))
    
    def __init__(self):
        """初始化 YfinanceFetcher"""
        pass
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        轉換股票代碼為 Yahoo Finance 格式
        
        Yahoo Finance 代碼格式：
        - A股滬市：600519.SS (Shanghai Stock Exchange)
        - A股深市：000001.SZ (Shenzhen Stock Exchange)
        - 港股：0700.HK (Hong Kong Stock Exchange)
        - 美股：AAPL, TSLA, GOOGL (無需後綴)
        
        Args:
            stock_code: 原始代碼，如 '600519', 'hk00700', 'AAPL'
            
        Returns:
            Yahoo Finance 格式代碼

        Examples:
            >>> fetcher._convert_stock_code('600519')
            '600519.SS'
            >>> fetcher._convert_stock_code('hk00700')
            '0700.HK'
            >>> fetcher._convert_stock_code('AAPL')
            'AAPL'
        """
        import re

        code = stock_code.strip().upper()

        # 美股：1-5个大写字母（可能包含 .），直接返回
        if re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code):
            logger.debug(f"识别为美股代码: {code}")
            return code

        # 港股：hk前缀 -> .HK后缀
        if code.startswith('HK'):
            hk_code = code[2:].lstrip('0') or '0'  # 去除前导0，但保留至少一个0
            hk_code = hk_code.zfill(4)  # 补齐到4位
            logger.debug(f"轉換港股代碼: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # 已經包含後綴的情況
        if '.SS' in code or '.SZ' in code or '.HK' in code:
            return code

        # 去除可能的 .SH 後綴
        code = code.replace('.SH', '')

        # A 股：根據代碼前綴判斷市場
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SS"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            logger.warning(f"無法確定股票 {code} 的市場，默認使用深市")
            return f"{code}.SZ"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 Yahoo Finance 獲取原始數據
        
        使用 yfinance.download() 獲取歷史數據
        
        流程：
        1. 轉換股票代碼格式
        2. 調用 yfinance API
        3. 處理返回數據
        """
        import yfinance as yf
        
        # 轉換代碼格式
        yf_code = self._convert_stock_code(stock_code)
        
        logger.debug(f"調用 yfinance.download({yf_code}, {start_date}, {end_date})")
        
        try:
            # 使用 yfinance 下載數據
            df = yf.download(
                tickers=yf_code,
                start=start_date,
                end=end_date,
                progress=False,  # 禁止進度條
                auto_adjust=True,  # 自動調整價格（復權）
            )
            
            if df.empty:
                raise DataFetchError(f"Yahoo Finance 未查詢到 {stock_code} 的數據")
            
            return df
            
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Yahoo Finance 獲取數據失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 Yahoo Finance 數據
        
        yfinance 回傳的列名：
        Open, High, Low, Close, Volume（索引是日期）
        
        注意：新版 yfinance 回傳 MultiIndex 列名，如 ('Close', 'AMD')
        需要先扁平化列名再進行處理
        
        需要映射到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 處理 MultiIndex 列名（新版 yfinance 回傳格式）
        # 例如: ('Close', 'AMD') -> 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            logger.debug(f"檢測到 MultiIndex 列名，進行扁平化處理")
            # 取第一級列名（Price level: Close, High, Low, etc.）
            df.columns = df.columns.get_level_values(0)
        
        # 重置索引，將日期從索引變為列
        df = df.reset_index()
        
        # 列名映射（yfinance 使用首字母大寫）
        column_mapping = {
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        }
        
        df = df.rename(columns=column_mapping)
        
        # 計算漲跌幅（因為 yfinance 不直接提供）
        if 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
        
        # 計算成交額（yfinance 不提供，使用估算值）
        # 成交額 ≈ 成交量 * 平均價格
        if 'volume' in df.columns and 'close' in df.columns:
            df['amount'] = df['volume'] * df['close']
        else:
            df['amount'] = 0
        
        # 添加股票代碼列
        df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_main_indices(self) -> Optional[List[Dict[str, Any]]]:
        """
        獲取主要指數行情 (Yahoo Finance)
        """
        import yfinance as yf

        # 映射關係：akshare 代碼 -> (yfinance 代碼, 名稱)
        yf_mapping = {
            'sh000001': ('000001.SS', '上證指數'),
            'sz399001': ('399001.SZ', '深證成指'),
            'sz399006': ('399006.SZ', '創業板指'),
            'sh000688': ('000688.SS', '科創 50'),
            'sh000016': ('000016.SS', '上證 50'),
            'sh000300': ('000300.SS', '滬深 300'),
        }

        results = []
        try:
            for ak_code, (yf_code, name) in yf_mapping.items():
                try:
                    ticker = yf.Ticker(yf_code)
                    # 獲取最近 2 天數據以計算漲跌
                    hist = ticker.history(period='2d')
                    if hist.empty:
                        continue

                    today = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else today

                    price = float(today['Close'])
                    prev_close = float(prev['Close'])
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100 if prev_close else 0

                    # 振幅
                    high = float(today['High'])
                    low = float(today['Low'])
                    amplitude = ((high - low) / prev_close * 100) if prev_close else 0

                    results.append({
                        'code': ak_code,
                        'name': name,
                        'current': price,
                        'change': change,
                        'change_pct': change_pct,
                        'open': float(today['Open']),
                        'high': high,
                        'low': low,
                        'prev_close': prev_close,
                        'volume': float(today['Volume']),
                        'amount': 0.0, # Yahoo Finance 可能不提供準確的成交額
                        'amplitude': amplitude
                    })
                    logger.debug(f"[Yfinance] 獲取指數 {name} 成功")

                except Exception as e:
                    logger.warning(f"[Yfinance] 獲取指數 {name} 失敗: {e}")
                    continue

            if results:
                logger.info(f"[Yfinance] 成功獲取 {len(results)} 個指數行情")
                return results

        except Exception as e:
            logger.error(f"[Yfinance] 獲取指數行情失敗: {e}")

        return None

    def _is_us_stock(self, stock_code: str) -> bool:
        """
        判斷代碼是否為美股
        
        美股代碼規則：
        - 1-5 個大寫字母，如 'AAPL', 'TSLA'
        - 可能包含 '.'，如 'BRK.B'
        """
        code = stock_code.strip().upper()
        return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取美股即時行情數據
        
        資料來源：yfinance Ticker.info
        
        Args:
            stock_code: 美股代碼，如 'AMD', 'AAPL', 'TSLA'
            
        Returns:
            UnifiedRealtimeQuote 對象，獲取失敗回傳 None
        """
        import yfinance as yf
        
        # 僅處理美股
        if not self._is_us_stock(stock_code):
            logger.debug(f"[Yfinance] {stock_code} 不是美股，跳過")
            return None
        
        try:
            symbol = stock_code.strip().upper()
            logger.debug(f"[Yfinance] 獲取美股 {symbol} 即時行情")
            
            ticker = yf.Ticker(symbol)
            
            # 嘗試獲取 fast_info（更快，但欄位較少）
            try:
                info = ticker.fast_info
                if info is None:
                    raise ValueError("fast_info is None")
                
                price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                open_price = getattr(info, 'open', None)
                high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
                market_cap = getattr(info, 'marketCap', None) or getattr(info, 'market_cap', None)
                
            except Exception:
                # 回退到 history 方法獲取最新數據
                logger.debug(f"[Yfinance] fast_info 失敗，嘗試 history 方法")
                hist = ticker.history(period='2d')
                if hist.empty:
                    logger.warning(f"[Yfinance] 無法獲取 {symbol} 的數據")
                    return None
                
                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today
                
                price = float(today['Close'])
                prev_close = float(prev['Close'])
                open_price = float(today['Open'])
                high = float(today['High'])
                low = float(today['Low'])
                volume = int(today['Volume'])
                market_cap = None
            
            # 計算漲跌幅
            change_amount = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100
            
            # 計算振幅
            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = ((high - low) / prev_close) * 100
            
            # 獲取股票名稱
            try:
                name = ticker.info.get('shortName', '') or ticker.info.get('longName', '') or symbol
            except Exception:
                name = symbol
            
            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=name,
                source=RealtimeSource.FALLBACK,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,  # yfinance 不直接提供成交額
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=market_cap,
                circ_mv=None,
            )
            
            logger.info(f"[Yfinance] 獲取美股 {symbol} 即時行情成功: 價格={price}")
            return quote
            
        except Exception as e:
            logger.warning(f"[Yfinance] 獲取美股 {stock_code} 即時行情失敗: {e}")
            return None


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = YfinanceFetcher()
    
    try:
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"獲取成功，共 {len(df)} 條數據")
        print(df.tail())
    except Exception as e:
        print(f"獲取失敗: {e}")
