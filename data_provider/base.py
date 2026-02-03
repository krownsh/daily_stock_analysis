# -*- coding: utf-8 -*-
"""
===================================
數據源基類與管理器
===================================

設計模式：策略模式 (Strategy Pattern)
- BaseFetcher: 抽象基類，定義統一介面
- DataFetcherManager: 策略管理器，實現自動切換

防封禁策略：
1. 每個 Fetcher 內置流控邏輯
2. 失敗自動切換到下一個數據源
3. 指數退避重試機制
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import numpy as np
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# 配置日誌
logger = logging.getLogger(__name__)


# === 標準化列名定義 ===
STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']


class DataFetchError(Exception):
    """數據獲取異常基類"""
    pass


class RateLimitError(DataFetchError):
    """API 速率限制異常"""
    pass


class DataSourceUnavailableError(DataFetchError):
    """數據源不可用異常"""
    pass


class BaseFetcher(ABC):
    """
    數據源抽象基類
    
    職責：
    1. 定義統一的數據獲取介面
    2. 提供數據標準化方法
    3. 實現通用的技術指標計算
    
    子類實現：
    - _fetch_raw_data(): 從具體數據源獲取原始數據
    - _normalize_data(): 將原始數據轉換為標準格式
    """
    
    name: str = "BaseFetcher"
    priority: int = 99  # 優先級數字越小越優先
    
    @abstractmethod
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從數據源獲取原始數據（子類必須實現）
        
        Args:
            stock_code: 股票代碼，如 '600519', '000001'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            原始數據 DataFrame（列名因數據源而異）
        """
        pass
    
    @abstractmethod
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化數據列名（子類必須實現）

        將不同數據源的列名統一為：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        """
        pass

    def get_main_indices(self) -> Optional[List[Dict[str, Any]]]:
        """
        獲取主要指數即時行情

        Returns:
            List[Dict]: 指數列表，每個元素為字典，包含:
                - code: 指數代碼
                - name: 指數名稱
                - current: 當前點位
                - change: 漲跌點數
                - change_pct: 漲跌幅(%)
                - volume: 成交量
                - amount: 成交額
        """
        return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        獲取市場漲跌統計

        Returns:
            Dict: 包含:
                - up_count: 上漲家數
                - down_count: 下跌家數
                - flat_count: 平盤家數
                - limit_up_count: 漲停家數
                - limit_down_count: 跌停家數
                - total_amount: 兩市成交額
        """
        return None

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        獲取板塊漲跌榜

        Args:
            n: 返回前n個

        Returns:
            Tuple: (領漲板塊列表, 領跌板塊列表)
        """
        return None

    def get_daily_data(
        self,
        stock_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> pd.DataFrame:
        """
        獲取日線數據（統一入口）
        
        流程：
        1. 計算日期範圍
        2. 調用子類獲取原始數據
        3. 標準化列名
        4. 計算技術指標
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期（可選）
            end_date: 結束日期（可選，默認今天）
            days: 獲取天數（當 start_date 未指定時使用）
            
        Returns:
            標準化的 DataFrame，包含技術指標
        """
        # 計算日期範圍
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if start_date is None:
            # 默認獲取最近 30 個交易日（按日曆日估算，多取一些）
            from datetime import timedelta
            start_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=days * 2)
            start_date = start_dt.strftime('%Y-%m-%d')
        
        logger.info(f"[{self.name}] 獲取 {stock_code} 數據: {start_date} ~ {end_date}")
        
        try:
            # Step 1: 獲取原始數據
            raw_df = self._fetch_raw_data(stock_code, start_date, end_date)
            
            if raw_df is None or raw_df.empty:
                raise DataFetchError(f"[{self.name}] 未獲取到 {stock_code} 的數據")
            
            # Step 2: 標準化列名
            df = self._normalize_data(raw_df, stock_code)
            
            # Step 3: 數據清洗
            df = self._clean_data(df)
            
            # Step 4: 計算技術指標
            df = self._calculate_indicators(df)
            
            logger.info(f"[{self.name}] {stock_code} 獲取成功，共 {len(df)} 條數據")
            return df
            
        except Exception as e:
            logger.error(f"[{self.name}] 獲取 {stock_code} 失敗: {str(e)}")
            raise DataFetchError(f"[{self.name}] {stock_code}: {str(e)}") from e
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        數據清洗
        
        處理：
        1. 確保日期列格式正確
        2. 數值類型轉換
        3. 去除空值行
        4. 按日期排序
        """
        df = df.copy()
        
        # 確保日期列為 datetime 類型
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # 數值列類型轉換
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 去除關鍵列為空的行
        df = df.dropna(subset=['close', 'volume'])
        
        # 按日期升序排序
        df = df.sort_values('date', ascending=True).reset_index(drop=True)
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算技術指標
        
        計算指標：
        - MA5, MA10, MA20: 移動平均線
        - Volume_Ratio: 量比（今日成交量 / 5日平均成交量）
        """
        df = df.copy()
        
        # 點移平均線
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean()
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean()
        
        # 量比：當日成交量 / 5日平均成交量
        avg_volume_5 = df['volume'].rolling(window=5, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / avg_volume_5.shift(1)
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # 保留2位小數
        for col in ['ma5', 'ma10', 'ma20', 'volume_ratio']:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        return df
    
    @staticmethod
    def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """
        智能隨機休眠（Jitter）
        
        防封禁策略：模擬人類行為的隨機延遲
        在請求之間加入不規則的等待時間
        """
        sleep_time = random.uniform(min_seconds, max_seconds)
        logger.debug(f"隨機休眠 {sleep_time:.2f} 秒...")
        time.sleep(sleep_time)


class DataFetcherManager:
    """
    數據源策略管理器
    
    職責：
    1. 管理多個數據源（按優先級排序）
    2. 自動故障切換（Failover）
    3. 提供統一的數據獲取介面
    
    切換策略：
    - 優先使用高優先級數據源
    - 失敗後自動切換到下一個
    - 所有數據源都失敗時拋出異常
    """
    
    def __init__(self, fetchers: Optional[List[BaseFetcher]] = None):
        """
        初始化管理器
        
        Args:
            fetchers: 數據源列表（可選，默認按優先級自動建立）
        """
        self._fetchers: List[BaseFetcher] = []
        
        if fetchers:
            # 按優先級排序
            self._fetchers = sorted(fetchers, key=lambda f: f.priority)
        else:
            # 默認數據源將在首次使用時延遲載入
            self._init_default_fetchers()
    
    def _init_default_fetchers(self) -> None:
        """
        初始化默認數據源列表
        
        優先級動態調整邏輯：
        - 如果配置了 TUSHARE_TOKEN：Tushare 優先級提升為 0（最高）
        - 否則按默認優先級：
          0. EfinanceFetcher (Priority 0) - 最高優先級
          1. AkshareFetcher (Priority 1)
          2. PytdxFetcher (Priority 2) - 通達信
          2. TushareFetcher (Priority 2)
          3. BaostockFetcher (Priority 3)
          4. YfinanceFetcher (Priority 4)
        """
        from .efinance_fetcher import EfinanceFetcher
        from .akshare_fetcher import AkshareFetcher
        from .tushare_fetcher import TushareFetcher
        from .pytdx_fetcher import PytdxFetcher
        from .baostock_fetcher import BaostockFetcher
        from .yfinance_fetcher import YfinanceFetcher
        from src.config import get_config

        config = get_config()

        # 建立所有數據源實例（優先級在各 Fetcher 的 __init__ 中確定）
        efinance = EfinanceFetcher()
        akshare = AkshareFetcher()
        tushare = TushareFetcher()  # 會根據 Token 配置自動調整優先級
        pytdx = PytdxFetcher()      # 通達信數據源
        baostock = BaostockFetcher()
        yfinance = YfinanceFetcher()

        # 初始化數據源列表
        self._fetchers = [
            efinance,
            akshare,
            tushare,
            pytdx,
            baostock,
            yfinance,
        ]

        # 按優先級排序（Tushare 如果配置了 Token 且初始化成功，優先級為 0）
        self._fetchers.sort(key=lambda f: f.priority)

        # 構建優先級說明
        priority_info = ", ".join([f"{f.name}(P{f.priority})" for f in self._fetchers])
        logger.info(f"已初始化 {len(self._fetchers)} 個數據源（按優先級）: {priority_info}")
    
    def add_fetcher(self, fetcher: BaseFetcher) -> None:
        """添加數據源並重新排序"""
        self._fetchers.append(fetcher)
        self._fetchers.sort(key=lambda f: f.priority)
    
    def get_daily_data(
        self, 
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> Tuple[pd.DataFrame, str]:
        """
        獲取日線數據（自動切換數據源）
        
        故障切換策略：
        1. 從最高優先級數據源開始嘗試
        2. 捕獲異常後自動切換到下一個
        3. 記錄每個數據源的失敗原因
        4. 所有數據源失敗後拋出詳細異常
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            days: 獲取天數
            
        Returns:
            Tuple[DataFrame, str]: (數據, 成功的數據源名稱)
            
        Raises:
            DataFetchError: 所有數據源都失敗時拋出
        """
        errors = []
        
        for fetcher in self._fetchers:
            try:
                logger.info(f"嘗試使用 [{fetcher.name}] 獲取 {stock_code}...")
                df = fetcher.get_daily_data(
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    days=days
                )
                
                if df is not None and not df.empty:
                    logger.info(f"[{fetcher.name}] 成功獲取 {stock_code}")
                    return df, fetcher.name
                    
            except Exception as e:
                error_msg = f"[{fetcher.name}] 失敗: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                # 繼續嘗試下一個數據源
                continue
        
        # 所有數據源都失敗
        error_summary = f"所有數據源獲取 {stock_code} 失敗:\n" + "\n".join(errors)
        logger.error(error_summary)
        raise DataFetchError(error_summary)
    
    @property
    def available_fetchers(self) -> List[str]:
        """返回可用數據源名稱列表"""
        return [f.name for f in self._fetchers]
    
    def prefetch_realtime_quotes(self, stock_codes: List[str]) -> int:
        """
        批量預取即時行情數據（在分析開始前調用）
        
        策略：
        1. 檢查優先級中是否包含全量拉取數據源（efinance/akshare_em）
        2. 如果不包含，跳過預取（新浪/騰訊是單股票查詢，無需預取）
        3. 如果自選股數量 >= 5 且使用全量數據源，則預取填充快取
        
        這樣做的好處：
        - 使用新浪/騰訊時：每隻股票獨立查詢，無全量拉取問題
        - 使用 efinance/東財時：預取一次，後續快取命中
        
        Args:
            stock_codes: 待分析的股票代碼列表
            
        Returns:
            預取的股票數量（0 表示跳過預取）
        """
        from src.config import get_config
        
        config = get_config()
        
        # 如果即時行情被禁用，跳過預取
        if not config.enable_realtime_quote:
            logger.debug("[預取] 即時行情功能已禁用，跳過預取")
            return 0
        
        # 檢查優先級中是否包含全量拉取數據源
        # 注意：新增全量介面（如 tushare_realtime）時需同步更新此列表
        # 全量介面特徵：一次 API 調用拉取全市場 5000+ 股票數據
        priority = config.realtime_source_priority.lower()
        bulk_sources = ['efinance', 'akshare_em', 'tushare']  # 全量介面列表
        
        # 如果優先級中前兩個都不是全量數據源，跳過預取
        # 因為新浪/騰訊是單股票查詢，不需要預取
        priority_list = [s.strip() for s in priority.split(',')]
        first_bulk_source_index = None
        for i, source in enumerate(priority_list):
            if source in bulk_sources:
                first_bulk_source_index = i
                break
        
        # 如果沒有全量數據源，或者全量數據源排在第 3 位之後，跳過預取
        if first_bulk_source_index is None or first_bulk_source_index >= 2:
            logger.info(f"[預取] 當前優先級使用輕量級數據源(sina/tencent)，無需預取")
            return 0
        
        # 如果股票數量少於 5 個，不進行批量預取（逐個查詢更高效）
        if len(stock_codes) < 5:
            logger.info(f"[預取] 股票數量 {len(stock_codes)} < 5，跳過批量預取")
            return 0
        
        logger.info(f"[預取] 開始批量預取即時行情，共 {len(stock_codes)} 隻股票...")
        
        # 嘗試通過 efinance 或 akshare 預取
        # 只需要調用一次 get_realtime_quote，快取機制會自動拉取全市場數據
        try:
            # 用第一隻股票觸發全量拉取
            first_code = stock_codes[0]
            quote = self.get_realtime_quote(first_code)
            
            if quote:
                logger.info(f"[預取] 批量預取完成，快取已填充")
                return len(stock_codes)
            else:
                logger.warning(f"[預取] 批量預取失敗，將使用逐個查詢模式")
                return 0
                
        except Exception as e:
            logger.error(f"[預取] 批量預取異常: {e}")
            return 0
    
    def get_realtime_quote(self, stock_code: str):
        """
        獲取即時行情數據（自動故障切換）
        
        故障切換策略（按配置的優先級）：
        1. 美股：使用 YfinanceFetcher.get_realtime_quote()
        2. EfinanceFetcher.get_realtime_quote()
        3. AkshareFetcher.get_realtime_quote(source="em")  - 東財
        4. AkshareFetcher.get_realtime_quote(source="sina") - 新浪
        5. AkshareFetcher.get_realtime_quote(source="tencent") - 騰訊
        6. 返回 None（降級兜底）
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            UnifiedRealtimeQuote 對象，所有數據源都失敗則返回 None
        """
        from .realtime_types import get_realtime_circuit_breaker
        from .akshare_fetcher import _is_us_code
        from src.config import get_config
        
        config = get_config()
        
        # 如果即時行情功能被禁用，直接返回 None
        if not config.enable_realtime_quote:
            logger.debug(f"[即時行情] 功能已禁用，跳過 {stock_code}")
            return None
        
        # 美股單獨處理，使用 YfinanceFetcher
        if _is_us_code(stock_code):
            for fetcher in self._fetchers:
                if fetcher.name == "YfinanceFetcher":
                    if hasattr(fetcher, 'get_realtime_quote'):
                        try:
                            quote = fetcher.get_realtime_quote(stock_code)
                            if quote is not None:
                                logger.info(f"[即時行情] 美股 {stock_code} 成功獲取 (來源: yfinance)")
                                return quote
                        except Exception as e:
                            logger.warning(f"[即時行情] 美股 {stock_code} 獲取失敗: {e}")
                    break
            logger.warning(f"[即時行情] 美股 {stock_code} 無可用數據源")
            return None
        
        # 獲取配置的數據源優先級
        source_priority = config.realtime_source_priority.split(',')
        
        errors = []
        
        for source in source_priority:
            source = source.strip().lower()
            
            try:
                quote = None
                
                if source == "efinance":
                    # 嘗試 EfinanceFetcher
                    for fetcher in self._fetchers:
                        if fetcher.name == "EfinanceFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code)
                            break
                
                elif source == "akshare_em":
                    # 嘗試 AkshareFetcher 東財數據源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="em")
                            break
                
                elif source == "akshare_sina":
                    # 嘗試 AkshareFetcher 新浪數據源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="sina")
                            break
                
                elif source in ("tencent", "akshare_qq"):
                    # 嘗試 AkshareFetcher 騰訊數據源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="tencent")
                            break
                
                elif source == "tushare":
                    # 嘗試 TushareFetcher（需要 Tushare Pro 積分）
                    for fetcher in self._fetchers:
                        if fetcher.name == "TushareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code)
                            break
                
                if quote is not None and quote.has_basic_data():
                    logger.info(f"[即時行情] {stock_code} 成功獲取 (來源: {source})")
                    return quote
                    
            except Exception as e:
                error_msg = f"[{source}] 失敗: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue
        
        # 所有數據源都失敗，返回 None（降級兜底）
        if errors:
            logger.warning(f"[即時行情] {stock_code} 所有數據源均失敗，降級處理: {'; '.join(errors)}")
        else:
            logger.warning(f"[即時行情] {stock_code} 無可用數據源")
        
        return None
    
    def get_chip_distribution(self, stock_code: str):
        """
        獲取籌碼分佈數據（帶熔斷和多數據源降級）

        策略：
        1. 檢查配置開關
        2. 檢查熔斷器狀態
        3. 依次嘗試多個數據源：AkshareFetcher -> TushareFetcher -> EfinanceFetcher
        4. 所有數據源失敗則返回 None（降級兜底）

        Args:
            stock_code: 股票代碼

        Returns:
            ChipDistribution 對象，失敗則返回 None
        """
        from .realtime_types import get_chip_circuit_breaker
        from src.config import get_config

        config = get_config()

        # 如果籌碼分佈功能被禁用，直接返回 None
        if not config.enable_chip_distribution:
            logger.debug(f"[籌碼分佈] 功能已禁用，跳過 {stock_code}")
            return None

        circuit_breaker = get_chip_circuit_breaker()

        # 定義籌碼數據源優先級列表
        chip_sources = [
            ("AkshareFetcher", "akshare_chip"),
            ("TushareFetcher", "tushare_chip"),
            ("EfinanceFetcher", "efinance_chip"),
        ]

        for fetcher_name, source_key in chip_sources:
            # 檢查熔斷器狀態
            if not circuit_breaker.is_available(source_key):
                logger.debug(f"[熔斷] {fetcher_name} 籌碼介面處於熔斷狀態，嘗試下一個")
                continue

            try:
                for fetcher in self._fetchers:
                    if fetcher.name == fetcher_name:
                        if hasattr(fetcher, 'get_chip_distribution'):
                            chip = fetcher.get_chip_distribution(stock_code)
                            if chip is not None:
                                circuit_breaker.record_success(source_key)
                                logger.info(f"[籌碼分佈] {stock_code} 成功獲取 (來源: {fetcher_name})")
                                return chip
                        break
            except Exception as e:
                logger.warning(f"[籌碼分佈] {fetcher_name} 獲取 {stock_code} 失敗: {e}")
                circuit_breaker.record_failure(source_key, str(e))
                continue

        logger.warning(f"[籌碼分佈] {stock_code} 所有數據源均失敗")
        return None

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        獲取股票中文名稱（自動切換數據源）
        
        嘗試從多個數據源獲取股票名稱：
        1. 先從即時行情快取中獲取（如果有）
        2. 依次嘗試各個數據源的 get_stock_name 方法
        3. 最後嘗試讓大模型通過搜尋獲取（需要外部調用）
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票中文名稱，所有數據源都失敗則返回 None
        """
        # 1. 先檢查快取
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 初始化快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        # 2. 嘗試從即時行情中獲取（最快）
        quote = self.get_realtime_quote(stock_code)
        if quote and hasattr(quote, 'name') and quote.name:
            name = quote.name
            self._stock_name_cache[stock_code] = name
            logger.info(f"[股票名稱] 從即時行情獲取: {stock_code} -> {name}")
            return name
        
        # 3. 依次嘗試各個數據源
        for fetcher in self._fetchers:
            if hasattr(fetcher, 'get_stock_name'):
                try:
                    name = fetcher.get_stock_name(stock_code)
                    if name:
                        self._stock_name_cache[stock_code] = name
                        logger.info(f"[股票名稱] 從 {fetcher.name} 獲取: {stock_code} -> {name}")
                        return name
                except Exception as e:
                    logger.debug(f"[股票名稱] {fetcher.name} 獲取失敗: {e}")
                    continue
        
        # 4. 所有數據源都失敗
        logger.warning(f"[股票名稱] 所有數據源都無法獲取 {stock_code} 的名稱")
        return None

    def batch_get_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """
        批量獲取股票中文名稱
        
        先嘗試從支持批量查詢的數據源獲取股票列表，
        然後再逐個查詢缺失的股票名稱。
        
        Args:
            stock_codes: 股票代碼列表
            
        Returns:
            {股票代碼: 股票名稱} 字典
        """
        result = {}
        missing_codes = set(stock_codes)
        
        # 1. 先檢査快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        for code in stock_codes:
            if code in self._stock_name_cache:
                result[code] = self._stock_name_cache[code]
                missing_codes.discard(code)
        
        if not missing_codes:
            return result
        
        # 2. 嘗試批量獲取股票列表
        for fetcher in self._fetchers:
            if hasattr(fetcher, 'get_stock_list') and missing_codes:
                try:
                    stock_list = fetcher.get_stock_list()
                    if stock_list is not None and not stock_list.empty:
                        for _, row in stock_list.iterrows():
                            code = row.get('code')
                            name = row.get('name')
                            if code and name:
                                self._stock_name_cache[code] = name
                                if code in missing_codes:
                                    result[code] = name
                                    missing_codes.discard(code)
                        
                        if not missing_codes:
                            break
                        
                        logger.info(f"[股票名稱] 從 {fetcher.name} 批量獲取完成，剩餘 {len(missing_codes)} 個待查")
                except Exception as e:
                    logger.debug(f"[股票名稱] {fetcher.name} 批量獲取失敗: {e}")
                    continue
        
        # 3. 逐個獲取剩餘的
        for code in list(missing_codes):
            name = self.get_stock_name(code)
            if name:
                result[code] = name
                missing_codes.discard(code)
        
        logger.info(f"[股票名稱] 批量獲取完成，成功 {len(result)}/{len(stock_codes)}")
        return result

    def get_main_indices(self) -> List[Dict[str, Any]]:
        """獲取主要指數即時行情（自動切換數據源）"""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_main_indices()
                if data:
                    logger.info(f"[{fetcher.name}] 獲取指數行情成功")
                    return data
            except Exception as e:
                logger.warning(f"[{fetcher.name}] 獲取指數行情失敗: {e}")
                continue
        return []

    def get_market_stats(self) -> Dict[str, Any]:
        """獲取市場漲跌統計（自動切換數據源）"""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_market_stats()
                if data:
                    logger.info(f"[{fetcher.name}] 獲取市場統計成功")
                    return data
            except Exception as e:
                logger.warning(f"[{fetcher.name}] 獲取市場統計失敗: {e}")
                continue
        return {}

    def get_sector_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """獲取板塊漲跌榜（自動切換數據源）"""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_sector_rankings(n)
                if data:
                    logger.info(f"[{fetcher.name}] 獲取板塊榜單成功")
                    return data
            except Exception as e:
                logger.warning(f"[{fetcher.name}] 獲取板塊榜單失敗: {e}")
                continue
        return [], []
