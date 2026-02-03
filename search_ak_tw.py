import akshare as ak

def find_tw_in_ak():
    # 搜尋所有可能的函數，看哪一個能返回 2330
    # 或者是搜尋東財的海外市場
    print("Searching for 2330 in AkShare...")
    # 某些函數可能包含 'spot'
    spot_funcs = [f for f in dir(ak) if 'spot' in f]
    print(f"Checking {len(spot_funcs)} spot functions...")
    
    # 我們不實際執行所有函數，只看名字
    tw_related = [f for f in spot_funcs if 'tw' in f or 'taiwan' in f]
    print(f"TW related: {tw_related}")

if __name__ == "__main__":
    find_tw_in_ak()
