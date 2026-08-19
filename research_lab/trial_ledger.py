"""ЖУРНАЛ ПОПЫТОК — предохранитель для автоматического исследователя.

ЗАЧЕМ. Владелец хочет робота, который сам ищет в интернете, сам формулирует
гипотезы, сам их тестирует и приносит готовое. Идея правильная, но у неё
есть ровно одно место, где она ломается:

    робот, который проверяет тысячу гипотез в день, найдёт сотню
    «работающих» — и все они будут шумом.

Это не гипотетика: в `backtest_runs/` уже 53 467 прогонов, и ни один гейт
проекта не учитывал их количество. Результат, отобранный как лучший
из десятков тысяч, — принципиально более слабое свидетельство, чем тот же
результат из десяти попыток.

РЕШЕНИЕ. Каждая проверка регистрируется ДО того, как увидит результат,
вместе с критерием опровержения. Журнал считает попытки внутри «семейства»
гипотез и автоматически поднимает планку значимости по числу попыток
(Deflated Sharpe, Bailey & Lopez de Prado).

Гипотеза принимается, только если её Sharpe бьёт планку, рассчитанную
на ФАКТИЧЕСКОЕ число попыток в этом семействе — включая все неудачные,
про которые обычно забывают.

ПОЧЕМУ ЭТО ГЛАВНАЯ ДЕТАЛЬ АВТОМАТИЗАЦИИ. Без счётчика попыток любой
автоматический исследователь — генератор ложных открытий. Со счётчиком
он становится безопасным: чем больше он перебирает, тем выше сам себе
поднимает планку.

Использование:

    from research_lab.trial_ledger import TrialLedger

    led = TrialLedger()
    tid = led.register(
        family="funding_variants",
        hypothesis="фандинг p95 удержание 4ч даёт положительный остаток",
        falsify_if="остаток после снятия беты <= 0 или t < 2",
    )
    ... прогон ...
    print(led.record_result(tid, returns=[...]).text())
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import uuid
from dataclasses import dataclass, asdict, field

from research_lab.significance import (
    deflated_sharpe, expected_max_sharpe_under_null, _moments,
)

LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "runtime", "research", "trial_ledger.jsonl")


@dataclass
class Verdict:
    trial_id: str
    family: str
    trials_in_family: int
    n_obs: int
    sharpe_per_obs: float
    hurdle: float
    dsr: float
    passed: bool

    def text(self) -> str:
        mark = "ПРОШЛА" if self.passed else "НЕ ПРОШЛА"
        return (
            f"[{mark}] семейство «{self.family}», попытка №{self.trials_in_family}\n"
            f"  наблюдений: {self.n_obs}\n"
            f"  Sharpe за наблюдение: {self.sharpe_per_obs:+.4f}\n"
            f"  планка с поправкой на {self.trials_in_family} попыток: "
            f"{self.hurdle:+.4f}\n"
            f"  DSR: {self.dsr:.3f}  (порог принятия 0.95)"
        )


class TrialLedger:
    """Журнал попыток. Пишет jsonl, ничего не удаляет."""

    def __init__(self, path: str = LEDGER):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    # ── чтение ──
    def _all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out

    def count_family(self, family: str) -> int:
        """Сколько попыток уже сделано в этом семействе. Включая провалы."""
        return sum(1 for r in self._all()
                   if r.get("family") == family and r.get("kind") == "register")

    def _append(self, rec: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ── регистрация ДО результата ──
    def register(self, *, family: str, hypothesis: str, falsify_if: str,
                 params: dict | None = None) -> str:
        """Регистрирует попытку. Вызывать ДО прогона, иначе смысл теряется.

        `falsify_if` обязателен: гипотеза без критерия опровержения
        не является гипотезой.
        """
        if not falsify_if.strip():
            raise ValueError("falsify_if обязателен: гипотеза без критерия "
                             "опровержения не проверяема")
        tid = uuid.uuid4().hex[:12]
        self._append({
            "kind": "register",
            "trial_id": tid,
            "family": family,
            "hypothesis": hypothesis,
            "falsify_if": falsify_if,
            "params": params or {},
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        return tid

    # ── результат ──
    def record_result(self, trial_id: str, returns: list[float],
                      *, accept_dsr: float = 0.95) -> Verdict:
        rec = next((r for r in self._all()
                    if r.get("trial_id") == trial_id and r.get("kind") == "register"), None)
        if rec is None:
            raise KeyError(f"попытка {trial_id} не зарегистрирована — "
                           "результат без регистрации не принимается")
        family = rec["family"]
        trials = self.count_family(family)
        n, mu, sd, sk, ku = _moments(returns)
        sharpe = (mu / sd) if sd > 0 else 0.0
        dsr, hurdle = deflated_sharpe(sharpe, n, trials, skew=sk, kurtosis=ku)
        v = Verdict(trial_id, family, trials, n, sharpe, hurdle, dsr,
                    passed=bool(dsr >= accept_dsr))
        self._append({"kind": "result", **asdict(v),
                      "ts": dt.datetime.now(dt.timezone.utc).isoformat()})
        return v

    # ── обзор ──
    def summary(self) -> str:
        recs = self._all()
        fams: dict[str, dict] = {}
        for r in recs:
            f = r.get("family", "?")
            d = fams.setdefault(f, {"trials": 0, "passed": 0})
            if r.get("kind") == "register":
                d["trials"] += 1
            elif r.get("kind") == "result" and r.get("passed"):
                d["passed"] += 1
        if not fams:
            return "журнал пуст"
        lines = [f"{'семейство':<28}{'попыток':>9}{'прошло':>9}{'планка сейчас':>16}"]
        for f, d in sorted(fams.items(), key=lambda x: -x[1]["trials"]):
            # планка при типичной дисперсии 1/sqrt(100)
            h = expected_max_sharpe_under_null(d["trials"], 0.1)
            lines.append(f"{f[:26]:<28}{d['trials']:>9}{d['passed']:>9}{h:>+16.4f}")
        return "\n".join(lines)


def _self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        led = TrialLedger(os.path.join(td, "t.jsonl"))

        # без критерия опровержения регистрация обязана падать
        try:
            led.register(family="f", hypothesis="h", falsify_if="  ")
        except ValueError:
            pass
        else:
            raise AssertionError("пустой falsify_if принят")

        # результат без регистрации не принимается
        try:
            led.record_result("нет-такого", [0.1, 0.2])
        except KeyError:
            pass
        else:
            raise AssertionError("результат без регистрации принят")

        # ГЛАВНОЕ: планка обязана расти с числом попыток
        import random
        rnd = random.Random(1)
        good = [rnd.gauss(0.15, 1.0) for _ in range(400)]
        t1 = led.register(family="a", hypothesis="h", falsify_if="t<2")
        v1 = led.record_result(t1, good)
        for _ in range(60):
            led.register(family="a", hypothesis="перебор", falsify_if="t<2")
        t2 = led.register(family="a", hypothesis="h", falsify_if="t<2")
        v2 = led.record_result(t2, good)

        assert v2.trials_in_family > v1.trials_in_family
        assert v2.hurdle > v1.hurdle, "планка не выросла с числом попыток"
        assert v2.dsr < v1.dsr, "DSR не упал при том же результате"
        print("самопроверка trial_ledger: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print()
        print("Один и тот же результат, разное число попыток в семействе:")
        print(v1.text())
        print()
        print(v2.text())


if __name__ == "__main__":
    _self_test()
