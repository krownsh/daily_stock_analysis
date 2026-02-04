import logging
import os
from data_provider.finmind_fetcher import FinMindFetcher
import pandas as pd

def test_finmind():
    logging.basicConfig(level=logging.INFO)
    fm = FinMindFetcher()
    
    stock_code = "2330"
    # 使用 2023 年的數據確保有資料
    start_date = "2023-11-01"
    end_date = "2023-11-10"
    
    print(f"Testing FinMind for {stock_code} from {start_date} to {end_date}")
    
    # 1. 測試三大法人
    print("\n1. Testing Institutional Investors...")
    try:
        df = fm.dl.taiwan_stock_institutional_investors(
            stock_id=stock_code,
            start_date=start_date,
            end_date=end_date
        )
        print("Columns:", df.columns.tolist())
        print(df.head())
    except Exception as e:
        print(f"Error 1: {e}")
        
    # 2. 測試融資融券
    print("\n2. Testing Margin Trading...")
    try:
        df = fm.dl.taiwan_stock_margin_purchase_short_sale(
            stock_id=stock_code,
            start_date=start_date,
            end_date=end_date
        )
        print("Columns:", df.columns.tolist())
        print(df.head())
    except Exception as e:
        print(f"Error 2: {e}")

if __name__ == "__main__":
    test_finmind()
