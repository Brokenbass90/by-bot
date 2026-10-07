#!/usr/bin/env python3
"""Проверка готовности B3 БЕЗ чтения исходов: замки, конфиг, наличие потоков, ЧИСЛО сделок по ногам/сгибам (не R),
метки режима, отсутствие квитанции. R не суммируется и не печатается. Выход: READY / BLOCKED_* ."""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wf as W, replay as P, rezhim_v1 as RV

def main():
    prich = []
    if W.KV.exists(): prich.append("квитанция B3 уже есть (судья потрачен)")
    if not RV.proverit(): prich.append("замок REZHIM_V1 не сходится")
    konf_b = W.KONF.read_bytes(); konf = json.loads(konf_b); ksha = hashlib.sha256(konf_b).hexdigest()
    if ksha != "9b65e28c2d283f2cdf1e4ab17d95cc46a7afe672fdf9d72085685a90d4f2256f": prich.append("B3_KONFIG изменён")
    try: tr = W.potoki(konf)
    except FileNotFoundError as e: tr = []; prich.append(str(e))
    metki = W.metki_v1(); bez = sum(1 for t in tr if metki.get(t["ts"] // P.H * P.H) is None)
    sch = {}
    for a, b, c in konf["sgiby"]:
        s0, s1, s2 = W.ms(a), W.ms(b), W.ms(c)
        for leg in konf["nogi"]:
            sch.setdefault(leg, []).append(dict(train_zakrytyh=sum(1 for t in tr if t["leg"] == leg and s0 <= t["ts"] and W.vyhod(t) <= s1),
                                               test=sum(1 for t in tr if t["leg"] == leg and s1 <= t["ts"] < s2)))
    out = dict(status="READY" if not prich else "BLOCKED", prichiny=prich, konfig_sha256=ksha, sdelok=len(tr),
               sdelok_bez_metki_rezhima=bez, po_nogam_i_sgibam=sch)
    print(json.dumps(out, ensure_ascii=False, indent=1)); return 0 if not prich else 1

if __name__ == "__main__":
    sys.exit(main())
