#!/usr/bin/env python3
"""svodka_v1.py — ежедневная сводка владельцу (Factory V3, слой 0, «система общается со мной»). 13.10.2026. ТОЛЬКО ЧТЕНИЕ.
Собирает: денежные контуры (Alpaca — из отчёта Codex, KITY, Elder) → тени (storozh) → данные (Data QA) → реестр → календарь
→ что нужно от владельца. Пишет research_lab/data/svodka/<дата>.md и печатает. Никаких доходностей до вердиктов.

    python3 research_lab/factory_v3/svodka_v1.py
"""
import datetime as dt, glob, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; LAB = HERE.parent; ROOT = LAB.parent; D = LAB / "data"
CODEX = ROOT.parent / "bybit-bot-recovery-20260824"
sys.path.insert(0, str(HERE))
KALENDAR = [("2026-10-15", "KITY Bybit: первый четверг; квитанция C1 — пт после 00:05 UTC"),
            ("2026-10-19", "Атлас издержек: ≥ 7 суток → kripto_atlas_sbor.py --atlas"),
            ("2026-10-22", "KITY Bybit: второй четверг (C1/C2)"),
            ("2026-10-20", "Elder ETS2M_V2: окно 1 → --otsenit 1 (ориентир 20–25.10)"),
            ("2026-10-23", "Решение о канарейке KITY (≈)")]


def _hvost_stroki(p, n=40):
    try: return Path(p).read_text(errors="replace").splitlines()[-n:]
    except Exception: return []


def alpaca():
    f = sorted(glob.glob(str(CODEX / "reports" / "ALPACA_DYNAMIC_LIVE_READINESS_*.md")))
    if not f: return "нет доступа к отчёту Codex"
    txt = Path(f[-1]).read_text(errors="replace")
    zag = next((l.strip("# ").strip() for l in txt.splitlines() if l.startswith("## ")), "")
    st = re.findall(r"`([A-Z_]{6,}(?: / [A-Z_]{6,})?)`", txt[:4000])
    return f"{zag} — {st[0] if st else 'статус не найден'} ({Path(f[-1]).name})"


def kity():
    puls = [l for l in _hvost_stroki(D / "kity_bybit_ten.log") if "пульс" in l]
    kv = sorted(glob.glob(str(D / "kity_bybit_ten" / "*" / "kvitanciya_C1.json")))
    kvs = []
    for k in kv:
        try: kvs.append(f"{Path(k).parent.name}: {json.loads(Path(k).read_text()).get('status')}")
        except Exception: pass
    return (puls[-1][:120] if puls else "нет пульса") + (f"; квитанции: {', '.join(kvs)}" if kvs else "; квитанций C1 пока нет")


def elder():
    s = [l for l in _hvost_stroki(D / "yadro_ETS2M.log", 60) if "ishodov" in l]
    return s[-1].strip()[:160] if s else "нет данных"


def push_nuzhen():
    try:
        a = subprocess.run(["git", "-C", str(ROOT), "rev-list", "--count", "origin/research/fabrika-v1..research/fabrika-v1"],
                           capture_output=True, text=True, timeout=20).stdout.strip()
        return int(a or 0)
    except Exception:
        return None


def sobrat(segodnya=None):
    segodnya = segodnya or dt.datetime.now(dt.timezone.utc).date()
    st = {}
    try: st = json.loads((D / "storozh" / "OTCHET.json").read_text())
    except Exception: pass
    try:
        import data_qa_v1; qa = data_qa_v1.proverit_vse()
    except Exception as e: qa = dict(data_qa=dict(status=f"ошибка: {e}"))
    try:
        from reestr_v1 import Reestr; rs = Reestr().svodka()
    except Exception as e: rs = dict(oshibka=str(e))
    try:
        import sudi_v_reestr; from reestr_v1 import Reestr as _R
        _r = _R(); kan = sudi_v_reestr.gotovnost_kanareyki_kity(_r)
        prog = {g: v.get("kvitancii", [{}])[-1].get("status") for g, v in _r.sostoyanie()["gipotezy"].items()
                if any(k.get("vid") == "PROGRESS" for k in v.get("kvitancii", []))}
    except Exception as e: kan, prog = dict(oshibka=str(e)), {}
    try: kf = json.loads((D / "factory_v3" / "KONTROL_FERMY.json").read_text())
    except Exception: kf = dict(status="ещё не запускался")
    zh = st.get("zhurnaly", {}); plohie = {k: v["status"] for k, v in zh.items() if v.get("status") != "OK"}
    qa_plohie = {k: v["status"] for k, v in qa.items() if v.get("status") not in ("OK", "NET_DANNYH", "MALO")}
    izvestnye = {"likvidacii_bybit": "известно: сторона перевёрнута в старом файле, ждём сборщик V2 (Codex)"}
    nado = []
    p = push_nuzhen()
    if p: nado.append(f"`git push origin research/fabrika-v1` — локально впереди на {p} коммит(ов)")
    if kf.get("status") == "TREVOGA": nado.append("контроль фермы TREVOGA: " + "; ".join(kf.get("problemy", []))[:300])
    if plohie: nado.append("посмотреть тени: " + ", ".join(f"{k} {v}" for k, v in plohie.items()))
    nado += [f"данные {k}: {v}" for k, v in qa_plohie.items() if k not in izvestnye]
    blizko = [f"- {d}: {t}" for d, t in sorted(KALENDAR) if 0 <= (dt.date.fromisoformat(d) - segodnya).days <= 10]
    md = [f"# Сводка {segodnya.isoformat()}", "",
          "## Деньги",
          f"- **Alpaca:** {alpaca()}",
          f"- **KITY Bybit:** {kity()}",
          f"- **Elder ETS2M:** {elder()}",
          f"- **Канарейка KITY:** чистых недель (C1 и C2 PASS) {kan.get('chistyh_nedel')} из 2" + (" → ГОТОВО к досье" if kan.get('gotovo_k_dosie') else ""),
          f"- **До вердиктов теней (закрытых решений):** {prog}", "",
          "## Тени и сборщики",
          f"- живых по реестру: {sum(1 for v in zh.values() if v.get('status') == 'OK')} из {len(zh)}"
          + (f"; проблемы: {plohie}" if plohie else "; проблем нет") + f" (сторож {st.get('kogda', '—')})", "",
          "## Данные (Data QA V1)",
          *[f"- {k}: {v.get('status')}" + (f" — {izvestnye[k]}" if k in izvestnye else "") for k, v in qa.items()], "",
          "## Реестр экспериментов",
          f"- семей {rs.get('semey')} (KILL {rs.get('semey_kill')}), гипотезы {rs.get('gipotez')}, попыток {rs.get('popytok')}", "",
          f"- контроль фермы (раз в неделю): {kf.get('status')} {kf.get('kogda', '')}"
          + (f" — образцы {kf.get('obrazcy')}, мощность {kf.get('kalibrovka', {}).get('moshchnost')}" if kf.get('kogda') else ""), "",
          "## Ближайшие события", *(blizko or ["- в ближайшие 10 дней нет"]), "",
          "## Нужно от тебя", *([f"- {x}" for x in nado] or ["- ничего"])]
    out = "\n".join(md) + "\n"
    (D / "svodka").mkdir(parents=True, exist_ok=True)
    (D / "svodka" / f"{segodnya.isoformat()}.md").write_text(out)
    return out


if __name__ == "__main__":
    print(sobrat())
