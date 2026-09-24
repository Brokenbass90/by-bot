#!/usr/bin/env python3
"""kalibrovka.py — проверка ЛИНЕЙКИ, а не стратегии.

ЗАЧЕМ. 23 сентября судья назвал находкой S_OBOROT_TOLCHOK (p ровно 0.0100
при пороге 0.01), а нетронутое окно её убило. Один такой случай — ещё не
улика: при шести проверках порог 0.01 обязан иногда срабатывать вхолостую.
Но проверить это надо числом, а не рассуждением.

ДВА РЕЖИМА, И ОНИ ОТВЕЧАЮТ НА РАЗНЫЕ ВОПРОСЫ.

  --rezhim peremeshat   (по умолчанию) ЭТО НОЛЬ.
      Доходности каждой бумаги перемешиваются независимо. Рвётся всё:
      и связь между бумагами, и собственная память бумаги. Эджа в таких
      данных нет никакого. Сколько раз судья скажет «находка» — это и есть
      его честная доля ложных тревог. Обещано около 1% при пороге t ≥ 2.5.

  --rezhim sdvig        ЭТО НЕ НОЛЬ, а РАЗБОРКА ЭДЖА.
      Доходности каждой бумаги прокручиваются по кругу. Связь между
      бумагами рвётся, а СОБСТВЕННАЯ память бумаги остаётся. Если сигнал
      и здесь зарабатывает — значит, он берёт не отношение бумаг друг к
      другу, а инерцию каждой по отдельности. Это не приговор сигналу:
      инерция отдельной бумаги — настоящий эффект, который снимается
      настоящими деньгами. Это уточнение того, ЧТО именно он снимает.

Путать эти два режима нельзя: на сдвинутых данных высокий t — ожидаемое
поведение моментум-сигнала, а не ложь судьи.

    python3 kalibrovka.py --signal KR_SILA_K_BTC_LS --povtorov 200
    python3 kalibrovka.py --signal KR_SILA_K_BTC_LS --povtorov 50 --rezhim sdvig
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
PROGON = DIR / "begun_portfel.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", required=True)
    ap.add_argument("--povtorov", type=int, default=200)
    ap.add_argument("--porog_t", type=float, default=2.5)
    ap.add_argument("--min_neff", type=float, default=20.0)
    ap.add_argument("--rezhim", choices=("peremeshat", "sdvig"), default="peremeshat")
    ap.add_argument("--ot", type=int, default=1, help="с какого зерна начать: прогоны идут частями")
    a = ap.parse_args()
    import portfeli
    if a.signal not in portfeli.SIGNALY:
        print("нет такого сигнала"); return 1
    out = DIR / f"rezultaty/KALIBROVKA_{a.signal}_{a.rezhim}.json"
    syroe = out.with_suffix(".jsonl"); out.parent.mkdir(exist_ok=True)
    bylo = {}
    if syroe.exists():
        for ln in syroe.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r_ = json.loads(ln); bylo[r_["seed"]] = r_
    ts, nahodok, malo, upalo = [], 0, 0, 0
    t0 = time.time()
    chto = ("НОЛЬ: данных без всякого эджа" if a.rezhim == "peremeshat"
            else "РАЗБОРКА: связь между бумагами порвана, инерция каждой сохранена")
    print(f"КАЛИБРОВКА по сигналу {a.signal}: {a.povtorov} прогонов")
    print(f"  режим {a.rezhim} — {chto}")
    print(f"  порог находки: t ≥ {a.porog_t}, n_eff ≥ {a.min_neff}")
    for i in range(a.ot, a.ot + a.povtorov):
        if i in bylo:
            continue
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            vyh = f.name
        par = json.dumps({"signal": a.signal, "etap": "discovery",
                          "kalibrovka": i, "kalibrovka_rezhim": a.rezhim})
        r = subprocess.run([sys.executable, str(PROGON), "--param", par, "--vyhod", vyh],
                           capture_output=True, text=True)
        try:
            v = (json.loads(Path(vyh).read_text()).get("okna") or {}).get("VSE") or {}
        except Exception:
            v = {}
        Path(vyh).unlink(missing_ok=True)
        zap = {"seed": i, "t": v.get("t"), "edge": v.get("edge"), "n_eff": v.get("n_eff"),
               "upalo": bool(r.returncode != 0 or "t" not in v)}
        with syroe.open("a", encoding="utf-8") as f:
            f.write(json.dumps(zap, ensure_ascii=False) + "\n")
        if i % 10 == 0:
            print(f"    зерно {i}, {round(time.time() - t0)} с", flush=True)
    import numpy as np
    vse = {}
    for ln in syroe.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r_ = json.loads(ln); vse[r_["seed"]] = r_
    for r_ in vse.values():
        if r_["upalo"] or r_["t"] is None:
            upalo += 1
        elif (r_["n_eff"] or 0) < a.min_neff:
            malo += 1
        else:
            ts.append(r_["t"])
            if r_["t"] >= a.porog_t:
                nahodok += 1
    a.povtorov = len(vse)
    ts = np.array(ts)
    rez = {"signal": a.signal, "rezhim": a.rezhim, "povtorov": a.povtorov, "porog_t": a.porog_t,
           "godnyh": int(len(ts)), "malo_dannyh": malo, "upalo": upalo,
           "nahodok": nahodok, "dolya_lozhnyh": (nahodok / len(ts)) if len(ts) else None,
           "t_srednee": float(ts.mean()) if len(ts) else None,
           "t_sko": float(ts.std(ddof=1)) if len(ts) > 1 else None,
           "t_95": float(np.quantile(ts, 0.95)) if len(ts) else None,
           "t_99": float(np.quantile(ts, 0.99)) if len(ts) else None}
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rez, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nИТОГ")
    print(f"  годных прогонов: {rez['godnyh']} (мало данных {malo}, упало {upalo})")
    if not len(ts):
        print("  считать нечего."); return 1
    print(f"  t: среднее {rez['t_srednee']:+.2f}, разброс {rez['t_sko']:.2f}")
    print(f"  95-й процентиль {rez['t_95']:+.2f}, 99-й {rez['t_99']:+.2f}")
    print(f"  ложных находок: {nahodok} из {len(ts)} = {100 * rez['dolya_lozhnyh']:.1f}%")
    if a.rezhim == "sdvig":
        print("  ЭТО НЕ ЛОЖНЫЕ ТРЕВОГИ. Высокий t здесь значит, что сигнал снимает")
        print("  инерцию каждой бумаги по отдельности, а не отношение бумаг друг к другу.")
    elif rez["dolya_lozhnyh"] <= 0.02:
        print("  ЛИНЕЙКА ЧЕСТНАЯ: порог ведёт себя как обещано.")
    else:
        print("  ЛИНЕЙКА ВРЁТ: порог пропускает больше, чем должен. Все измеренные t")
        print(f"  надо читать скромнее, а честный порог ближе к {rez['t_99']:.1f}.")
    print(f"  записано: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
