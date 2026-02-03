import efinance as ef
import pandas as pd

def check_cols():
    df = ef.stock.get_realtime_quotes()
    print(f"Columns: {df.columns.tolist()}")

if __name__ == "__main__":
    check_cols()
