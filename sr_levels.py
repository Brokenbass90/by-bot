# sr_levels.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import time
import statistics
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from indicators import atr_pct_from_ohlc


# =========================
# Models
# =========================

@dataclass
class Level:
    price: float
    kind: str          # "support" | "resistance"
    tf: str            # "1h" | "4h"
    score: float
    touches: int
    last_ts: int       # unix seconds


# =========================
# Helpers
# =========================

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_pct_dist(a: float, b: float) -> float:
    return abs(a - b) / max(1e-12, b) * 100.0


def _atr_pct(h: List[float], l: List[float], c: List[float], period: int = 14) -> float:
    """
    Обёртка над indicators.atr_pct_from_ohlc для сохранения старого API.
    """
    return atr_pct_from_ohlc(h, l, c, period=period, fallback=0.8)


# =========================
# HTTP session (retry)
# =========================

_SESS = requests.Session()
_retry = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=0.4,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=32, pool_maxsize=32)
_SESS.mount("https://", _adapter)
_SESS.mount("http://", _adapter)


def _fetch_bybit_klines(
    base_url: str,
    symbol: str,
    interval: str,
    limit: int,
) -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """
    Bybit v5 /market/kline
    interval:
      "60"  = 1h
      "240" = 4h
    Returns: t,o,h,l,c (t in seconds, chronological)
    """
    url = f"{base_url.rstrip('/')}/v5/market/kline"
    r = _SESS.get(
        url,
        params={"category": "linear", "symbol": symbol, "interval": interval, "limit": int(limit)},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("retCode")) != "0":
        raise RuntimeError(f"kline error: {j}")

    rows = (j.get("result") or {}).get("list") or []
    if not rows:
        raise RuntimeError(f"kline empty: symbol={symbol} interval={interval}")

    rows.reverse()  # chronological

    t = [int(int(x[0]) // 1000) for x in rows]
    o = [float(x[1]) for x in rows]
    h = [float(x[2]) for x in rows]
    l = [float(x[3]) for x in rows]
    c = [float(x[4]) for x in rows]
    return t, o, h, l, c


def _pivots(
    t: List[int],
    h: List[float],
    l: List[float],
    swing_n: int,
) -> List[Tuple[float, str, int]]:
    """
    Swing highs/lows (fractals).
    Returns list of (price, kind, ts).
    """
    out: List[Tuple[float, str, int]] = []
    n = int(max(1, swing_n))
    if len(h) < (2 * n + 3):
        return out

    for i in range(n, len(h) - n):
        hi = h[i]
        lo = l[i]
        if hi == max(h[i - n : i + n + 1]):
            out.append((hi, "resistance", t[i]))
        if lo == min(l[i - n : i + n + 1]):
            out.append((lo, "support", t[i]))
    return out


def _cluster_levels(
    cands: List[Tuple[float, str, int]],
    tol_pct: float,
    tf: str,
    *,
    tf_weight: float = 1.0,
    recency_days_cap: float = 10.0,
    recency_weight: float = 0.45,
) -> List[Level]:
    """
    Cluster pivot candidates into zones by tol_pct.
    - cluster key is "kind" and distance <= tol_pct
    - cluster price = median of assigned prices
    - score uses touches + recency bonus, multiplied by tf_weight
    """
    tol_pct = float(max(0.01, tol_pct))
    clusters: List[dict] = []

    for price, kind, ts in cands:
        price = float(price)
        ts = int(ts)

        placed = False
        for cl in clusters:
            if cl["kind"] != kind:
                continue
            if _safe_pct_dist(price, cl["price"]) <= tol_pct:
                cl["prices"].append(price)
                cl["touches"] += 1
                cl["last_ts"] = max(cl["last_ts"], ts)
                cl["price"] = statistics.median(cl["prices"])
                placed = True
                break

        if not placed:
            clusters.append(
                {
                    "kind": str(kind),
                    "price": price,
                    "prices": [price],
                    "touches": 1,
                    "last_ts": ts,
                }
            )

    now = int(time.time())
    levels: List[Level] = []
    for cl in clusters:
        touches = int(cl["touches"])
        last_ts = int(cl["last_ts"])
        recency_days = max(0.0, (now - last_ts) / 86400.0)

        recency_bonus = max(0.0, float(recency_days_cap) - recency_days) * float(recency_weight)
        score = (touches * 1.0 + recency_bonus) * float(tf_weight)

        levels.append(
            Level(
                price=float(cl["price"]),
                kind=str(cl["kind"]),
                tf=str(tf),
                score=float(score),
                touches=touches,
                last_ts=last_ts,
            )
        )

    levels.sort(key=lambda x: x.score, reverse=True)
    return levels


def _merge_1h_into_4h(lv4: List[Level], lv1: List[Level], tol4_pct: float) -> List[Level]:
    tol4_pct = float(max(0.01, tol4_pct))
    out: List[Level] = [Level(**vars(x)) for x in lv4]

    for one in lv1:
        absorbed = False
        for z in out:
            if z.kind != one.kind:
                continue
            if _safe_pct_dist(one.price, z.price) <= tol4_pct:
                z.score += 0.35 * one.score
                z.touches += one.touches
                z.last_ts = max(z.last_ts, one.last_ts)
                absorbed = True
                break
        if not absorbed:
            out.append(one)

    out.sort(key=lambda x: x.score, reverse=True)
    return out


# =========================
# Service
# =========================

class LevelsService:
    """
    Cached SR levels (1h + 4h) per symbol.
    """

    def __init__(
        self,
        base_url: str,
        ttl_sec: int = 900,
        limit_1h: int = 700,
        limit_4h: int = 400,
        *,
        swing_n_1h: int = 2,
        swing_n_4h: int = 3,
        max_levels: int = 18,
        tf_weight_4h: float = 1.25,
        # tol multipliers and clamps (percent)
        tol_mul_1h: float = 0.30,
        tol_mul_4h: float = 0.22,
        tol_1h_min: float = 0.20,
        tol_1h_max: float = 0.90,
        tol_4h_min: float = 0.25,
        tol_4h_max: float = 0.80,
    ):
        self.base_url = base_url.rstrip("/")
        self.ttl = int(ttl_sec)
        self.limit_1h = int(limit_1h)
        self.limit_4h = int(limit_4h)

        self.swing_n_1h = int(swing_n_1h)
        self.swing_n_4h = int(swing_n_4h)
        self.max_levels = int(max_levels)

        self.tf_weight_4h = float(tf_weight_4h)

        self.tol_mul_1h = float(tol_mul_1h)
        self.tol_mul_4h = float(tol_mul_4h)
        self.tol_1h_min = float(tol_1h_min)
        self.tol_1h_max = float(tol_1h_max)
        self.tol_4h_min = float(tol_4h_min)
        self.tol_4h_max = float(tol_4h_max)

        self._cache: Dict[str, Tuple[int, List[Level], dict]] = {}

    def get(self, symbol: str) -> Tuple[List[Level], dict]:
        """
        Returns: (levels, meta)
        Если Bybit временно глючит — отдаём последний кэш (пусть даже протухший),
        чтобы бот не падал.
        """
        now = int(time.time())
        row = self._cache.get(symbol)
        if row and now - row[0] <= self.ttl:
            return row[1], row[2]

        try:
            # -------- 1h --------
            t1, _, h1, l1, c1 = _fetch_bybit_klines(self.base_url, symbol, interval="60", limit=self.limit_1h)
            atr1 = _atr_pct(h1, l1, c1, 14)
            tol1 = _clamp(self.tol_mul_1h * atr1, self.tol_1h_min, self.tol_1h_max)

            # -------- 4h --------
            t4, _, h4, l4, c4 = _fetch_bybit_klines(self.base_url, symbol, interval="240", limit=self.limit_4h)
            atr4 = _atr_pct(h4, l4, c4, 14)
            tol4 = _clamp(self.tol_mul_4h * atr4, self.tol_4h_min, self.tol_4h_max)

            # -------- pivots -> clusters --------
            cands1 = _pivots(t1, h1, l1, swing_n=self.swing_n_1h)
            cands4 = _pivots(t4, h4, l4, swing_n=self.swing_n_4h)

            lv1 = _cluster_levels(cands1, tol_pct=tol1, tf="1h", tf_weight=1.0)
            lv4 = _cluster_levels(cands4, tol_pct=tol4, tf="4h", tf_weight=self.tf_weight_4h)

            # merge 1h into 4h zones
            levels = _merge_1h_into_4h(lv4, lv1, tol4_pct=tol4)

            # cap list
            levels = levels[: max(1, self.max_levels)]

            meta = {
                "atr_1h_pct": float(atr1),
                "atr_4h_pct": float(atr4),
                "tol_1h_pct": float(tol1),
                "tol_4h_pct": float(tol4),
                "swing_n_1h": int(self.swing_n_1h),
                "swing_n_4h": int(self.swing_n_4h),
                "max_levels": int(self.max_levels),
                "tf_weight_4h": float(self.tf_weight_4h),
            }

            self._cache[symbol] = (now, levels, meta)
            return levels, meta

        except Exception:
            # fallback: last cached (even if stale)
            if row:
                return row[1], row[2]
            # absolutely no cache: return empty safe defaults
            return [], {
                "atr_1h_pct": 0.0,
                "atr_4h_pct": 0.0,
                "tol_1h_pct": float(self.tol_1h_min),
                "tol_4h_pct": float(self.tol_4h_min),
                "swing_n_1h": int(self.swing_n_1h),
                "swing_n_4h": int(self.swing_n_4h),
                "max_levels": int(self.max_levels),
                "tf_weight_4h": float(self.tf_weight_4h),
            }

    # ---------- navigation helpers ----------
    @staticmethod
    def nearest_above(levels: List[Level], price: float, kind_filter: Optional[str] = None) -> Optional[Level]:
        cands = [lv for lv in levels if lv.price > price and (kind_filter is None or lv.kind == kind_filter)]
        return min(cands, key=lambda lv: lv.price) if cands else None

    @staticmethod
    def nearest_below(levels: List[Level], price: float, kind_filter: Optional[str] = None) -> Optional[Level]:
        cands = [lv for lv in levels if lv.price < price and (kind_filter is None or lv.kind == kind_filter)]
        return max(cands, key=lambda lv: lv.price) if cands else None

    @staticmethod
    def best_near(
        levels: List[Level],
        price: float,
        tol_pct: float,
        *,
        tf_prefer: Optional[str] = None,
        tie_dist_eps_pct: float = 0.02,
    ) -> Optional[Level]:
        tol_pct = float(max(0.01, tol_pct))
        best: Optional[Level] = None
        best_dist = 1e18

        for lv in levels:
            dist = _safe_pct_dist(price, lv.price)
            if dist > tol_pct:
                continue

            if best is None or dist < best_dist - 1e-12:
                best = lv
                best_dist = dist
                continue

            if tf_prefer and abs(dist - best_dist) <= float(tie_dist_eps_pct):
                if lv.tf == tf_prefer and best.tf != tf_prefer:
                    best = lv
                    best_dist = dist

        return best
