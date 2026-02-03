import akshare as ak

def list_tw_funcs():
    tw_funcs = [f for f in dir(ak) if 'tw' in f.lower() or 'taiwan' in f.lower()]
    for f in sorted(tw_funcs):
        print(f)

if __name__ == "__main__":
    list_tw_funcs()
