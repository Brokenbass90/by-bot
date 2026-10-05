#!/usr/bin/env python3
"""kontroller.py — AUTONOMOUS_SHADOW_RESEARCH_V1, срез 4: контроллер ОДНОГО исследовательского слота.

Очередь: data/fabrika_xs/ochered/<id>.json — prereg-JSON для sudya_xs + блок "odobreno" {kem, kogda, proverka_semi}.
Только одобренные Claude элементы исполняются; DRAFT аналитика сюда не попадает без одобрения.
Один шаг (идемпотентно):
  1. digest; тревоги по наборам, нужным активному/следующему элементу → BLOCKED_DATA, слот не трогается.
  2. слот пуст → берёт самый старый одобренный элемент; отказ, если семья на кладбище или квитанция уже есть;
     кладёт в prereg/, ставит замок (sudya_xs.zamorozit), пишет SLOT.json.
  3. слот занят, замок есть, результата нет → ОДИН прогон sudya_xs.progon → квитанция; KILL → семья на кладбище;
     READY_FOR_BUILD / BLOCKED → флаг TREBUETSYA_CLAUDE; слот освобождается; всё в zhurnal.jsonl.
Без git, без сети, без брокера, без правки порогов. Цикл — только ручной screen (никакого launchd/cron на Mac).
    python3 research_lab/fabrika/kontroller.py --shag
    python3 research_lab/fabrika/kontroller.py --cikl 6      (шаг раз в 6 часов, в screen)
"""
from __future__ import annotations
import datetime as dt, json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sudya_xs as X
import digest as G

LAB = X.LAB


def norm(s): return re.sub(r"[^A-Z0-9]", "", str(s).upper())


class Kontroller:
    def __init__(self, lab: Path = LAB):
        self.lab = lab; self.fx = lab / "data" / "fabrika_xs"
        self.slot_f = self.fx / "SLOT.json"; self.zh = self.fx / "zhurnal.jsonl"; self.och = self.fx / "ochered"
        self.kl_f = lab / "generator" / "kladbische.json"

    def zapis(self, sobytie, **kw):
        self.fx.mkdir(parents=True, exist_ok=True)
        with open(self.zh, "a") as f:
            f.write(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), sobytie=sobytie, **kw),
                               ensure_ascii=False) + "\n")

    def slot(self):
        return json.loads(self.slot_f.read_text()) if self.slot_f.exists() else {"aktivnye": []}

    def shag(self):
        sl = self.slot(); dg = G.sobrat(self.lab)
        if not sl["aktivnye"]:
            kand = sorted(self.och.glob("*.json")) if self.och.is_dir() else []
            kl = {norm(x["semya"]) for x in json.loads(self.kl_f.read_text())} if self.kl_f.exists() else set()
            for f in kand:
                sp = json.loads(f.read_text())
                if not sp.get("odobreno", {}).get("kem"):
                    continue
                if norm(sp.get("semya", sp["id"])) in kl:
                    self.zapis("OTKAZ_KLADBISCHE", id=sp["id"]); f.rename(f.with_suffix(".otkaz")); continue
                if (self.fx / sp["id"] / "KVITANCIYA.json").exists():
                    self.zapis("OTKAZ_UZHE_EST_KVITANCIYA", id=sp["id"]); f.rename(f.with_suffix(".otkaz")); continue
                if self._blok_dannyh(sp, dg):
                    self.zapis("BLOCKED_DATA", id=sp["id"], trevogi=dg["trevogi"]); return "BLOCKED_DATA"
                pr = self.lab / "prereg" / f"{sp['id']}.json"; pr.parent.mkdir(exist_ok=True)
                pr.write_text(json.dumps(sp, ensure_ascii=False, indent=1)); h = X.zamorozit(pr, self.lab)
                f.rename(f.with_suffix(".vzyato"))
                self.slot_f.write_text(json.dumps({"aktivnye": [sp["id"]]}, ensure_ascii=False))
                self.zapis("ZAMOK", id=sp["id"], sha256=h); return f"ZAMOK {sp['id']}"
            return "PUSTO"
        i = sl["aktivnye"][0]; pr = self.lab / "prereg" / f"{i}.json"
        sp = json.loads(pr.read_text())
        if self._blok_dannyh(sp, dg):
            self.zapis("BLOCKED_DATA", id=i, trevogi=dg["trevogi"]); return "BLOCKED_DATA"
        try:
            rez = X.progon(pr, self.lab)
        except X.Otkaz as e:
            self.zapis("OTKAZ_SUDI", id=i, prichina=str(e)); self.slot_f.write_text(json.dumps({"aktivnye": []}))
            return f"OTKAZ {e}"
        st = rez["status"]
        if st == "KILL" and self.kl_f.exists():
            kl = json.loads(self.kl_f.read_text()); kl.append(dict(semya=sp.get("semya", i), prichina=f"kontroller KILL {dt.date.today()}"))
            self.kl_f.write_text(json.dumps(kl, ensure_ascii=False, indent=1))
        self.zapis("TERMINAL", id=i, status=st, trebuetsya_claude=st != "KILL")
        self.slot_f.write_text(json.dumps({"aktivnye": []}))
        return f"TERMINAL {i} {st}"

    def _blok_dannyh(self, sp, dg):
        n = sp["dannye"]; v = dg["nabory"].get(n)
        if v is None:
            return True
        if v.get("arhiv"):
            return False
        return any((x.get("otstavanie_dn") or 0) > 3 for x in v["podpapki"].values())


def main():
    k = Kontroller(); zamok = k.fx / "kontroller.pid"
    if zamok.exists() and zamok.read_text().strip():
        try:
            os.kill(int(zamok.read_text()), 0); sys.exit("контроллер уже работает")
        except (OSError, ValueError):
            pass
    k.fx.mkdir(parents=True, exist_ok=True); zamok.write_text(str(os.getpid()))
    try:
        if "--cikl" in sys.argv:
            chasy = float(sys.argv[sys.argv.index("--cikl") + 1])
            while True:
                print(dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), k.shag(), flush=True)
                time.sleep(chasy * 3600)
        else:
            print(k.shag())
    finally:
        zamok.write_text("")          # очистка вместо удаления (удаление в подключённых папках может быть запрещено)


if __name__ == "__main__":
    main()
