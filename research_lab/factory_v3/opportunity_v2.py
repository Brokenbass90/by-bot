#!/usr/bin/env python3
"""opportunity_v2.py — OpportunityRecord V2 / Evidence Standard v2 (15.10.2026). Причинная запись возможности ДО решения.

Три отдельных append-only журнала (JSONL), каждый — цепочка хешей (prev_hash → record_hash), подделка задним числом видна:
  opportunities  — возможность: что было известно и когда. Исходов здесь нет по построению.
  decisions      — решение политики (BASELINE_V1 / BRAIN_V1) по opp_id: аллокация, сработавшие ограничения Risk Engine.
  joins          — позже и отдельно: исполнение (owner_id Codex) и исход. Исход прикрепляется ОДИН раз; второй, отличающийся, — отказ.

Правила V2 (сверх V1):
  * opp_id = sha256(sleeve|mechanism|version|symbol|side|t_observation_ms)[:32] — уникален, дубль отклоняется;
  * source_ref + source_sha256 — откуда и что именно прочитано (lineage);
  * t_observation_ms ≤ t_available_ms ≤ t_decision_ms; t_recorded_ms пишет журнал; запись позже t_available + LAG_MS → late=True
    (сохраняется, но как причинное свидетельство не считается);
  * любое неизвестное поле = строка "UNKNOWN" (не 0, не пусто); exp_net_bps = UNKNOWN, если неизвестна любая его часть;
  * execution_owner_id = "UNKNOWN" до join от Codex; outcome — только в joins.
"""
import hashlib, json, os, time
from pathlib import Path

SCHEMA = "OpportunityRecord V2"
UNKNOWN = "UNKNOWN"
LAG_MS = 2 * 3600 * 1000
NULEVOY = "0" * 64
POLYA_OPP = ["opp_id", "schema", "source_ref", "source_sha256", "t_observation_ms", "t_available_ms", "t_decision_ms",
             "sleeve", "mechanism", "version", "symbol", "side", "horizon_ms", "context", "features",
             "exp_gross_bps", "cost_fee_bps", "cost_spread_bps", "cost_slip_bps", "cost_funding_bps", "exp_net_bps",
             "uncertainty_bps", "prior_ref", "prior_status", "execution_owner_id"]


class OshibkaV2(Exception):
    pass


def _num_or_unknown(x, imya):
    if x == UNKNOWN: return UNKNOWN
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x:
        raise OshibkaV2(f"{imya}: число или UNKNOWN, получено {x!r}")
    return float(x)


def opp_id(sleeve, mechanism, version, symbol, side, t_observation_ms):
    return hashlib.sha256(f"{sleeve}|{mechanism}|{version}|{symbol}|{int(side)}|{int(t_observation_ms)}".encode()).hexdigest()[:32]


def vozmozhnost(*, source_ref, source_sha256, t_observation_ms, t_available_ms, t_decision_ms, sleeve, mechanism, version, symbol,
                side, horizon_ms, context, features, exp_gross_bps, cost_fee_bps, cost_spread_bps, cost_slip_bps, cost_funding_bps,
                uncertainty_bps, prior_ref, prior_status):
    if side not in (1, -1): raise OshibkaV2("side ∈ {+1, −1}")
    if not (int(t_observation_ms) <= int(t_available_ms) <= int(t_decision_ms)):
        raise OshibkaV2(f"{symbol}: наблюдение {t_observation_ms} ≤ доступность {t_available_ms} ≤ решение {t_decision_ms} нарушено")
    if not isinstance(context, dict) or not isinstance(features, dict): raise OshibkaV2("context/features — словари")
    if not source_sha256 or (source_sha256 != UNKNOWN and len(source_sha256) != 64): raise OshibkaV2("source_sha256: 64 hex или UNKNOWN")
    ch = {k: _num_or_unknown(v, k) for k, v in dict(exp_gross_bps=exp_gross_bps, cost_fee_bps=cost_fee_bps, cost_spread_bps=cost_spread_bps,
                                                       cost_slip_bps=cost_slip_bps, cost_funding_bps=cost_funding_bps,
                                                       uncertainty_bps=uncertainty_bps).items()}
    chasti = [ch["exp_gross_bps"], ch["cost_fee_bps"], ch["cost_spread_bps"], ch["cost_slip_bps"], ch["cost_funding_bps"]]
    net = UNKNOWN if UNKNOWN in chasti else chasti[0] - sum(chasti[1:])
    z = dict(opp_id=opp_id(sleeve, mechanism, version, symbol, side, t_observation_ms), schema=SCHEMA, source_ref=str(source_ref),
             source_sha256=source_sha256, t_observation_ms=int(t_observation_ms), t_available_ms=int(t_available_ms),
             t_decision_ms=int(t_decision_ms), sleeve=sleeve, mechanism=mechanism, version=version, symbol=symbol, side=int(side),
             horizon_ms=int(horizon_ms), context=context, features=features, **ch, exp_net_bps=net, prior_ref=prior_ref,
             prior_status=prior_status, execution_owner_id=UNKNOWN)
    assert list(z) == POLYA_OPP or set(z) == set(POLYA_OPP)
    return z


def _hesh(z):
    return hashlib.sha256(json.dumps(z, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Zhurnal:
    """Append-only JSONL с цепочкой хешей. Проверка цепочки при открытии; разрыв → исключение (не молча)."""
    def __init__(self, put):
        self.put = Path(put); self.put.parent.mkdir(parents=True, exist_ok=True)
        self.zapisi, self.prev = [], NULEVOY
        if self.put.exists():
            for n, l in enumerate(open(self.put, encoding="utf-8")):
                if not l.strip(): continue
                z = json.loads(l); telo = {k: v for k, v in z.items() if k not in ("prev_hash", "record_hash")}
                if z["prev_hash"] != self.prev or z["record_hash"] != _hesh({**telo, "prev_hash": z["prev_hash"]}):
                    raise OshibkaV2(f"{self.put.name}: цепочка хешей разорвана на строке {n + 1}")
                self.zapisi.append(z); self.prev = z["record_hash"]

    def dobavit(self, telo, t_recorded_ms=None):
        telo = dict(telo); telo["t_recorded_ms"] = int(t_recorded_ms if t_recorded_ms is not None else time.time() * 1000)
        z = {**telo, "prev_hash": self.prev}; z["record_hash"] = _hesh(z)
        with open(self.put, "a", encoding="utf-8") as f:
            f.write(json.dumps(z, ensure_ascii=False, sort_keys=True) + "\n"); f.flush(); os.fsync(f.fileno())
        self.zapisi.append(z); self.prev = z["record_hash"]; return z


class Hranilishche:
    """Три журнала Brain Shadow. Решения и исходы связываются только через opp_id."""
    def __init__(self, papka):
        p = Path(papka)
        self.opp, self.dec, self.join = Zhurnal(p / "opportunities.jsonl"), Zhurnal(p / "decisions.jsonl"), Zhurnal(p / "joins.jsonl")
        self.ids = {z["opp_id"] for z in self.opp.zapisi}
        self.resheno = {(z["opp_id"], z["policy"]) for z in self.dec.zapisi}
        self.ishody = {z["opp_id"]: z for z in self.join.zapisi if z["kind"] == "outcome"}
        self.korrekcii = {}                                                       # 21.10: opp_id → последняя коррекция исхода
        for z in self.join.zapisi:
            if z["kind"] == "outcome_correction": self.korrekcii[z["opp_id"]] = z

    def dobavit_vozmozhnost(self, v, t_recorded_ms=None):
        if v["opp_id"] in self.ids: return None                                  # дубль — молча не пишем повторно
        now = int(t_recorded_ms if t_recorded_ms is not None else time.time() * 1000)
        z = self.opp.dobavit({**v, "late": now > v["t_available_ms"] + LAG_MS}, now); self.ids.add(v["opp_id"]); return z

    def dobavit_reshenie(self, opp_id_, policy, policy_sha, allocation_units, constraints, t_recorded_ms=None):
        if opp_id_ not in self.ids: raise OshibkaV2("решение без возможности")
        if opp_id_ in self.ishody: raise OshibkaV2("решение после известного исхода запрещено")
        if (opp_id_, policy) in self.resheno: return None
        z = self.dec.dobavit(dict(opp_id=opp_id_, policy=policy, policy_sha=policy_sha, allocation_units=float(allocation_units),
                                  constraints=list(constraints)), t_recorded_ms)
        self.resheno.add((opp_id_, policy)); return z

    def prikrepit_ishod(self, opp_id_, t_outcome_ms, realized_net_bps, source_ref, source_sha256, t_recorded_ms=None):
        if opp_id_ not in self.ids: raise OshibkaV2("исход без возможности")
        net = _num_or_unknown(realized_net_bps, "realized_net_bps")
        if opp_id_ in self.ishody:
            if self.ishody[opp_id_]["realized_net_bps"] != net: raise OshibkaV2(f"{opp_id_}: исход уже прикреплён и отличается")
            return None
        z = self.join.dobavit(dict(kind="outcome", opp_id=opp_id_, t_outcome_ms=int(t_outcome_ms), realized_net_bps=net,
                                   source_ref=source_ref, source_sha256=source_sha256), t_recorded_ms)
        self.ishody[opp_id_] = z; return z

    def ispravit_ishod(self, opp_id_, realized_net_bps, prichina, source_ref, source_sha256, t_recorded_ms=None):
        """21.10.2026: исправление ошибочного исхода ОТДЕЛЬНЫМ событием (append-only). Исходная запись не меняется и остаётся
        в цепочке; коррекция ссылается на хеш исправляемой записи и обязана иметь причину. Расчёты берут ishod_aktualnyy()."""
        if opp_id_ not in self.ishody: raise OshibkaV2("коррекция без исходного исхода")
        if not str(prichina or "").strip(): raise OshibkaV2("коррекция без причины не принимается")
        net = _num_or_unknown(realized_net_bps, "realized_net_bps")
        pred = self.korrekcii.get(opp_id_) or self.ishody[opp_id_]
        if pred["realized_net_bps"] == net: return None                          # ничего не меняет — не пишем
        z = self.join.dobavit(dict(kind="outcome_correction", opp_id=opp_id_, realized_net_bps=net, corrects=pred["record_hash"],
                                   prichina=str(prichina), source_ref=source_ref, source_sha256=source_sha256), t_recorded_ms)
        self.korrekcii[opp_id_] = z; return z

    def ishod_aktualnyy(self, opp_id_):
        """Последняя версия исхода: коррекция, если есть, иначе исходная запись; None — исхода нет."""
        return self.korrekcii.get(opp_id_) or self.ishody.get(opp_id_)

    def prikrepit_ispolnenie(self, opp_id_, execution_owner_id, detali, t_recorded_ms=None):
        if opp_id_ not in self.ids: raise OshibkaV2("исполнение без возможности")
        return self.join.dobavit(dict(kind="execution", opp_id=opp_id_, execution_owner_id=str(execution_owner_id), detali=detali), t_recorded_ms)
