"""ПАМЯТЬ ЗАКРЫТЫХ ГИПОТЕЗ — чтобы не ходить по кругу.

ЗАЧЕМ. `trial_ledger.py` не даёт обмануть себя цифрами: чем больше попыток,
тем выше планка. Но он не мешает **проверять одно и то же по десятому разу**.
Для автоматического исследователя это критично: он не устаёт и не помнит.

Здесь хранится то, что уже закрыто: вердикт, МЕХАНИЗМ закрытия и условие,
при котором гипотезу можно переоткрыть. Перед регистрацией новой попытки
достаточно спросить `check()`.

ПОЧЕМУ ХРАНИТСЯ МЕХАНИЗМ, А НЕ ПРОСТО «НЕ РАБОТАЕТ». «Не получилось» —
бесполезная запись: через месяц никто не вспомнит, было ли дело в идее,
в данных или в баге. Механизм («спред 2.91 bps против круга 4.00»)
проверяем и позволяет понять, изменились ли условия.

УСЛОВИЕ ПЕРЕОТКРЫТИЯ обязательно. Гипотеза, закрытая навсегда без условий,
— это догма. Условие превращает закрытие в обратимое решение.

Использование:

    from research_lab.hypothesis_memory import HypothesisMemory
    mem = HypothesisMemory()
    for hit in mem.check("проверить отскок после каскада ликвидаций"):
        print(hit.warn())
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict

STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "runtime", "research", "closed_hypotheses.json")

_STOP = {
    "и", "в", "на", "с", "по", "для", "не", "что", "как", "это", "из", "за",
    "от", "до", "при", "или", "то", "же", "а", "но", "у", "о", "об", "the",
    "a", "of", "to", "in", "is", "проверить", "тест", "гипотеза",
}


def _tokens(text: str) -> set[str]:
    """Значимые слова, усечённые до основы.

    Усечение до 5 символов — грубый стеммер, но необходимый: без него
    «каскад» и «каскада» считались разными словами, и память пропускала
    перефразированную гипотезу. А ловить перефразированное — вся её задача.
    Поймано собственной самопроверкой.
    """
    words = re.findall(r"[а-яёa-z0-9]{3,}", (text or "").lower())
    return {w[:5] for w in words if w not in _STOP}


@dataclass
class Closed:
    key: str
    title: str
    verdict: str
    mechanism: str            # ПОЧЕМУ закрыто, проверяемо
    reopen_if: str            # при каких условиях вернуться
    evidence: str = ""        # где смотреть подробности
    date: str = ""

    def warn(self) -> str:
        return (
            f"⚠ ПОХОЖЕ НА ЗАКРЫТОЕ: {self.title}\n"
            f"   вердикт:    {self.verdict}\n"
            f"   механизм:   {self.mechanism}\n"
            f"   вернуться:  {self.reopen_if}\n"
            f"   подробно:   {self.evidence or '—'}"
        )


# Заряжено из reports/CLAUDE_CONSOLIDATED_2026_08_03.md
SEED: list[Closed] = [
    Closed("market_making", "Маркет-мейкинг", "закрыт",
           "спред 2.91 bps против круга 4.00 bps — арифметика, не исполнение",
           "снижение комиссий или появление ребейтов маркет-мейкера",
           "consolidated §1", "2026-07"),
    Closed("cross_exchange_arb", "Межбиржевой арбитраж", "закрыт",
           "251 цикл, винрейт 30%, −5.5%/мес после издержек",
           "не возвращаться без принципиально иной инфраструктуры исполнения",
           "consolidated §1", "2026-07"),
    Closed("equity_overnight", "Овернайт на акциях", "закрыт",
           "buy&hold бьёт стратегию вдвое после издержек",
           "нет", "research_lab/equity_overnight.py", "2026-07"),
    Closed("hour_seasonality", "Сезонность по часам", "закрыт",
           "52.6% случайных перемешиваний дают не хуже — находка не отличима от шума",
           "нет", "consolidated §1", "2026-07"),
    Closed("fx_intraday", "Внутридневной FX", "закрыт",
           "эдж 0.18 пипса при круговых издержках 1.04 пипса",
           "принципиально лучшие условия исполнения", "consolidated §1", "2026-07"),
    Closed("vol_selling", "Продажа волатильности", "закрыт",
           "толстый хвост убытков несовместим с плечом 3 и депозитом $1000",
           "депозит на порядок больше и отдельный риск-лимит", "consolidated §1", "2026-07"),
    Closed("options_expiry", "Экспирации опционов", "закрыт",
           "мощности не хватит: разброс дрейфа 350-484 bps при 12 событиях в год, "
           "для эффекта 50 bps нужно 25 лет истории",
           "эффект >100 bps на бесплатных данных",
           "research_lab/options_expiry.py", "2026-07-29"),
    Closed("liquidation_cascade", "Каскады ликвидаций сами по себе", "закрыт",
           "эффект +7.9 bps (t=3.54) НЕ растёт с размером каскада — "
           "микроструктурный, живёт под издержками ~8 bps круг",
           "каскад НА УРОВНЕ — это другая гипотеза, она не проверялась",
           "research_lab/liquidation_cascade.py", "2026-07-29"),
    Closed("heat_selector", "Разогретость монеты как селектор", "закрыт условно",
           "на мажорах признака нет: холодные −0.07%, разогретые −0.29%, t<1",
           "проверить заново на новых альтах — в кэше были только 13 мажоров",
           "research_lab/heat_selector.py", "2026-07-29"),
    Closed("entry_ladder", "Лестница входа как источник дохода", "закрыт",
           "доход не меняется (−0.003R), но хвост легчает на треть — "
           "это инструмент формы риска, а не эдж",
           "вернуться при работе над риск-бюджетом, не над доходностью",
           "research_lab/entry_ladder.py", "2026-07-29"),
    Closed("pead_gap_proxy", "PEAD через гэпы", "закрыт условно",
           "заменитель слабый: нет величины сюрприза, 59 бумаг за 3 года",
           "настоящие даты отчётностей и консенсус",
           "research_lab/equity_gap_drift.py", "2026-07"),
    Closed("att1_min_slope", "Порог наклона ATT1", "закрыт",
           "на медвежьем окне +11%, но по трём окнам ноль: +3.78 против +3.74",
           "нет", "reports/CLAUDE_FOR_CODEX_2026_08_02.md", "2026-08-02"),
    Closed("purge_leakage", "Утечка через перекрытие сделок", "закрыт",
           "измерено: 0.0% и 1.3% — сделки коротки относительно истории",
           "вернуться при мета-разметке: длинные перекрывающиеся окна дадут 55%",
           "research_lab/purged_cv.py", "2026-08-02"),
]


class HypothesisMemory:
    def __init__(self, path: str = STORE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self._write(SEED)

    def _write(self, items: list[Closed]) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump([asdict(i) for i in items], fh, ensure_ascii=False, indent=2)

    def all(self) -> list[Closed]:
        with open(self.path, encoding="utf-8") as fh:
            return [Closed(**d) for d in json.load(fh)]

    def check(self, text: str, *, min_overlap: int = 2) -> list[Closed]:
        """Похожие закрытые гипотезы. Совпадение по значимым словам."""
        q = _tokens(text)
        hits = []
        for c in self.all():
            corpus = _tokens(f"{c.title} {c.mechanism} {c.key.replace('_',' ')}")
            n = len(q & corpus)
            if n >= min_overlap:
                hits.append((n, c))
        return [c for _, c in sorted(hits, key=lambda x: -x[0])]

    def close(self, c: Closed) -> None:
        if not c.mechanism.strip():
            raise ValueError("механизм обязателен: «не работает» — бесполезная запись")
        if not c.reopen_if.strip():
            raise ValueError("условие переоткрытия обязательно: "
                             "закрытие без условий — это догма, а не вывод")
        items = [i for i in self.all() if i.key != c.key] + [c]
        self._write(items)


def _self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mem = HypothesisMemory(os.path.join(td, "h.json"))
        assert len(mem.all()) >= 12

        hits = mem.check("отскок после каскада ликвидаций на альтах")
        assert any(h.key == "liquidation_cascade" for h in hits), "каскады не найдены"

        hits2 = mem.check("продажа волатильности через опционы")
        assert any(h.key == "vol_selling" for h in hits2), "воля не найдена"

        assert not mem.check("совершенно посторонняя тема про погоду")

        for bad in (
            Closed("x", "t", "закрыт", "", "условие"),
            Closed("x", "t", "закрыт", "механизм", ""),
        ):
            try:
                mem.close(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("запись без механизма/условия принята")

        print("самопроверка hypothesis_memory: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print(f"в памяти закрытых гипотез: {len(mem.all())}")
        print()
        print(mem.check("каскад ликвидаций отскок")[0].warn())


if __name__ == "__main__":
    _self_test()
