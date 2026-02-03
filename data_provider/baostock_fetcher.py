# -*- coding: utf-8 -*-
"""
===================================
BaostockFetcher - 備用資料來源 2 (Priority 3)
===================================

數據來源：證券寶（Baostock）
特點：免費、無需 Token、需要登錄管理
優點：穩定、無配額限制

關鍵策略：
1. 管理 bs.login() 和 bs.logout() 生命周期
2. 使用上下文管理器防止連接洩露
3. 失敗後指數退避重試
"""

import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Generator

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


class BaostockFetcher(BaseFetcher):
    """
    Baostock 資料來源實現
    
    優先級：3
    數據來源：證券寶 Baostock API
    
    關鍵策略：
    - 使用上下文管理器管理連接生命週期
    - 每次請求都重新登錄/登出，防止連接洩露
    - 失敗後指數退避重試
    
    Baostock 特點：
    - 免費、無需註冊
    - 需要顯式登錄/登出
    - 數據更新略有延遲（T+1）
    """
    
    name = "BaostockFetcher"
    priority = int(os.getenv("BAOSTOCK_PRIORITY", "3"))
    
    def __init__(self):
        """初始化 BaostockFetcher"""
        self._bs_module = None
    
    def _get_baostock(self):
        """
        延遲加載 baostock 模組
        
        只在首次使用時導入，避免未安裝時報錯
        """
        if self._bs_module is None:
            import baostock as bs
            self._bs_module = bs
        return self._bs_module
    
    @contextmanager
    def _baostock_session(self) -> Generator:
        """
        Baostock 連接上下文管理器
        
        確保：
        1. 進入上下文時自動登錄
        2. 退出上下文時自動登出
        3. 異常時也能正確登出
        
        使用示例：
            with self._baostock_session():
                # 在這裡執行數據查詢
        """
        bs = self._get_baostock()
        login_result = None
        
        try:
            # 登錄 Baostock
            login_result = bs.login()
            
            if login_result.error_code != '0':
                raise DataFetchError(f"Baostock 登錄失敗: {login_result.error_msg}")
            
            logger.debug("Baostock 登錄成功")
            
            yield bs
            
        finally:
            # 確保登出，防止連接洩露
            try:
                logout_result = bs.logout()
                if logout_result.error_code == '0':
                    logger.debug("Baostock 登出成功")
                else:
                    logger.warning(f"Baostock 登出異常: {logout_result.error_msg}")
            except Exception as e:
                logger.warning(f"Baostock 登出時發生錯誤: {e}")
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        轉換股票代碼為 Baostock 格式
        
        Baostock 要求的格式：
        - 滬市：sh.600519
        - 深市：sz.000001
        
        Args:
            stock_code: 原始代碼，如 '600519', '000001'
            
        Returns:
            Baostock 格式代碼，如 'sh.600519', 'sz.000001'
        """
        code = stock_code.strip()
        
        # 已經包含前綴的情況
        if code.startswith(('sh.', 'sz.')):
            return code.lower()
        
        # 去除可能的後綴
        code = code.replace('.SH', '').replace('.SZ', '').replace('.sh', '').replace('.sz', '')
        
        # 根據代碼前綴判斷市場
        if code.startswith(('600', '601', '603', '688')):
            return f"sh.{code}"
        elif code.startswith(('000', '002', '300')):
            return f"sz.{code}"
        else:
            logger.warning(f"無法確定股票 {code} 的市場，預設使用深市")
            return f"sz.{code}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 Baostock 獲取原始數據
        
        使用 query_history_k_data_plus() 獲取日線數據
        
        流程：
        1. 檢查是否為美股（不支援）
        2. 使用上下文管理器管理連接
        3. 轉換股票代碼格式
        4. 調用 API 查詢數據
        5. 將結果轉換為 DataFrame
        """
        # 美股不支援，拋出異常讓 DataFetcherManager 切換到其他資料來源
        if _is_us_code(stock_code):
            raise DataFetchError(f"BaostockFetcher 不支援美股 {stock_code}，請使用 AkshareFetcher 或 YfinanceFetcher")
        
        # 轉換代碼格式
        bs_code = self._convert_stock_code(stock_code)
        
        logger.debug(f"調用 Baostock query_history_k_data_plus({bs_code}, {start_date}, {end_date})")
        
        with self._baostock_session() as bs:
            try:
                # 查詢日線數據
                # adjustflag: 1-後復權，2-前復權，3-不復權
                rs = bs.query_history_k_data_plus(
                    code=bs_code,
                    fields="date,open,high,low,close,volume,amount,pctChg",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",  # 日線
                    adjustflag="2"  # 前復權
                )
                
                if rs.error_code != '0':
                    raise DataFetchError(f"Baostock 查詢失敗: {rs.error_msg}")
                
                # 轉換為 DataFrame
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())
                
                if not data_list:
                    raise DataFetchError(f"Baostock 未查詢到 {stock_code} 的數據")
                
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                return df
                
            except Exception as e:
                if isinstance(e, DataFetchError):
                    raise
                raise DataFetchError(f"Baostock 獲取數據失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 Baostock 數據
        
        Baostock 返回的列名：
        date, open, high, low, close, volume, amount, pctChg
        
        需要映射到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名映射（只需要處理 pctChg）
        column_mapping = {
            'pctChg': 'pct_chg',
        }
        
        df = df.rename(columns=column_mapping)
        
        # 數值類型轉換（Baostock 返回的都是字串）
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
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
        
        使用 Baostock 的 query_stock_basic 介面獲取股票基本訊息
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票名稱，失敗返回 None
        """
        # 檢查快取
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 初始化快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            bs_code = self._convert_stock_code(stock_code)
            
            with self._baostock_session() as bs:
                # 查詢股票基本訊息
                rs = bs.query_stock_basic(code=bs_code)
                
                if rs.error_code == '0':
                    data_list = []
                    while rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        # Baostock 返回的欄位：code, code_name, ipoDate, outDate, type, status
                        fields = rs.fields
                        name_idx = fields.index('code_name') if 'code_name' in fields else None
                        if name_idx is not None and len(data_list[0]) > name_idx:
                            name = data_list[0][name_idx]
                            self._stock_name_cache[stock_code] = name
                            logger.debug(f"Baostock 獲取股票名稱成功: {stock_code} -> {name}")
                            return name
                
        except Exception as e:
            logger.warning(f"Baostock 獲取股票名稱失敗 {stock_code}: {e}")
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        獲取股票列表
        
        使用 Baostock 的 query_stock_basic 介面獲取全部股票列表
        
        Returns:
            包含 code, name 列的 DataFrame，失敗返回 None
        """
        try:
            with self._baostock_session() as bs:
                # 查詢所有股票基本訊息
                rs = bs.query_stock_basic()
                
                if rs.error_code == '0':
                    data_list = []
                    while rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        df = pd.DataFrame(data_list, columns=rs.fields)
                        
                        # 轉換代碼格式（去除 sh. 或 sz. 前綴）
                        df['code'] = df['code'].apply(lambda x: x.split('.')[1] if '.' in x else x)
                        df = df.rename(columns={'code_name': 'name'})
                        
                        # 更新快取
                        if not hasattr(self, '_stock_name_cache'):
                            self._stock_name_cache = {}
                        for _, row in df.iterrows():
                            self._stock_name_cache[row['code']] = row['name']
                        
                        logger.info(f"Baostock 獲取股票列表成功: {len(df)} 條")
                        return df[['code', 'name']]
                
        except Exception as e:
            logger.warning(f"Baostock 獲取股票列表失敗: {e}")
        
        return None


if __name__ == "__main__":
    # 測試代碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = BaostockFetcher()
    
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
