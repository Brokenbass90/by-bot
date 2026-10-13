#!/usr/bin/env python3
"""ten_v1.py — авто-тень V1 (Factory V3, слой 5). 13.10.2026. Новая тень = один JSON-конфиг, без ручного screen-кода.

Конфиг data/factory_v3/teni/<imya>.json:
  {"imya": "...", "gipoteza": "<id в реестре, статус SHADOW>", "signal": "modul:funkciya",
   "kazhdye_min": 60, "sdvig_min": 2, "parametry": {...}}
Сигнал: f(now_ms, parametry) -> [ {sym, napravlenie(+1/-1), izvestno_ms, ...}, ... ] — только решения, известные к now.

Гарантии:
  • стартует только если гипотеза в реестре в SHADOW/CANARY; если реестр перевёл её в KILL — тень останавливается сама;
  • один экземпляр: flock data/locks/ten3_<imya>.lock (снимается ОС при смерти процесса);
  • журнал решений append-only data/factory_v3/teni/<imya>/zhurnal.jsonl; ключ (sym, izvestno_ms, napravlenie) идемпотентен;
    решение «из будущего» (izvestno_ms > now) — отказ и тревога; известное раньше предыдущего прохода — помечается opozdanie;
  • пульс «<iso> пульс: жив …» в data/ten3_<imya>.log и авторегистрация в data/storozh/aktivnye.json — сторож видит тень сразу.
Исходы и PnL тень не считает: это работа замороженного судьи по журналу.

    python3 research_lab/factory_v3/ten_v1.py <imya> [--odin-prohod]
"""
import datetime as dt, fcntl, importlib, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent; LAB = HERE.parent
for p in (str(HERE), str(LAB)):
    if p not in sys.path: sys.path.insert(0, p)
from reestr_v1 import Reestr

D = LAB / "data"
ZHIVYE = ("SHADOW", "CANARY")


class OshibkaTeni(Exception):
    pass


def iso(ms=None): return dt.datetime.fromtimestamp((ms or time.time() * 1000) / 1000, dt.timezone.utc).isoformat(timespec="seconds")


class Ten:
    def __init__(self, imya, baza=None, reestr=None):
        self.D = Path(baza) if baza else D
        self.cfg = json.loads((self.D / "factory_v3" / "teni" / f"{imya}.json").read_text())
        if self.cfg["imya"] != imya: raise OshibkaTeni("имя в конфиге не совпадает с файлом")
        self.imya = imya; self.reestr = reestr or Reestr()
        self.papka = self.D / "factory_v3" / "teni" / imya; self.papka.mkdir(parents=True, exist_ok=True)
        self.zhurnal = self.papka / "zhurnal.jsonl"; self.sost = self.papka / "sostoyanie.json"
        self.log_put = self.D / f"ten3_{imya}.log"
        mod, fn = self.cfg["signal"].split(":"); self.signal = getattr(importlib.import_module(mod), fn)
        self._fd = None

    def log(self, *a):
        with open(self.log_put, "a") as f: f.write(iso() + " " + " ".join(str(x) for x in a) + "\n")

    def status_v_reestre(self):
        g = self.reestr.sostoyanie()["gipotezy"].get(self.cfg["gipoteza"])
        return g["status"] if g else None

    def zamok(self):
        (self.D / "locks").mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.D / "locks" / f"ten3_{self.imya}.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try: fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise OshibkaTeni(f"тень {self.imya} уже работает (замок занят)")

    def zaregistrirovat_u_storozha(self):
        p = self.D / "storozh" / "aktivnye.json"; p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX); f.seek(0); txt = f.read()
            spisok = json.loads(txt) if txt.strip() else []
            if f"ten3_{self.imya}" not in spisok:
                spisok.append(f"ten3_{self.imya}"); f.seek(0); f.truncate(); f.write(json.dumps(spisok, ensure_ascii=False, indent=1))

    def _klyuchi(self):
        if not self.zhurnal.exists(): return set()
        with open(self.zhurnal) as f:
            return {(r["sym"], r["izvestno_ms"], r["napravlenie"]) for r in (json.loads(l) for l in f if l.strip())}

    def prohod(self, now_ms=None):
        now_ms = now_ms or int(time.time() * 1000)
        st = self.status_v_reestre()
        if st not in ZHIVYE:
            self.log(f"остановлена: гипотеза {self.cfg['gipoteza']} в реестре = {st}")
            return dict(stop=True, status=st)
        prosh = json.loads(self.sost.read_text())["posl_prohod_ms"] if self.sost.exists() else None
        uzhe = self._klyuchi(); novye, budushchie = 0, 0
        for r in self.signal(now_ms, self.cfg.get("parametry", {})):
            k = (r["sym"], int(r["izvestno_ms"]), int(r["napravlenie"]))
            if k[1] > now_ms:
                budushchie += 1; self.log("ТРЕВОГА: решение из будущего отклонено", k); continue
            if k in uzhe: continue
            zap = dict(r, izvestno_ms=k[1], napravlenie=k[2], zapisano_ms=now_ms, ten=self.imya, gipoteza=self.cfg["gipoteza"],
                       opozdanie=bool(prosh and k[1] < prosh))
            with open(self.zhurnal, "a") as f: f.write(json.dumps(zap, ensure_ascii=False, sort_keys=True) + "\n")
            uzhe.add(k); novye += 1
        self.sost.write_text(json.dumps(dict(posl_prohod_ms=now_ms)))
        self.log(f"пульс: жив, новых решений {novye}, всего {len(uzhe)}, из будущего {budushchie}")
        return dict(stop=False, novyh=novye, vsego=len(uzhe), iz_budushchego=budushchie)

    def zapusk(self, odin=False):
        st = self.status_v_reestre()
        if st not in ZHIVYE: raise OshibkaTeni(f"гипотеза {self.cfg['gipoteza']} в реестре = {st}; тень запускается только для {ZHIVYE}")
        self.zamok(); self.zaregistrirovat_u_storozha(); self.log("старт", json.dumps(self.cfg, ensure_ascii=False))
        while True:
            if self.prohod()["stop"] or odin: return
            k = self.cfg.get("kazhdye_min", 60) * 60; s = self.cfg.get("sdvig_min", 2) * 60
            time.sleep(k - (time.time() - s) % k)


if __name__ == "__main__":
    Ten(sys.argv[1]).zapusk(odin="--odin-prohod" in sys.argv)
