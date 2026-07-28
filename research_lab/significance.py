"""ЗНАЧИМОСТЬ РЕЗУЛЬТАТА С ПОПРАВКОЙ НА РАЗМЕР ПОИСКА.

Отвечает на два вопроса, которых в проекте до сих пор не было:

  1. «Мы отобрали этот результат из N попыток. Насколько он слабее, чем кажется?»
     -> deflated_sharpe(), expected_max_sharpe_under_null()

  2. «Сколько сделок нужно, чтобы вообще что-то различить?»
     -> required_trades(), power_of_sample()

Зачем. В backtest_runs/ лежит 53 467 прогонов. Результат, отобранный как лучший
из десятков тысяч попыток, — принципиально более слабое свидетельство, чем тот же
результат из десяти попыток. Ни один гейт проекта этого не учитывал. Это наиболее
вероятная причина, почему кандидаты стабильно рассыпаются на OOS: их отбирают
из огромного пространства, а судят как одиночную гипотезу.

Источники метода:
  Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio: Correcting for
  Selection Bias, Backtest Overfitting and Non-Normality".

ВАЖНО ПРО ЕДИНИЦЫ. Везде sharpe — ЗА ОДНО НАБЛЮДЕНИЕ (per-trade или per-bar),
НЕ годовой. Это сознательно: в проекте уже была ошибка, где `mu/sd*sqrt(n)`
называлось Sharpe и росло с длиной выборки. Здесь длина выборки входит
отдельным аргументом `n_obs` и никогда не прячется внутрь метрики.
Для перевода: sharpe_annual = sharpe_per_obs * sqrt(наблюдений в году).

Использование:
    from research_lab.significance import assess
    print(assess(returns_R=[...], n_trials=1000).text())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

EULER_GAMMA = 0.5772156649015329


# ─────────────────────────── базовая статистика ────────────────────────────

def _moments(x: Sequence[float]) -> tuple[int, float, float, float, float]:
    """Возвращает (n, mean, std_выборочное, skew, kurtosis_полный).

    kurtosis — ПОЛНЫЙ (нормальное распределение = 3.0), не excess.
    Это важно: формула Bailey/Lopez de Prado ожидает именно полный.
    """
    n = len(x)
    if n < 2:
        return n, 0.0, 0.0, 0.0, 3.0
    mean = sum(x) / n
    var = sum((v - mean) ** 2 for v in x) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return n, mean, 0.0, 0.0, 3.0
    m3 = sum((v - mean) ** 3 for v in x) / n
    m4 = sum((v - mean) ** 4 for v in x) / n
    pop_var = sum((v - mean) ** 2 for v in x) / n
    pop_std = math.sqrt(pop_var)
    skew = m3 / (pop_std ** 3) if pop_std > 0 else 0.0
    kurt = m4 / (pop_var ** 2) if pop_var > 0 else 3.0
    return n, mean, std, skew, kurt


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Обратная функция нормального распределения (Acklam), |err| < 1.15e-9."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ───────────────────── поправка на размер пространства поиска ─────────────────

def expected_max_sharpe_under_null(n_trials: int, sharpe_dispersion: float) -> float:
    """Ожидаемый ЛУЧШИЙ Sharpe из n_trials попыток, если эджа НЕТ вообще.

    Это планка, которую надо побить. Если ваш отобранный Sharpe ниже неё —
    результат неотличим от «прогнали много случайных вариантов и взяли лучший».

    sharpe_dispersion — стандартное отклонение Sharpe МЕЖДУ попытками свипа.
    Если неизвестно, консервативная оценка = 1/sqrt(n_obs).
    """
    n = max(1, int(n_trials))
    if sharpe_dispersion <= 0:
        return 0.0
    # With one preregistered trial there is no winner's-curse hurdle.
    if n == 1:
        return 0.0
    a = _norm_ppf(1.0 - 1.0 / n)
    b = _norm_ppf(1.0 - 1.0 / (n * math.e))
    return sharpe_dispersion * ((1.0 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe(
    sharpe_per_obs: float,
    n_obs: int,
    n_trials: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    sharpe_dispersion: float | None = None,
) -> tuple[float, float]:
    """Deflated Sharpe Ratio. Возвращает (DSR, побитая_планка).

    DSR — вероятность, что истинный Sharpe > 0 С УЧЁТОМ того, что результат
    отобран из n_trials попыток. Читается как p-value наоборот:
    DSR = 0.95 значит «95% уверенности, что эдж настоящий».
    Порог принятия обычно 0.95.
    """
    if n_obs < 2:
        return 0.0, 0.0
    disp = sharpe_dispersion if sharpe_dispersion is not None else 1.0 / math.sqrt(n_obs)
    sr0 = expected_max_sharpe_under_null(n_trials, disp)
    denom_sq = 1.0 - skew * sharpe_per_obs + ((kurtosis - 1.0) / 4.0) * sharpe_per_obs ** 2
    if denom_sq <= 0:
        return 0.0, sr0
    z = (sharpe_per_obs - sr0) * math.sqrt(n_obs - 1) / math.sqrt(denom_sq)
    return _norm_cdf(z), sr0


def min_track_record_length(
    sharpe_per_obs: float,
    *,
    benchmark_sharpe: float = 0.0,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    confidence: float = 0.95,
) -> float:
    """Сколько наблюдений нужно, чтобы Sharpe был статистически значим."""
    edge = sharpe_per_obs - benchmark_sharpe
    if edge <= 0:
        return math.inf
    denom_sq = 1.0 - skew * sharpe_per_obs + ((kurtosis - 1.0) / 4.0) * sharpe_per_obs ** 2
    if denom_sq <= 0:
        return math.inf
    return 1.0 + denom_sq * (_norm_ppf(confidence) / edge) ** 2


# ──────────────────────────── расчёт мощности ────────────────────────────────

def required_trades(
    expectancy_R: float,
    std_R: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    one_sided: bool = True,
) -> int:
    """Сколько сделок нужно, чтобы ОТЛИЧИТЬ эдж от нуля.

    Это ответ на «когда уже можно судить?». Правило N>=40 — эмпирика;
    здесь настоящий расчёт.
    """
    if expectancy_R <= 0 or std_R <= 0:
        return -1
    z_a = _norm_ppf(1.0 - alpha) if one_sided else _norm_ppf(1.0 - alpha / 2.0)
    z_b = _norm_ppf(power)
    return int(math.ceil(((z_a + z_b) * std_R / expectancy_R) ** 2))


def power_of_sample(
    n_trades: int,
    expectancy_R: float,
    std_R: float,
    *,
    alpha: float = 0.05,
    one_sided: bool = True,
) -> float:
    """Какова мощность при УЖЕ имеющемся числе сделок.

    Мощность 0.20 означает: даже если эдж реален, вы увидите его лишь
    в 20% случаев. Отрицательный результат на такой выборке НЕ информативен.
    """
    if n_trades < 2 or std_R <= 0 or expectancy_R <= 0:
        return 0.0
    z_a = _norm_ppf(1.0 - alpha) if one_sided else _norm_ppf(1.0 - alpha / 2.0)
    return _norm_cdf(expectancy_R * math.sqrt(n_trades) / std_R - z_a)


def min_detectable_edge(
    n_trades: int,
    std_R: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    one_sided: bool = True,
) -> float:
    """Минимальный эдж (R/сделка), различимый на данной выборке."""
    if n_trades < 2 or std_R <= 0:
        return math.inf
    z_a = _norm_ppf(1.0 - alpha) if one_sided else _norm_ppf(1.0 - alpha / 2.0)
    z_b = _norm_ppf(power)
    return (z_a + z_b) * std_R / math.sqrt(n_trades)


# ─────────────────────────────── сводный отчёт ───────────────────────────────

@dataclass
class Verdict:
    n: int = 0
    expectancy_R: float = 0.0
    std_R: float = 0.0
    sharpe_per_trade: float = 0.0
    skew: float = 0.0
    kurtosis: float = 3.0
    n_trials: int = 1
    dsr: float = 0.0
    hurdle: float = 0.0
    min_trl: float = 0.0
    power: float = 0.0
    need_n: int = 0
    mde_R: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.dsr >= 0.95 and self.power >= 0.80

    def text(self) -> str:
        o = ["=== ЗНАЧИМОСТЬ С ПОПРАВКОЙ НА РАЗМЕР ПОИСКА ==="]
        o.append(f"  сделок                       n = {self.n}")
        o.append(f"  ожидание                     {self.expectancy_R:+.4f} R/сделку")
        o.append(f"  разброс                      {self.std_R:.4f} R")
        o.append(f"  Sharpe на сделку             {self.sharpe_per_trade:.4f}")
        o.append(f"  скос / эксцесс               {self.skew:+.2f} / {self.kurtosis:.2f}")
        o.append("")
        o.append(f"  попыток отбора               {self.n_trials}")
        o.append(f"  планка от случайности        {self.hurdle:.4f} Sharpe/сделку")
        o.append(f"  DSR (нужно >= 0.95)          {self.dsr:.4f}")
        o.append(f"  нужно наблюдений (MinTRL)    {self.min_trl:.0f}")
        o.append("")
        o.append(f"  мощность сейчас (нужно 0.80) {self.power:.3f}")
        o.append(f"  нужно сделок для решения     {self.need_n}")
        o.append(f"  различимый эдж на этом n     {self.mde_R:+.4f} R/сделку")
        for note in self.notes:
            o.append(f"  ! {note}")
        o.append("ИТОГ: " + ("ЗНАЧИМ с поправкой на отбор" if self.ok
                             else "НЕ ДОКАЗАН — см. причины выше"))
        return "\n".join(o)


def assess(returns_R: Sequence[float], n_trials: int = 1,
           *, alpha: float = 0.05, power_target: float = 0.80,
           sharpe_dispersion: float | None = None) -> Verdict:
    """Полная оценка серии сделок в R с поправкой на n_trials попыток отбора."""
    n, mean, std, skew, kurt = _moments(returns_R)
    v = Verdict(n=n, expectancy_R=mean, std_R=std, skew=skew, kurtosis=kurt,
                n_trials=max(1, int(n_trials)))
    if n < 2 or std <= 0:
        v.notes.append("выборка слишком мала для любых выводов")
        return v
    v.sharpe_per_trade = mean / std
    v.dsr, v.hurdle = deflated_sharpe(
        v.sharpe_per_trade, n, v.n_trials,
        skew=skew, kurtosis=kurt, sharpe_dispersion=sharpe_dispersion)
    v.min_trl = min_track_record_length(
        v.sharpe_per_trade, benchmark_sharpe=v.hurdle, skew=skew, kurtosis=kurt)
    v.power = power_of_sample(n, mean, std, alpha=alpha)
    v.need_n = required_trades(mean, std, alpha=alpha, power=power_target)
    v.mde_R = min_detectable_edge(n, std, alpha=alpha, power=power_target)

    if v.sharpe_per_trade <= v.hurdle:
        v.notes.append(
            f"отобранный Sharpe {v.sharpe_per_trade:.4f} НЕ ПРЕВОСХОДИТ планку "
            f"случайного лучшего из {v.n_trials} попыток ({v.hurdle:.4f})")
    if v.power < 0.80:
        v.notes.append(
            f"мощность {v.power:.2f}: выборки не хватает. Отрицательный результат "
            f"на таком n НЕ доказывает отсутствие эджа")
    if v.min_trl > n:
        v.notes.append(f"нужно ~{v.min_trl:.0f} наблюдений, есть {n}")
    return v
