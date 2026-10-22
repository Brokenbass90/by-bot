import os, re, json, subprocess, time
ROOT='.'
SKIP={'.venv','.venv-research','archive','_to_delete','backtest_runs','backtest_archive','tmp','tmp_codex_sync','__pycache__','node_modules','.git','signal_copy','pytest-cache-files-qjinodvv','runtime','logs','data','data_in','state','baselines','_snimki','reports','docs','share_main_strategy','_dlya_deepseek'}
EXT_TXT=('.py','.json','.yaml','.yml','.sh','.command','.service','.timer','.toml','.cfg','.ini','.txt')
mods=[]; texts={}
for dp, dn, fn in os.walk(ROOT):
    rel=os.path.relpath(dp,ROOT)
    parts=rel.split(os.sep)
    if parts[0] in SKIP or any(p in SKIP for p in parts): dn[:]=[]; continue
    if rel.startswith('research_lab') and len(parts)>1 and parts[1] in ('data','results','prereg','os2'):
        if parts[1] in ('data','results'): dn[:]=[]; continue
    dn[:]=[d for d in dn if d not in SKIP]
    for f in fn:
        p=os.path.normpath(os.path.join(dp,f))
        if f.startswith('.env') or 'config' in f.lower() and f.endswith(('.env','.local')): continue
        if f.endswith(EXT_TXT):
            try:
                if os.path.getsize(p) < 3_000_000: texts[p]=open(p,encoding='utf-8',errors='ignore').read()
            except Exception: pass
        if f.endswith('.py'): mods.append(p)
# plus Mac runtime entrypoints from owner's screen list + HUKI
runtime_entry={'kripto_atlas_sbor','kity_m3_ten','yadro','breakout_ten','poly_sbor','ten_sila','ten','bounce_ten','kity_bybit_ten','storozh','edinstvennyy_zapusk','ten_pump4'}
try: runtime_entry|=set(json.load(open('research_lab/fabrika/HUKI.json')))
except Exception: pass
import collections
idx=collections.defaultdict(set)
for p,t in texts.items():
    for tok in set(re.findall(r'[A-Za-z0-9_]+', t)): idx[tok].add(p)
out=[]
for m in mods:
    stem=os.path.splitext(os.path.basename(m))[0]
    if stem in ('__init__','conftest'): continue
    refs=[p for p in idx.get(stem,()) if p!=m]
    tests=[p for p in refs if os.path.basename(p).startswith('test_')]
    other=[p for p in refs if p not in tests]
    has_main='__main__' in texts.get(m,'')
    out.append(dict(m=m, refs=len(other), tests=len(tests), main=has_main, runtime=stem in runtime_entry, size=os.path.getsize(m), ref_files=sorted(other)[:5]))
json.dump(out, open('tmp/inventar_koda.json','w'), ensure_ascii=False)
dead=[o for o in out if o['refs']==0 and not o['runtime'] and not o['m'].startswith('tests')]
print('модулей', len(out), 'без вызывающих (кроме тестов)', len(dead))
import collections
print(collections.Counter(o['m'].split(os.sep)[0] if os.sep in o['m'] else '.' for o in dead))
