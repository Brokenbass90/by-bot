"""ВАЛИДАТОР ИССЛЕДОВАНИЙ — автоматическая проверка на известные классы самообмана.

Каждая проверка соответствует ошибке, которая РЕАЛЬНО была допущена в этом проекте.
Дешевле поймать здесь, чем на живых деньгах.

Использование:
    from research_lab.validator import validate
    report = validate(returns=[...], meta={...}, phases=[[...],[...],[...]],
                      by_symbol={...}, by_month={...})
    print(report.text())
    if not report.ok: ...  # не передавать на интеграцию
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "BLOCK"      # BLOCK = нельзя дальше, WARN = предупреждение

@dataclass
class Report:
    checks: list = field(default_factory=list)
    stage: str = "research"

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "BLOCK")

    def text(self) -> str:
        w = max((len(c.name) for c in self.checks), default=10)
        out = [f"=== ВАЛИДАТОР ИССЛЕДОВАНИЯ [{self.stage.upper()}] ==="]
        for c in self.checks:
            tag = "PASS" if c.passed else ("FAIL" if c.severity == "BLOCK" else "WARN")
            out.append(f"  [{tag}]  {c.name:<{w}}  {c.detail}")
        if self.ok:
            destination = "передаче" if self.stage == "research" else self.stage
            out.append(f"ИТОГ: ГОДЕН к {destination}")
        else:
            out.append("ИТОГ: НЕ ГОДЕН — есть блокирующие дефекты")
        return "\n".join(out)

def _stats(r):
    n = len(r)
    if n < 2: return 0.0, 0.0, 0.0
    mu = sum(r)/n
    sd = (sum((x-mu)**2 for x in r)/(n-1))**0.5
    sh = mu/sd*math.sqrt(n) if sd > 0 else 0.0
    e = 1.0
    for x in r: e *= (1+x)
    return (e-1)*100, sh, sd

def validate(returns, meta=None, phases=None, by_symbol=None, by_month=None,
             min_n=60, min_sharpe=0.8, max_dd=50.0):
    meta = meta or {}
    stage = str(meta.get("promotion_stage") or "research").strip().lower()
    if stage not in {"research", "shadow", "canary", "capital", "live"}:
        raise ValueError(f"unknown promotion_stage: {stage}")
    requires_capital_evidence = stage in {"canary", "capital", "live"}
    evidence_severity = "BLOCK" if requires_capital_evidence else "WARN"
    rep = Report(stage=stage)
    tot, sh, _ = _stats(returns)

    # 1. Размер выборки
    rep.checks.append(Check("размер выборки", len(returns) >= min_n,
        f"n={len(returns)} (нужно >={min_n})"))

    # 2. Перекрывающиеся окна — класс ошибки: завышение n в 56 раз
    ov = meta.get("windows_overlap")
    rep.checks.append(Check("непересекающиеся окна", ov is False,
        "объявлено non-overlapping" if ov is False else
        "НЕ ПОДТВЕРЖДЕНО: укажи meta['windows_overlap']=False. Перекрытие раздувало результат в 56x"))

    # 3. Зависимость от фазы сетки — класс ошибки: PASS на удачном дне старта
    if phases:
        tots = [_stats(p)[0] for p in phases]
        shs  = [_stats(p)[1] for p in phases]
        rep.checks.append(Check("независимость от фазы", all(t > 0 for t in tots),
            "фазы: " + " / ".join(f"{t:.1f}%(Sh {s:.2f})" for t, s in zip(tots, shs))))
    else:
        rep.checks.append(Check("независимость от фазы", False,
            "НЕ ПРОВЕРЕНО: передай phases=[...]. V1 прошла ворота только на удачной фазе"))

    # 4. Пост-фактум пороги
    ph = meta.get("posthoc_thresholds")
    rep.checks.append(Check("пороги пре-регистрированы", ph is False,
        "все пороги заморожены до прогона" if ph is False else
        f"ВНИМАНИЕ, пост-фактум: {ph if ph else 'не задано'}",
        severity=evidence_severity))

    # 5. Survivorship
    sv = meta.get("universe_includes_delisted")
    rep.checks.append(Check("универсум с делистингами", sv is True,
        "PIT-универсум" if sv is True else
        "универсум только из выживших — доходность завышена (величина неизвестна)",
        severity=evidence_severity))

    # 6. Издержки
    tk = meta.get("taker_bps")
    rep.checks.append(Check("ставка тейкера верна", tk is not None and abs(tk-5.5) < 2.0,
        f"тейкер {tk} bps" if tk is not None else
        "не указана. Была ошибка: считали 8 bps вместо 5.5 и зря хоронили кандидата"))

    # 7. Концентрация по символам
    if by_symbol:
        gross = sum(v for v in by_symbol.values() if v > 0) or 1.0
        best = max(by_symbol.values())
        posf = sum(1 for v in by_symbol.values() if v > 0)/len(by_symbol)
        rep.checks.append(Check("концентрация по монетам", best/gross <= 0.35 and posf >= 0.5,
            f"лучшая монета {best/gross*100:.1f}% прибыли, в плюсе {posf*100:.0f}% монет"))

    # 8. Концентрация по времени
    if by_month:
        vals = list(by_month.values())
        gross = sum(v for v in vals if v > 0) or 1.0
        best = max(vals)
        posf = sum(1 for v in vals if v > 0)/len(vals)
        wo = 1.0
        for v in vals:
            if v != best: wo *= (1+v/100)
        rep.checks.append(Check("концентрация по месяцам", best/gross <= 0.40 and (wo-1) > 0,
            f"лучший месяц {best/gross*100:.1f}% прибыли, без него итог {(wo-1)*100:.1f}%, "
            f"в плюсе {posf*100:.0f}% месяцев"))

    # 8b. Трение: комиссия в долях R
    rp = meta.get("median_risk_pct_of_price")
    fb = meta.get("round_trip_fee_bps")
    if rp and fb:
        fee_R = (fb / 100.0) / rp
        rep.checks.append(Check("трение комиссии", fee_R <= 0.5 * abs(tot / max(1, len(returns)) or 1) or fee_R < 0.02,
            f"комиссия = {fee_R:.4f} R (риск {rp}% цены, круг {fb} bps). "
            f"Тесный стоп усиливает трение: Элдер имел валовой +0.0392R и чистый -0.0096R",
            severity=evidence_severity))

    # 8c. Для денег недостаточно статистического бэктеста: нужны независимый
    # OOS и доказательство, что тот же order path переживает реальные издержки.
    if requires_capital_evidence:
        oos = meta.get("out_of_sample")
        rep.checks.append(Check(
            "независимый OOS",
            oos is True,
            "отдельный OOS/forward зафиксирован" if oos is True else
            "нет подтверждённого независимого OOS/forward",
        ))
        slippage = meta.get("slippage_modelled")
        rep.checks.append(Check(
            "проскальзывание",
            slippage is True,
            "slippage/markout учтён" if slippage is True else
            "slippage не смоделирован и не измерен",
        ))
        parity = meta.get("execution_parity")
        rep.checks.append(Check(
            "execution parity",
            parity is True,
            "исследование и исполнитель используют один order path" if parity is True else
            "нет доказательства parity между сигналом, заявкой и fill",
        ))

    # 9. Ворота качества
    rep.checks.append(Check("Sharpe", sh >= min_sharpe, f"{sh:.2f} (нужно >={min_sharpe})"))
    e = 1.0; pk = 1.0; dd = 0.0
    for x in returns:
        e *= (1+x); pk = max(pk, e); dd = max(dd, (pk-e)/pk)
    rep.checks.append(Check("просадка", dd*100 <= max_dd, f"{dd*100:.1f}% (лимит {max_dd}%)"))

    # 10. Обе половины
    h = len(returns)//2
    t1, _, _ = _stats(returns[:h]); t2, _, _ = _stats(returns[h:])
    rep.checks.append(Check("обе половины времени > 0", t1 > 0 and t2 > 0,
        f"1-я {t1:.1f}%, 2-я {t2:.1f}%"))
    return rep
