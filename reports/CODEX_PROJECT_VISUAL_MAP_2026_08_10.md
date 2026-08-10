# Визуальная карта торговой станции

Срез: 2026-08-10 18:55 UTC. Сплошные смысловые связи — целевая архитектура; статусы live
следует читать только вместе со временем и источником.

## 1. Какой это проект

```mermaid
flowchart LR
    M["Рынки и данные<br/>crypto · equities · future FX"] --> D["Версионированный data plane<br/>PIT · quality · snapshots"]
    D --> R["Research factory<br/>VectorBT → causal replay → WF/OOS"]
    R --> I["Independent replay<br/>LEAN · trade-by-trade parity"]
    I --> O["Strategy owner<br/>shadow / canary / money authority"]
    O --> X["Execution engine<br/>intent · orders · fills · protection"]
    X --> B["Broker truth<br/>Bybit · Alpaca · future adapters"]
    B --> C["Reconciliation + accounting<br/>broker ↔ runner ↔ owner ↔ ledger"]
    C --> H["Web / Telegram control tower"]
    C --> A["AI audit plane<br/>Codex · Claude · Ollama · external red-team"]
    A --> F["Finding queue<br/>reproduce → patch → tests → deploy"]
    F --> R
    F --> X
```

## 2. Truth ladder для live

```mermaid
flowchart TD
    G["Git commit<br/>код существует"] --> P["Deploy receipt<br/>bundle + SHA + config"]
    P --> S["Service active<br/>процесс запущен"]
    S --> HB["Fresh heartbeat<br/>runner сообщает state"]
    HB --> BR["Direct broker truth<br/>orders · fills · positions · balance"]
    BR --> RC["Reconciled truth<br/>owner + runner + broker + accounting"]
    RC --> UI["Operator truth<br/>web/TG с freshness и source"]

    G -. "f290463 включен в atomic bundle" .-> P
    P -. "live c5eba1c · 6/6<br/>staged 4757451 · 8/8" .-> S
    BR -. "ADA + DOT shorts open 18:54 UTC<br/>broker stops present" .-> RC
```

Нижний слой не может быть доказан верхним: active service не доказывает flat,
heartbeat не доказывает broker balance, а Git commit не доказывает deploy.

## 3. Promotion funnel

```mermaid
flowchart LR
    H["Hypothesis<br/>causal mechanism"] --> PF["Cheap prefilter<br/>many variants"]
    PF --> PR["Preregister<br/>one change + holdout"]
    PR --> CR["Causal replay<br/>fees · latency · fills"]
    CR --> WF["Walk-forward / OOS<br/>uncertainty"]
    WF --> IR["Independent replay<br/>different engine"]
    IR --> SH["Shadow<br/>real market path"]
    SH --> C1["Tiny canary<br/>owner-approved"]
    C1 --> N20["Clean N20 review"]
    N20 --> N30["Clean N30 decision"]
    N30 --> SC["Risk ladder<br/>0.10 → 0.25 → 0.50"]

    PF -. "FAIL is valuable" .-> AR["Archive with reason"]
    CR -. "harness conflict" .-> FI["Finding + reproduction"]
    SH -. "adverse selection" .-> AR
```

## 4. Текущая карта контуров

```mermaid
flowchart TB
    subgraph Money["Money authority"]
        ATT["ATT1 short-only · risk 0.10<br/>ADA + DOT execution incidents<br/>pause new entries required"]
    end

    subgraph RiskZero["Risk-zero / shadow"]
        B1["BOUNCE1 / IVB1 / midterm<br/>enabled, risk 0"]
        MK["Maker entry<br/>adverse-selection conflict"]
        RT["Retest3<br/>config contract repaired<br/>edge not proven"]
        SB["Sloped break/retest<br/>ms/sec fix tested<br/>reachability open"]
        FU["Funding dynamic/frozen<br/>capital_authorized=false"]
        XS["XSEC v3<br/>median negative; outlier-dominated"]
        AP["Alpaca adaptive<br/>shadow_no_orders"]
        LG["Long-leg program<br/>largest portfolio gap"]
        SD["Six-day research queue<br/>48 bounded cases<br/>no order authority"]
    end

    subgraph SafeHold["Protected but not promotion-ready"]
        AL["Alpaca ABBV + SCHW<br/>equity $485.87 · stops 2/2<br/>SAFE_HOLD"]
    end

    ATT --> REC["Reconciliation gate<br/>pure four-source contract tested<br/>live wiring open"]
    B1 --> REP["Independent replay"]
    MK --> REP
    RT --> REP
    SB --> REP
    FU --> REP
    XS --> REP
    AP --> REP
    LG --> REP
    SD --> REP
    AL --> MKT["Protective apply PASS<br/>SCHW stop 96.47 → 105.03<br/>DAY rearm proof remains"]
```

## 5. Целевая fail-close логика

```mermaid
sequenceDiagram
    participant SO as Strategy owner
    participant RU as Runner
    participant BR as Broker
    participant AC as Accounting
    participant RC as Reconciler
    participant OP as Operator

    SO->>RU: signed intent + authority + idempotency key
    RU->>BR: order request
    BR-->>RU: broker order/fill receipt
    RU->>AC: lifecycle event
    RC->>SO: read expected authority
    RC->>RU: read runner state
    RC->>BR: read direct broker truth
    RC->>AC: read ledger linkage
    alt all equal and fresh
        RC-->>OP: reconciled green truth
    else symbol conflict
        RC->>RU: block new additions on symbol
        RC-->>OP: incident + exact mismatch
        Note over RU,BR: Existing position protection remains active
    else authority or broker truth unavailable
        RC->>RU: global fail-close new exposure
        RC-->>OP: critical incident
    end
```

## 6. Human/AI boundary

```mermaid
flowchart LR
    E["Events · code · reports · logs"] --> IDX["Non-secret hybrid index"]
    IDX --> AI["Codex / Claude / Ollama"]
    AI --> FN["Finding with evidence"]
    FN --> RP["Deterministic reproduction"]
    RP --> PA["Patch"]
    PA --> TS["Tests + independent parity"]
    TS --> DR["Deploy request"]
    DR --> OW{"Owner approval<br/>if capital changes?"}
    OW -- "no capital change" --> DP["Atomic deploy + receipt"]
    OW -- "yes" --> CF["Explicit confirmation"]
    CF --> DP

    AI -. "never directly" .-> NO["Risk change / live order"]
```
