def klaster_st(zn: np.ndarray, mon: np.ndarray, n: int = 1200) -> float:
    """Кластерный бутстрап по монетам. АЛГЕБРАИЧЕСКИ ТО ЖЕ, что
    kross.klaster_z, только без склейки массивов.

    В kross на каждой итерации монеты склеиваются и берётся среднее
    склейки. Среднее склейки монет с кратностями m_i равно
    (Σ m_i·сумма_i) / (Σ m_i·N_i) — то есть его можно получить из двух
    чисел на монету. Тот же посев 23 и тот же вызов rng.choice дают ту же
    последовательность выборок, поэтому и число получается то же.

    Не «похожее» — то же. Проверяется флагом --proverit_sigmu, и проверку
    надо гонять, а не верить комментарию.
    """
    if len(zn) < 50:
        return float("nan")
    mon = np.asarray(mon)
    _, pervye = np.unique(mon, return_index=True)
    uni = mon[np.sort(pervye)]            # порядок первого появления, как в kross
    if len(uni) < 5:
        return float("nan")
    sootv = np.full(int(mon.max()) + 1, -1, dtype=np.int64)
    sootv[uni] = np.arange(len(uni))
    kod = sootv[mon]
    cnt = np.bincount(kod, minlength=len(uni)).astype(float)
    sm = np.bincount(kod, weights=np.asarray(zn, dtype=float), minlength=len(uni))
    rng = np.random.default_rng(23)
    vyb = np.empty(n)
    for i in range(n):
        beru = rng.choice(len(uni), len(uni))
        w = np.bincount(beru, minlength=len(uni)).astype(float)
        zn_ = float((w * cnt).sum())
        vyb[i] = float((w * sm).sum() / zn_) if zn_ > 0 else np.nan
    return float(np.std(vyb))

def klaster_z_bystro(zn: np.ndarray, mon: np.ndarray, n: int = 1200) -> float:
    st = klaster_st(zn, mon, n)
    if not np.isfinite(st) or st <= 0:
        return float("nan")
    return float(np.mean(zn) / st)
