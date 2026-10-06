#!/usr/bin/env python3
"""kontroller.py — FACTORY AUTONOMY V1: контроллер ОДНОГО исследовательского слота (WIP = 1).

DATA HEALTH → ОЧЕРЕДЬ → НОВИЗНА/КЛАДБИЩЕ → ДИАГНОСТИКА ПРИЗНАКОВ (обязательна) → ИЗМЕРЕНИЕ ВЫБРАНО → МНОЖЕСТВЕННОСТЬ →
PREREG HASH LOCK → ОДИН ПРОГОН → ДЕТЕРМИНИРОВАННЫЙ СУДЬЯ → КВИТАНЦИЯ → РЕЕСТР → READY_FOR_BUILD (пакет Codex) / KILL (кладбище)
→ СЛОТ СВОБОДЕН → сообщение владельцу только на терминал/блокер.

Очередь: data/fabrika_xs/ochered/<id>.json — prereg-JSON + обязательные блоки:
  odobreno {kem, kogda, proverka_semi}            — одобрение Claude (ИИ не одобряет);
  diagnostika {fayl, izmerenie_vybrano}          — JSON диагностики признаков БЕЗ доходностей, сделанной до замка;
  okno_dannyh                                     — ключ окна для журнала множественных проверок;
  tip_sudi: "xs_weekly" (sudya_xs, по умолчанию) | "skript" (замороженный скрипт-судья; sha256 скрипта входит в замок).
Запреты в коде: нет спасения после FAIL, нет смены порогов, нет перепрогона, нет второго активного слота,
нет prereg на окне, где израсходовано ≥ LIMIT_PROVEROK исходов (нужны новые данные).
Без git, без сети, без брокера. Цикл — только ручной screen (никакого launchd/cron на Mac).
    python3 research_lab/fabrika/kontroller.py --shag | --cikl 6
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sudya_xs as X
import digest as G
import reestr_strategiy as RS

LAB = X.LAB
LIMIT_PROVEROK = 6


def norm(s): return re.sub(r"[^A-Z0-9]", "", str(s).upper())
def sha(b: bytes): return hashlib.sha256(b).hexdigest()
def seychas(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Kontroller:
    def __init__(self, lab: Path = LAB):
        self.lab = lab; self.fx = lab / "data" / "fabrika_xs"
        self.slot_f = self.fx / "SLOT.json"; self.zh = self.fx / "zhurnal.jsonl"; self.och = self.fx / "ochered"
        self.kl_f = lab / "generator" / "kladbische.json"; self.reestr = self.fx / "REESTR_STRATEGIY.json"
        self.vladelec = self.fx / "SOOBSHCHENIYA_VLADELCU.md"

    # ---------- журналы ----------
    def zapis(self, sobytie, **kw):
        self.fx.mkdir(parents=True, exist_ok=True)
        with open(self.zh, "a") as f:
            f.write(json.dumps(dict(kogda=seychas(), sobytie=sobytie, **kw), ensure_ascii=False) + "\n")

    def vladelcu(self, tekst):
        with open(self.vladelec, "a") as f:
            f.write(f"- {seychas()[:16]} UTC — {tekst}\n")

    def slot(self):
        return json.loads(self.slot_f.read_text()) if self.slot_f.exists() else {"aktivnye": []}

    def otkaz(self, f, sp, sobytie, **kw):
        self.zapis(sobytie, id=sp.get("id"), **kw); f.rename(f.with_suffix(".otkaz"))

    # ---------- шаг ----------
    def shag(self):
        sl = self.slot(); dg = G.sobrat(self.lab)
        if not sl["aktivnye"]:
            return self._vzyat(dg)
        return self._progon(sl["aktivnye"][0], dg)

    def _vzyat(self, dg):
        kl = {norm(x["semya"]) for x in json.loads(self.kl_f.read_text())} if self.kl_f.exists() else set()
        zh = RS.zhurnal_proverok(self.reestr)
        for f in sorted(self.och.glob("*.json")) if self.och.is_dir() else []:
            sp = json.loads(f.read_text())
            if not sp.get("odobreno", {}).get("kem"):
                continue
            if norm(sp.get("semya", sp["id"])) in kl:
                self.otkaz(f, sp, "OTKAZ_KLADBISCHE"); continue
            if (self.fx / sp["id"] / "KVITANCIYA.json").exists() or sp["id"] in RS.zagruzit(self.reestr)["zapisi"]:
                self.otkaz(f, sp, "OTKAZ_UZHE_PROVEREN"); continue
            dgk = sp.get("diagnostika") or {}
            if not (dgk.get("izmerenie_vybrano") and dgk.get("fayl") and (self.lab / dgk["fayl"]).exists()):
                self.otkaz(f, sp, "OTKAZ_NET_DIAGNOSTIKI"); continue
            okno = sp.get("okno_dannyh")
            if not okno:
                self.otkaz(f, sp, "OTKAZ_NET_OKNA_DANNYH"); continue
            if zh.get(okno, 0) >= LIMIT_PROVEROK:
                self.otkaz(f, sp, "BLOCKED_MNOZHESTVENNOST", okno=okno, izraskhodovano=zh[okno])
                self.vladelcu(f"{sp['id']}: BLOCKED — на окне {okno} уже {zh[okno]} проверок; нужны новые данные"); continue
            if self._blok_dannyh(sp, dg):
                self.zapis("BLOCKED_DATA", id=sp["id"], trevogi=dg["trevogi"])
                self.vladelcu(f"{sp['id']}: BLOCKED_DATA — {'; '.join(dg['trevogi'][:3]) or 'набор не найден'}"); return "BLOCKED_DATA"
            sp["proverka_nomer_na_okne"] = zh.get(okno, 0) + 1
            if sp.get("tip_sudi") == "skript":
                sk = self.lab / sp["skript"]
                if not sk.exists():
                    self.otkaz(f, sp, "OTKAZ_NET_SKRIPTA"); continue
                sp["skript_sha256"] = sha(sk.read_bytes())
            pr = self.lab / "prereg" / f"{sp['id']}.json"; pr.parent.mkdir(exist_ok=True)
            pr.write_text(json.dumps(sp, ensure_ascii=False, indent=1))
            h = self._zamok(pr, sp)
            f.rename(f.with_suffix(".vzyato"))
            self.slot_f.write_text(json.dumps({"aktivnye": [sp["id"]]}, ensure_ascii=False))
            self.zapis("ZAMOK", id=sp["id"], sha256=h, okno=okno, nomer=sp["proverka_nomer_na_okne"]); return f"ZAMOK {sp['id']}"
        return "PUSTO"

    def _zamok(self, pr, sp):
        if sp.get("tip_sudi") == "skript":
            lock = pr.with_suffix(".lock")
            if lock.exists():
                raise X.Otkaz("замок уже есть")
            h = sha(pr.read_bytes()); lock.write_text(json.dumps(dict(sha256=h, kogda=seychas()), indent=1)); return h
        return X.zamorozit(pr, self.lab)

    def _progon(self, i, dg):
        pr = self.lab / "prereg" / f"{i}.json"; sp = json.loads(pr.read_text())
        if self._blok_dannyh(sp, dg):
            self.zapis("BLOCKED_DATA", id=i, trevogi=dg["trevogi"]); return "BLOCKED_DATA"
        try:
            rez = self._sudit(pr, sp)
        except X.Otkaz as e:
            self.zapis("OTKAZ_SUDI", id=i, prichina=str(e)); self.slot_f.write_text(json.dumps({"aktivnye": []}))
            self.vladelcu(f"{i}: отказ судьи — {e}"); return f"OTKAZ {e}"
        st = rez["status"]
        if st == "KILL" and self.kl_f.exists():
            kl = json.loads(self.kl_f.read_text()); kl.append(dict(semya=sp.get("semya", i), prichina=f"kontroller KILL {dt.date.today()}"))
            self.kl_f.write_text(json.dumps(kl, ensure_ascii=False, indent=1))
        RS.zapisat(dict(id=i, semya=sp.get("semya", i), mehanizm=sp.get("mehanizm", ""), dannye=sp.get("dannye", ""),
                        okno_dannyh=sp.get("okno_dannyh"), prereg=str(pr.relative_to(self.lab)), prereg_sha256=sha(pr.read_bytes()),
                        verdikt=st, metriki=json.dumps({k: v for k, v in rez.items() if k in ("PRIMARY", "REPLICATION", "HOLDOUT")}, ensure_ascii=False)[:400],
                        kvitanciya=str((self.fx / i / "KVITANCIYA.json").relative_to(self.lab)),
                        vpered="нужна тень" if st == "READY_FOR_BUILD" else None), self.reestr)
        if st == "READY_FOR_BUILD":
            self._paket_codex(i, sp, rez)
        self.zapis("TERMINAL", id=i, status=st, trebuetsya_claude=st != "KILL")
        self.vladelcu(f"{i} → {st}" + (f" (пакет Codex: data/fabrika_xs/{i}/PAKET_CODEX.md)" if st == "READY_FOR_BUILD" else ""))
        self.slot_f.write_text(json.dumps({"aktivnye": []}))
        return f"TERMINAL {i} {st}"

    def _sudit(self, pr, sp):
        if sp.get("tip_sudi") != "skript":
            return X.progon(pr, self.lab)
        lock = json.loads(pr.with_suffix(".lock").read_text())
        if lock["sha256"] != sha(pr.read_bytes()):
            raise X.Otkaz("prereg правили после замка")
        sk = self.lab / sp["skript"]
        if sha(sk.read_bytes()) != sp["skript_sha256"]:
            raise X.Otkaz("скрипт-судья изменён после замка")
        vyh = self.fx / sp["id"]; kv = vyh / "KVITANCIYA.json"
        if kv.exists():
            raise X.Otkaz("результат уже есть — повторный прогон запрещён")
        p = subprocess.run([sys.executable, str(sk)], cwd=str(self.lab), capture_output=True, text=True, timeout=3000)
        rp = self.lab / sp["rezultat"]
        if p.returncode != 0 or not rp.exists():
            raise X.Otkaz(f"скрипт-судья не дал результата: {p.stderr[-300:]}")
        rez = json.loads(rp.read_text()); vyh.mkdir(parents=True, exist_ok=True)
        kv.write_text(json.dumps(dict(id=sp["id"], prereg_sha256=sha(pr.read_bytes()), skript_sha256=sp["skript_sha256"],
                                      rezultat_sha256=sha(rp.read_bytes()), status=rez["status"], kogda=seychas()), ensure_ascii=False, indent=1))
        return rez

    def _paket_codex(self, i, sp, rez):
        t = [f"# Пакет Codex: {i} — READY_FOR_BUILD ({dt.date.today()})", "",
             "Сгенерирован контроллером фабрики. Правило заморожено; Codex не меняет и не перепрогоняет исследование.",
             f"- механизм: {sp.get('mehanizm', '')}", f"- prereg: prereg/{i}.json (sha256 {sha((self.lab / 'prereg' / f'{i}.json').read_bytes())[:16]}…)",
             f"- данные/окно: {sp.get('dannye', '')} / {sp.get('okno_dannyh')} (проверка №{sp.get('proverka_nomer_na_okne')} на этом окне)",
             f"- квитанция: data/fabrika_xs/{i}/KVITANCIYA.json", "", "## Результат", "```", json.dumps(
                 {k: v for k, v in rez.items() if k != "sobytiya"}, ensure_ascii=False, indent=1, default=float)[:3000], "```", "",
             "## Что нужно от Codex (orders-OFF до GO владельца)",
             "1. Независимая реконструкция сигнала по prereg; сверка с вперёд-тенью Claude.",
             "2. Площадка/инструмент, мин. лот/номинал, спред/своп/комиссии выбранного счёта, глубина.",
             "3. Размер, лимиты на ногу/портфель/день, защита, выход/откат, единственный владелец позиции.",
             "4. Статус READY_FOR_CANARY или конкретный BLOCKED_*; деньги — только письменное GO владельца."]
        (self.fx / i).mkdir(parents=True, exist_ok=True); (self.fx / i / "PAKET_CODEX.md").write_text("\n".join(t))

    def _blok_dannyh(self, sp, dg):
        if sp.get("tip_sudi") == "skript":
            return any(not (self.lab / p).exists() for p in sp.get("vhodnye_fayly", []))
        n = sp["dannye"]; v = dg["nabory"].get(n)
        if v is None:
            return True
        if v.get("arhiv"):
            return False
        return any((x.get("otstavanie_dn") or 0) > 3 for x in v["podpapki"].values())


def main():
    k = Kontroller(); zamok = k.fx / "kontroller.pid"
    if zamok.exists() and zamok.read_text().strip():
        pid = zamok.read_text().strip()
        kmd = subprocess.run(["ps", "-p", pid, "-o", "command="], capture_output=True, text=True).stdout
        if "kontroller.py" in kmd:
            sys.exit("контроллер уже работает")
    k.fx.mkdir(parents=True, exist_ok=True); zamok.write_text(str(os.getpid()))
    try:
        if "--cikl" in sys.argv:
            chasy = float(sys.argv[sys.argv.index("--cikl") + 1])
            while True:
                print(seychas(), k.shag(), flush=True); time.sleep(chasy * 3600)
        else:
            print(k.shag())
    finally:
        zamok.write_text("")


if __name__ == "__main__":
    main()
