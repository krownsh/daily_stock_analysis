# -*- coding: utf-8 -*-
"""
===================================
FinMindFetcher - 台灣市場專業數據源
===================================

數據來源：FinMind API
特點：提供三大法人買賣超、融資融券、月營收等台股核心籌碼與基本面數據。
"""

import logging
import os
import pandas as pd
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from .base import BaseFetcher, DataFetchError
from .realtime_types import UnifiedRealtimeQuote

logger = logging.getLogger(__name__)

class FinMindFetcher:
    """
    FinMind 數據抓取器
    
    負責補齊 yfinance 缺失的台股籌碼面與營收數據。
    使用官方 SDK: https://github.com/FinMind/FinMind
    """
    
    def __init__(self, api_token: Optional[str] = None):
        """
        初始化 FinMindFetcher
        
        Args:
            api_token: FinMind API Token (可透過環境變數 FINMIND_API_KEY 配置)
        """
        from FinMind.data import DataLoader
        self.api_token = api_token or os.getenv("FINMIND_API_KEY", "")
        self.dl = DataLoader()
        if self.api_token:
            self.dl.login_by_token(api_token=self.api_token)
            logger.info("FinMind 已使用 Token 登入")
        else:
            logger.warning("FinMind 未配置 Token，將使用匿名存取（有頻率限制）")

    def fetch_institutional_investors(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """獲取三大法人買賣超"""
        try:
            df = self.dl.taiwan_stock_institutional_investors(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            if df.empty:
                return pd.DataFrame()
            
            # 轉換為每日加總 (外資、投信、自營商各自累加)
            # FinMind 'name' 欄位可能是: 'Foreign_Investor', 'Investment_Trust', 'Dealer_self', 'Dealer_Hedging'
            df['net_buy'] = df['buy'] - df['sell']
            
            # 建立透視表
            pivot_df = df.pivot_table(
                index='date', 
                columns='name', 
                values='net_buy', 
                aggfunc='sum'
            ).reset_index()
            
            # 欄位映射
            # 我們統一將自營商(自行買賣+避險)合併為 dealers_buy
            res_df = pd.DataFrame()
            res_df['date'] = pivot_df['date']
            
            if 'Foreign_Investor' in pivot_df.columns:
                res_df['foreign_buy'] = pivot_df['Foreign_Investor']
            
            if 'Investment_Trust' in pivot_df.columns:
                res_df['it_buy'] = pivot_df['Investment_Trust']
                
            dealers_cols = ['Dealer', 'Dealer_self', 'Dealer_Hedging']
            res_df['dealers_buy'] = 0.0
            for col in dealers_cols:
                if col in pivot_df.columns:
                    res_df['dealers_buy'] += pivot_df[col].fillna(0.0)
            
            return res_df
        except Exception as e:
            logger.error(f"FinMind 獲取三大法人數據失敗 [{stock_code}]: {e}")
            return pd.DataFrame()

    def fetch_margin_trading(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """獲取融資融券數據"""
        try:
            df = self.dl.taiwan_stock_margin_purchase_short_sale(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            if df.empty:
                return pd.DataFrame()
            
            # FinMind 欄位: MarginPurchaseBuy, MarginPurchaseSell, ShortSaleBuy, ShortSaleSell 等
            # 我們需要的是每日的淨變動或餘額
            # 為簡化，我們取 MarginPurchaseBuy - MarginPurchaseSell 作為當日變動
            # 但資料庫設計是 margin_buy, short_buy，這裡記錄變動值
            df['margin_buy'] = df['MarginPurchaseBuy'] - df['MarginPurchaseSell']
            df['short_buy'] = df['ShortSaleBuy'] - df['ShortSaleSell']
            
            return df[['date', 'margin_buy', 'short_buy']]
        except Exception as e:
            logger.error(f"FinMind 獲取融資融券數據失敗 [{stock_code}]: {e}")
            return pd.DataFrame()

    def fetch_latest_revenue_yoy(self, stock_code: str) -> float:
        """獲取最近一個月的營收年增率 (%)"""
        try:
            # 抓取過去 15 個月的營收以確保能計算 YoY
            start_date = (datetime.now() - timedelta(days=450)).strftime("%Y-%m-%d")
            df = self.dl.taiwan_stock_month_revenue(
                stock_id=stock_code,
                start_date=start_date
            )
            if df.empty or len(df) < 13:
                return 0.0
            
            # 按年月排序（由新到舊）
            df = df.sort_values(['revenue_year', 'revenue_month'], ascending=False)
            
            # 最新營收
            latest = df.iloc[0]
            latest_val = latest['revenue']
            
            # 尋找去年前同月份的營收
            year_ago = df[(df['revenue_month'] == latest['revenue_month']) & 
                          (df['revenue_year'] == latest['revenue_year'] - 1)]
            
            if not year_ago.empty:
                year_ago_val = year_ago.iloc[0]['revenue']
                if year_ago_val > 0:
                    yoy = (latest_val - year_ago_val) / year_ago_val * 100
                    return round(yoy, 2)
            
            return 0.0
        except Exception as e:
            logger.error(f"FinMind 計算營收 YoY 失敗 [{stock_code}]: {e}")
            return 0.0

    def fetch_month_revenue(self, stock_code: str, start_date: str) -> pd.DataFrame:
        """獲取月營收數據"""
        try:
            df = self.dl.taiwan_stock_month_revenue(
                stock_id=stock_code,
                start_date=start_date
            )
            return df
        except Exception as e:
            logger.error(f"FinMind 獲取月營收失敗 [{stock_code}]: {e}")
            return pd.DataFrame()

    def augment_stock_data(self, main_df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        將主數據 (OHLCV) 與 FinMind 數據合併
        """
        if main_df.empty:
            return main_df
            
        start_date = main_df['date'].min()
        end_date = main_df['date'].max()
        
        # 抓取籌碼數據
        inst_df = self.fetch_institutional_investors(stock_code, start_date, end_date)
        margin_df = self.fetch_margin_trading(stock_code, start_date, end_date)
        
        # 合併
        res_df = main_df.copy()
        
        if not inst_df.empty:
            res_df = pd.merge(res_df, inst_df, on='date', how='left')
            
        if not margin_df.empty:
            res_df = pd.merge(res_df, margin_df, on='date', how='left')
            
        # 填充 NaN 為 0
        cols_to_fix = ['foreign_buy', 'it_buy', 'dealers_buy', 'margin_buy', 'short_buy']
        for col in cols_to_fix:
            if col in res_df.columns:
                res_df[col] = res_df[col].fillna(0.0)
            else:
                res_df[col] = 0.0
                
        # 補齊營收 YoY (對當下所有日期使用相同的最新營收 YoY)
        res_df['revenue_yoy'] = self.fetch_latest_revenue_yoy(stock_code)
        
        return res_df
