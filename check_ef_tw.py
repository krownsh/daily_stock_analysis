import efinance as ef
import pandas as pd

def check_ef_tw():
    print("Fetching all realtime quotes from efinance...")
    df = ef.stock.get_realtime_quotes()
    # 台灣股票在東財的代碼通常是以 111. 或 116. 或 128. 開頭？
    # 或者名稱包含 台灣, 台積電 等
    tw_stocks = df[df['股票名稱'].str.contains('台積電|鴻海|聯發科', na=False)]
    print(f"Taiwan stocks found in efinance:\n{tw_stocks}")
    
    # 也可以嘗試搜尋
    # search_res = ef.stock.search_quote("2330")
    # print(f"Search result for 2330:\n{search_res}")

if __name__ == "__main__":
    check_ef_tw()
