import akshare as ak

def list_all_ak():
    all_funcs = dir(ak)
    # Search for anything that might be Taiwan or TSMC or 2330
    tw_related = [f for f in all_funcs if any(x in f.lower() for x in ['tw', 'taiwan', 'tse', 'otc', 'taipei'])]
    for f in sorted(tw_related):
        # Filter out some common ones
        if not f.startswith('_'):
             print(f)

if __name__ == "__main__":
    list_all_ak()
