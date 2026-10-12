#!/usr/bin/env python3
"""kity_bybit_paritet.py — условие C2: независимый пересчёт Codex против сигнала тени KITY_BYBIT.
Интерфейс для Codex (его код пишется независимо, НЕ импортирует kity_bybit_ten.py):
  вход  — те же файлы: data/kity_bybit_ten/<d>/snimok_2355.json (топ-50 по oi_usd, ничьи — по символу не нужны: сортировка -oi),
          архивы public.bybit.com/trading/<SYM>/<SYM><d−1>.csv.gz (sha256 каждого — в potok.json тени), дневные свечи Bybit;
  правило — доля агрессивных покупок дня d−1 = Σ notional(side=Buy) / Σ notional, notional = foreignNotional, иначе size×price;
          монета участвует, если есть архив и ≥ 60 закрытых дневных свечей, последняя = d−1; k = n//10;
          long = k наибольших, short = k наименьших (сортировка по (значение, символ));
  выход — JSON {"d": "...", "vse_priznaki": {SYM: доля}, "long": [SYM...], "short": [SYM...], "arhiv_sha256": {SYM: sha}}.
Сравнение: корзины совпадают 100% (как множества), |доля_codex − доля_тени| < 1e-6 по всем общим монетам, множества монет равны,
sha архивов совпадают. Любое расхождение → C2 FAIL с перечнем.
    .venv/bin/python research_lab/kity_bybit_paritet.py 2026-10-15 путь/к/codex.json
"""
import json, sys
from pathlib import Path
D = Path(__file__).resolve().parent / "data" / "kity_bybit_ten"
TOL = 1e-6


def main(d, put):
    ten = json.loads((D / d / "signal.json").read_text()); pot = json.loads((D / d / "potok.json").read_text())
    cx = json.loads(Path(put).read_text()); prob = []
    if cx.get("d") != d: prob.append(f"дата {cx.get('d')} != {d}")
    a, b = ten["vse_priznaki"], cx["vse_priznaki"]
    if set(a) != set(b): prob.append(f"монеты: только тень {sorted(set(a) - set(b))}, только codex {sorted(set(b) - set(a))}")
    dif = {s: abs(a[s] - b[s]) for s in set(a) & set(b)}
    plohie = {s: v for s, v in dif.items() if v >= TOL}
    if plohie: prob.append(f"доля ≥ 1e-6: {plohie}")
    for st in ("long", "short"):
        mt = {x["s"] for x in ten[st]}; mc = set(cx[st])
        if mt != mc: prob.append(f"{st}: тень {sorted(mt)} codex {sorted(mc)}")
    sha_t = {s: v["sha256"] for s, v in pot.items() if isinstance(v, dict)}
    raz = [s for s in cx.get("arhiv_sha256", {}) if s in sha_t and sha_t[s] != cx["arhiv_sha256"][s]]
    if raz: prob.append(f"sha архивов различаются: {raz}")
    if not cx.get("arhiv_sha256"): prob.append("codex не приложил sha архивов")
    rez = dict(d=d, status="C2_PASS" if not prob else "C2_FAIL", maks_raznica=max(dif.values()) if dif else None,
               monet=len(a), problemy=prob)
    (D / d / "paritet_C2.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1)); return 0 if not prob else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
