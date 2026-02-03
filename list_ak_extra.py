import akshare as ak

funcs = [f for f in dir(ak) if 'institutional' in f or 'margin' in f]
for f in sorted(funcs):
    print(f)
