import json, os, sys
D="research_lab/data/movers_5m"; OUT="research_lab/data/daily_338.json"
files=sorted(os.listdir(D))
lo,hi=int(sys.argv[1]),int(sys.argv[2])
acc=json.load(open(OUT)) if os.path.exists(OUT) else {}
for fn in files[lo:hi]:
    s=fn.replace(".json","")
    if s in acc: continue
    try: rows=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(rows)<300: continue
    d={}
    for r in rows:
        day=r[0]//86400000
        d[day]=r[4]          # последний close в сутках
    if len(d)>=60: acc[s]={str(k):v for k,v in d.items()}
json.dump(acc, open(OUT,"w"))
print(f"обработано до {hi}, символов накоплено: {len(acc)}")
