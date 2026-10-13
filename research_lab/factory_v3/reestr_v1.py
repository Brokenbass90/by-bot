#!/usr/bin/env python3
"""reestr_v1.py — Experiment Registry V1 (Factory V3, слой 1). 13.10.2026.

Зачем: без учёта попыток ферма бэктестов и ИИ-исследователь превращаются в машину поиска случайных красивых кривых.
Реестр — единственная точка, через которую идут гипотеза → попытка → результат → статус.

Модель
  СЕМЬЯ       механизм (G6: baseline + не более одного претендента).
  ГИПОТЕЗА    конкретная форма механизма; статус NEW → SCREEN → TEST → SHADOW → CANARY → MONEY, либо KILL (терминально).
  ОКНО        данные с ролью: DEV (скрининг, бюджет попыток), CONFIRM (точная проверка, одна попытка на гипотезу),
              HOLDOUT (запрещено для любых попыток — только тени/будущее).
  ПОПЫТКА     регистрируется ДО результата: окно, стадия, sha спецификации, замороженные критерии.
              Результат принимается только к зарегистрированной попытке с тем же sha и только один раз.

Поправка на перебор: требуемый t на окне = Φ⁻¹(1 − α / (2·k)), k — число попыток, зарегистрированных на окне к моменту
результата (α = 0.05): k=1 → 1.96, k=10 → 2.81, k=100 → 3.48, k=1000 → 4.06.

Хранилище: append-only JSONL (по умолчанию research_lab/data/factory_v3/reestr_v1.jsonl), запись под flock.
Состояние = воспроизведение журнала; журнал ничего не удаляет.
"""
import datetime as dt, fcntl, hashlib, json, re, statistics
from pathlib import Path

PUT_PO_UMOLCHANIYU = Path(__file__).resolve().parents[1] / "data" / "factory_v3" / "reestr_v1.jsonl"
STADII = ["NEW", "SCREEN", "TEST", "SHADOW", "CANARY", "MONEY"]
TERMINAL = "KILL"
ROLI_OKON = {"DEV": "SCREEN", "CONFIRM": "TEST"}          # роль окна → единственная стадия, которой оно доступно
ALPHA = 0.05
NUZHEN_GO = {"CANARY", "MONEY"}                          # переходы, требующие письменного GO владельца


class OshibkaReestra(Exception):
    pass


def spec_sha(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def trebuemyy_t(k, alpha=ALPHA):
    k = max(1, int(k))
    return statistics.NormalDist().inv_cdf(1 - alpha / (2 * k))


def osnovy(text):
    return {w[:5] for w in re.findall(r"[a-zа-яё0-9]{4,}", (text or "").lower())}


class Reestr:
    def __init__(self, put=None):
        self.put = Path(put) if put else PUT_PO_UMOLCHANIYU
        self.put.parent.mkdir(parents=True, exist_ok=True)

    # ---------- журнал ----------
    def _sobytiya(self):
        if not self.put.exists():
            return []
        return [json.loads(l) for l in self.put.read_text().splitlines() if l.strip()]

    def _zapisat(self, sob):
        sob = dict(sob, kogda=sob.get("kogda") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        with open(self.put, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                self._proverit(sob, self.sostoyanie())          # проверка под замком против актуального состояния
                f.write(json.dumps(sob, ensure_ascii=False, sort_keys=True) + "\n"); f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return sob

    # ---------- состояние ----------
    def sostoyanie(self):
        S = dict(semi={}, gipotezy={}, okna={}, popytki={})
        for e in self._sobytiya():
            t = e["tip"]
            if t == "semya":
                S["semi"][e["id"]] = dict(e)
            elif t == "gipoteza":
                S["gipotezy"][e["id"]] = dict(e, status="NEW", istoriya=[])
            elif t == "okno":
                S["okna"][e["id"]] = dict(e)
            elif t == "popytka":
                S["popytki"][e["id"]] = dict(e, rezultat=None)
            elif t == "rezultat":
                S["popytki"][e["popytka"]]["rezultat"] = e
            elif t == "perehod":
                g = S["gipotezy"][e["gipoteza"]]; g["status"] = e["v"]; g["istoriya"].append(e)
            elif t == "nasledie":
                g = S["gipotezy"][e["gipoteza"]]; g["status"] = e["status"]; g["istoriya"].append(e)
            elif t == "semya_kill":
                S["semi"][e["semya"]]["status"] = TERMINAL; S["semi"][e["semya"]]["prichina_kill"] = e["prichina"]
        return S

    def popytok_na_okne(self, okno, S=None):
        S = S or self.sostoyanie()
        return sum(1 for p in S["popytki"].values() if p["okno"] == okno)

    # ---------- правила (единственное место) ----------
    def _proverit(self, e, S):
        t = e["tip"]
        if t == "semya":
            if e["id"] in S["semi"]: raise OshibkaReestra(f"семья {e['id']} уже есть")
        elif t == "gipoteza":
            if e["id"] in S["gipotezy"]: raise OshibkaReestra(f"гипотеза {e['id']} уже есть")
            if e["semya"] not in S["semi"]: raise OshibkaReestra(f"нет семьи {e['semya']}")
            if S["semi"][e["semya"]].get("status") == TERMINAL: raise OshibkaReestra(f"семья {e['semya']} закрыта (KILL)")
        elif t == "okno":
            if e["id"] in S["okna"]: raise OshibkaReestra(f"окно {e['id']} уже есть")
            if e["rol"] not in ("DEV", "CONFIRM", "HOLDOUT"): raise OshibkaReestra("роль окна: DEV / CONFIRM / HOLDOUT")
            if e["rol"] != "HOLDOUT" and int(e.get("byudzhet", 0)) < 1: raise OshibkaReestra("у окна нужен бюджет ≥ 1")
        elif t == "popytka":
            if e["id"] in S["popytki"]: raise OshibkaReestra(f"попытка {e['id']} уже есть")
            g = S["gipotezy"].get(e["gipoteza"]); o = S["okna"].get(e["okno"])
            if not g: raise OshibkaReestra(f"нет гипотезы {e['gipoteza']}")
            if not o: raise OshibkaReestra(f"нет окна {e['okno']}")
            if g["status"] == TERMINAL: raise OshibkaReestra("гипотеза в KILL — попытки запрещены")
            if o["rol"] == "HOLDOUT": raise OshibkaReestra(f"окно {o['id']} — HOLDOUT: попытки запрещены (только тени)")
            if ROLI_OKON[o["rol"]] != e["stadiya"]: raise OshibkaReestra(f"окно {o['rol']} доступно только стадии {ROLI_OKON[o['rol']]}")
            if g["status"] != e["stadiya"]: raise OshibkaReestra(f"гипотеза в {g['status']}, попытка стадии {e['stadiya']}")
            if self.popytok_na_okne(o["id"], S) >= int(o["byudzhet"]): raise OshibkaReestra(f"бюджет окна {o['id']} исчерпан")
            if o["rol"] == "CONFIRM" and any(p["gipoteza"] == g["id"] and p["okno"] == o["id"] for p in S["popytki"].values()):
                raise OshibkaReestra("на CONFIRM-окне у гипотезы одна попытка")
            if not isinstance(e.get("kriterii"), dict) or "min_n" not in e["kriterii"]:
                raise OshibkaReestra("критерии попытки обязательны и замораживаются при регистрации (min_n, znak)")
        elif t == "rezultat":
            p = S["popytki"].get(e["popytka"])
            if not p: raise OshibkaReestra("результат к незарегистрированной попытке не принимается")
            if p["rezultat"] is not None: raise OshibkaReestra("результат попытки уже записан — повтор запрещён")
            if e["spec_sha"] != p["spec_sha"]: raise OshibkaReestra("спецификация изменена после регистрации")
            konec = S["okna"][p["okno"]]["konec"]
            if e["kogda"][:10] <= konec: raise OshibkaReestra(f"окно {p['okno']} ещё не закончилось ({konec}) — результат рано")
        elif t == "perehod":
            g = S["gipotezy"].get(e["gipoteza"])
            if not g: raise OshibkaReestra("нет гипотезы")
            if g["status"] == TERMINAL: raise OshibkaReestra("KILL терминален")
            if e["v"] != TERMINAL:
                if STADII.index(e["v"]) != STADII.index(g["status"]) + 1: raise OshibkaReestra(f"{g['status']} → {e['v']}: только на одну стадию вперёд")
                if e["v"] in NUZHEN_GO and not e.get("owner_go"): raise OshibkaReestra(f"{e['v']} требует письменного GO владельца")
                if e["v"] in ("TEST", "SHADOW"):
                    nado = "SCREEN" if e["v"] == "TEST" else "TEST"
                    if not any(p["gipoteza"] == g["id"] and p["stadiya"] == nado and p["rezultat"] and p["rezultat"]["verdikt"] == "PASS"
                               for p in S["popytki"].values()):
                        raise OshibkaReestra(f"для {e['v']} нужна PASS-попытка стадии {nado}")
        elif t == "nasledie":
            g = S["gipotezy"].get(e["gipoteza"])
            if not g or g["istoriya"]: raise OshibkaReestra("наследие — только для новой гипотезы без истории")
            if e["status"] not in STADII + [TERMINAL] or not e.get("dokument"): raise OshibkaReestra("наследие: статус и документ-основание обязательны")
        elif t == "semya_kill":
            if e["semya"] not in S["semi"]: raise OshibkaReestra("нет семьи")
            if S["semi"][e["semya"]].get("status") == TERMINAL: raise OshibkaReestra("семья уже закрыта")
        else:
            raise OshibkaReestra(f"неизвестный тип события {t}")

    # ---------- API ----------
    def semya(self, id, opisanie, status="ACTIVE", istochnik=None):
        return self._zapisat(dict(tip="semya", id=id, opisanie=opisanie, status=status, istochnik=istochnik))

    def gipoteza(self, id, semya, mehanizm, istochniki_dannyh, avtor="claude"):
        return self._zapisat(dict(tip="gipoteza", id=id, semya=semya, mehanizm=mehanizm,
                                  istochniki_dannyh=list(istochniki_dannyh), avtor=avtor))

    def okno(self, id, nabor, nachalo, konec, rol, byudzhet=0):
        return self._zapisat(dict(tip="okno", id=id, nabor=nabor, nachalo=nachalo, konec=konec, rol=rol, byudzhet=int(byudzhet)))

    def zaregistrirovat_popytku(self, id, gipoteza, okno, stadiya, spec, kriterii):
        return self._zapisat(dict(tip="popytka", id=id, gipoteza=gipoteza, okno=okno, stadiya=stadiya,
                                  spec_sha=spec_sha(spec), kriterii=kriterii))

    def zapisat_rezultat(self, popytka, spec, t, n, metrika=None):
        S = self.sostoyanie(); p = S["popytki"].get(popytka)
        if not p: raise OshibkaReestra("результат к незарегистрированной попытке не принимается")
        k = self.popytok_na_okne(p["okno"], S); t_req = trebuemyy_t(k)
        kr = p["kriterii"]; znak_ok = (t > 0) if kr.get("znak", "+") == "+" else (t < 0)
        verdikt = "PASS" if (n >= kr["min_n"] and znak_ok and abs(t) >= t_req) else "FAIL"
        return self._zapisat(dict(tip="rezultat", popytka=popytka, spec_sha=spec_sha(spec), t=float(t), n=int(n),
                                  metrika=metrika, popytok_na_okne=k, trebuemyy_t=round(t_req, 3), verdikt=verdikt))

    def perehod(self, gipoteza, v, prichina, owner_go=None):
        S = self.sostoyanie(); g = S["gipotezy"].get(gipoteza)
        return self._zapisat(dict(tip="perehod", gipoteza=gipoteza, iz=g["status"] if g else None, v=v,
                                  prichina=prichina, owner_go=owner_go))

    def nasledie(self, gipoteza, status, dokument):
        """Перенос статуса, полученного ДО реестра (тени, старые KILL) — с обязательной ссылкой на документ."""
        return self._zapisat(dict(tip="nasledie", gipoteza=gipoteza, status=status, dokument=dokument))

    def zakryt_semyu(self, semya, prichina):
        return self._zapisat(dict(tip="semya_kill", semya=semya, prichina=prichina))

    def pohozhie(self, text, porog=0.2):
        """Сверка с кладбищем: семьи/гипотезы в KILL с похожим описанием (Жаккар по основам слов)."""
        S = self.sostoyanie(); a = osnovy(text); out = []
        kand = [(s["id"], s.get("opisanie", "")) for s in S["semi"].values() if s.get("status") == TERMINAL]
        kand += [(g["id"], g.get("mehanizm", "")) for g in S["gipotezy"].values() if g["status"] == TERMINAL]
        for id_, txt in kand:
            b = osnovy(txt + " " + id_.replace("_", " "))
            j = len(a & b) / max(1, len(a | b))
            if j >= porog: out.append((round(j, 2), id_))
        return sorted(out, reverse=True)

    def svodka(self):
        S = self.sostoyanie(); from collections import Counter
        return dict(semey=len(S["semi"]), semey_kill=sum(s.get("status") == TERMINAL for s in S["semi"].values()),
                    gipotez=dict(Counter(g["status"] for g in S["gipotezy"].values())),
                    okon={o["id"]: dict(rol=o["rol"], popytok=self.popytok_na_okne(o["id"], S), byudzhet=o.get("byudzhet"))
                          for o in S["okna"].values()},
                    popytok=len(S["popytki"]), s_rezultatom=sum(p["rezultat"] is not None for p in S["popytki"].values()))


if __name__ == "__main__":
    import sys
    print(json.dumps(Reestr(sys.argv[1] if len(sys.argv) > 1 else None).svodka(), ensure_ascii=False, indent=1))
