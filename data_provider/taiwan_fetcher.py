# -*- coding: utf-8 -*-
"""
===================================
TaiwanFetcher - 台股資料來源
===================================

數據來源：Yahoo Finance (通過 yfinance)
特點：穩定、支援台股、含基本面數據
"""

import logging
import os
import pandas as pd
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource
from .finmind_fetcher import FinMindFetcher

logger = logging.getLogger(__name__)

class TaiwanFetcher(BaseFetcher):
    """
    台股資料來源實現
    
    主要使用 yfinance 作為底層，獲取台股的歷史與即時數據。
    支援代碼格式：'2330', '2317' (會自動轉換為 .TW 或 .TWO)
    """
    
    name = "TaiwanFetcher"
    priority = int(os.getenv("TAIWAN_PRIORITY", "2"))
    
    def __init__(self):
        """初始化 TaiwanFetcher"""
        super().__init__()
        self.fm = FinMindFetcher()

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        轉換台股代碼為 yfinance 格式
        
        台股有兩個市場：
        - 上市 (TWSE): .TW
        - 上櫃 (TPEx): .TWO
        
        目前的策略是優先嘗試 .TW，如果失敗再嘗試 .TWO。
        或者根據常見規則判斷（雖不完全準確，但大約可用）。
        """
        code = stock_code.strip().upper()
        
        # 如果已經有後綴，直接返回
        if code.endswith('.TW') or code.endswith('.TWO'):
            return code
            
        # 移除可能的 'tw' 前綴
        if code.startswith('TW'):
             code = code[2:]
             
        # 大部分 4 位數代碼是上市或上櫃
        # 這裡預設返回 .TW，實際抓取時若失敗可重試（在 _fetch_raw_data 處理）
        return f"{code}.TW"

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 yfinance 獲取原始數據
        """
        import yfinance as yf
        
        yf_code = self._convert_stock_code(stock_code)
        logger.info(f"[TaiwanFetcher] 抓取 {yf_code} 歷史數據: {start_date} ~ {end_date}")
        
        try:
            # 優先嘗試 .TW
            ticker = yf.Ticker(yf_code)
            df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
            
            # 如果數據足夠少且代碼是 4 位，嘗試 .TWO (上櫃)
            if df.empty and yf_code.endswith('.TW') and len(stock_code) >= 4:
                alt_code = yf_code.replace('.TW', '.TWO')
                logger.debug(f"[TaiwanFetcher] .TW 無數據，嘗試 {alt_code}")
                ticker = yf.Ticker(alt_code)
                df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
            
            if df.empty:
                raise DataFetchError(f"yfinance 未查詢到台股 {stock_code} 的數據")
            
            return df
            
        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"TaiwanFetcher 獲取數據失敗: {e}") from e

    def get_main_indices(self) -> Optional[List[Dict[str, Any]]]:
        """獲取台股主要指數即時行情"""
        import yfinance as yf
        indices_map = {
            '^TWII': '加權指數',
            '^TWOII': '櫃買指數',
        }
        
        results = []
        try:
            for code, name in indices_map.items():
                ticker = yf.Ticker(code)
                hist = ticker.history(period='2d')
                if hist.empty:
                    continue
                
                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today
                
                price = float(today['Close'])
                prev_close = float(prev['Close'])
                high = float(today['High'])
                low = float(today['Low'])
                
                results.append({
                    'code': code,
                    'name': name,
                    'current': price,
                    'change': round(price - prev_close, 2),
                    'change_pct': round((price - prev_close) / prev_close * 100, 2) if prev_close else 0,
                    'open': float(today['Open']),
                    'high': high,
                    'low': low,
                    'prev_close': prev_close,
                    'volume': float(today['Volume']),
                    'amount': float(today['Volume']) * price, # 概算
                    'amplitude': round((high - low) / prev_close * 100, 2) if prev_close else 0,
                })
            return results
        except Exception as e:
            logger.error(f"[Taiwan] 獲取指數行情失敗: {e}")
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """獲取台股市場漲跌統計 (透過 FinMind)"""
        try:
            return self.fm.fetch_market_summary()
        except Exception as e:
            logger.error(f"[Taiwan] 獲取市場統計失敗: {e}")
            return None

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 yfinance 數據為系統規格
        """
        df = df.copy()
        
        # yfinance history 返回的是 MultiIndex (新版) 或 一般索引
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.reset_index()
        
        # 映射列名
        column_mapping = {
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        }
        df = df.rename(columns=column_mapping)
        
        # 標準化日期格式
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
        # 計算漲跌幅
        if 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
            
        # 估算成交額
        if 'volume' in df.columns and 'close' in df.columns:
            df['amount'] = df['volume'] * df['close']
        else:
            df['amount'] = 0
            
        df['code'] = stock_code
        
        # 透過 FinMind 補齊籌碼數據
        try:
            df = self.fm.augment_stock_data(df, stock_code)
        except Exception as e:
            logger.warning(f"[Taiwan] FinMind 數據增強失敗: {e}")
            # 確保欄位存在以防合併出錯
            for col in ['foreign_buy', 'it_buy', 'dealers_buy', 'margin_buy', 'short_buy', 'revenue_yoy']:
                if col not in df.columns:
                    df[col] = 0.0
        
        # 只保留標準列 + 台灣特有列
        keep_cols = ['code'] + STANDARD_COLUMNS + ['foreign_buy', 'it_buy', 'dealers_buy', 'margin_buy', 'short_buy', 'revenue_yoy']
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取台股即時行情
        """
        import yfinance as yf
        
        yf_code = self._convert_stock_code(stock_code)
        
        try:
            ticker = yf.Ticker(yf_code)
            
            # yfinance 的 realtime 通常稍有延遲，但 history(period='2d') 可獲取當日
            hist = ticker.history(period='2d')
            if hist.empty:
                 # 嘗試 .TWO
                 if yf_code.endswith('.TW'):
                     yf_code = yf_code.replace('.TW', '.TWO')
                     ticker = yf.Ticker(yf_code)
                     hist = ticker.history(period='2d')
            
            if hist.empty:
                return None
                
            today = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else today
            
            price = float(today['Close'])
            prev_close = float(prev['Close'])
            
            # 獲取基礎資訊
            try:
                info = ticker.info
                # 優先使用 info 中的即時數據（如果有的話）
                price_rt = info.get('regularMarketPrice') or info.get('currentPrice')
                if price_rt:
                    price = price_rt
                    prev_close = info.get('regularMarketPreviousClose') or prev_close
                
                name = info.get('shortName') or info.get('longName') or stock_code
                pe = info.get('trailingPE')
                pb = info.get('priceToBook')
                mv = info.get('marketCap')
            except:
                name = stock_code
                pe, pb, mv = None, None, None
                
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=name,
                source=RealtimeSource.FALLBACK,
                price=price,
                change_pct=round((price - prev_close) / prev_close * 100, 2) if prev_close else 0,
                change_amount=round(price - prev_close, 2) if prev_close else 0,
                volume=int(today['Volume']),
                open_price=float(today['Open']),
                high=float(today['High']),
                low=float(today['Low']),
                pre_close=prev_close,
                pe_ratio=pe,
                pb_ratio=pb,
                total_mv=mv,
                circ_mv=None
            )
            return quote
        except Exception as e:
            logger.warning(f"TaiwanFetcher 獲取即時行情失敗: {e}")
            return None

if __name__ == "__main__":
    # 測試
    logging.basicConfig(level=logging.INFO)
    fetcher = TaiwanFetcher()
    data = fetcher.get_daily_data('2330')
    print(data.tail())
    quote = fetcher.get_realtime_quote('2330')
    print(quote)
