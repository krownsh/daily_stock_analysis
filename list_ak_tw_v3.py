import akshare as ak

print("Searching for functions related to Taiwan...")
all_funcs = [f for f in dir(ak) if 'tw' in f.lower() or 'taiwan' in f.lower()]
for f in sorted(all_funcs):
    print(f)
