import efinance as ef
import pandas as pd

def fast_check_ef_tw():
    print("Fetching all realtime quotes...")
    # 只獲取部分列以加快速度
    df = ef.stock.get_realtime_quotes()
    if df is not None:
        print(f"Total stocks: {len(df)}")
        # 尋找包含 2330 的行
        res = df[df['股票代碼'].str.contains('2330', na=False)]
        print(f"Rows with 2330:\n{res}")
        
        # 尋找名稱包含 '台積電'
        res_name = df[df['股票名稱'].str.contains('台積電', na=False)]
        print(f"Rows with 台積電:\n{res_name}")

if __name__ == "__main__":
    fast_check_ef_tw()
