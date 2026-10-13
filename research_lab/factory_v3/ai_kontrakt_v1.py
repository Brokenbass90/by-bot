#!/usr/bin/env python3
"""ai_kontrakt_v1.py — контракт ИИ-исследователя (Factory V3, слой 6). 13.10.2026.

Локальная модель (Ollama: qwen3 / deepseek) ПРЕДЛАГАЕТ механизмы. Она НЕ может:
  • задавать пороги, критерии, бюджеты, окна подтверждения/HOLDOUT, судью;
  • трогать риск, размер, плечо, ордера, LIVE;
  • менять статусы гипотез (её максимум — NEW в реестре).
В отличие от bot/deepseek_autoresearch_agent.py (подстройка параметров существующих стратегий = путь к переобучению),
здесь единица работы — МЕХАНИЗМ: кто вынужден/информирован, почему цена движется, почему эффект не выбран арбитражем.

Поток: промпт (PROMPT_SISTEMA) → JSON модели → proverit() → сверка с кладбищем → predlozhit() пишет NEW в реестр.
Сеть не нужна для тестов: klient передаётся снаружи (по умолчанию — Ollama на localhost:11434).
"""
import json, re, urllib.request

ISTOCHNIKI = {   # каталог данных, к которым у Фабрики реально есть доступ (расширяется только человеком)
    "binance_klines_d1": "дневные свечи USD-M Binance 2021+ (taker buy volume)",
    "binance_metrics": "OI, top trader long/short (count/sum), taker long/short ratio, 5 мин, 2021-12+",
    "binance_spot_taker": "дневной спот Binance с taker buy (335 монет)",
    "bybit_kline": "H1/M5 Bybit linear, тени",
    "bybit_funding": "фандинг Bybit 8ч, pit_daily",
    "bybit_oi": "OI Bybit (тень KITY)",
    "kripto_atlas": "спреды/глубина Bybit, снимки каждые 15 мин (с 12.10.2026)",
    "polymarket_snimki": "стаканы/цены Polymarket, снимки с 30.09.2026",
    "liquidations_v2": "ликвидации Bybit, исправленный сборщик Codex (только вперёд)",
    "alpaca_d1": "дневные акции США (PIT вселенная)",
    "deribit_dvol": "DVOL BTC/ETH почасово 2021-04+",
    "fx_gold_m5": "XAUUSD/FX M5 (только после атласа bid/ask — см. FX_GOLD_ADAPTER_SPEC)",
}
GORIZONTY = ["1h", "4h", "1d", "3d", "1w", "2w", "4w"]
OBYAZATELNYE = ["id", "semya", "mehanizm", "pochemu_ne_arbitrazhirovano", "istochniki_dannyh", "priznak",
                "vremya_izvestnosti", "napravlenie", "gorizont", "vselennaya", "kontrol", "falsifikaciya",
                "ozhidaemaya_chastota_v_mesyac", "izderzhki_ocenka_bps"]
ZAPRESHCHENO = re.compile(r"(porog|kriteri|alpha|min_n|t_req|byudzhet|okno_confirm|holdout|sudya|judge|risk|risk_|razmer|"
                          r"leverage|plecho|order|live|money|status|stadiya|pass|kill)", re.I)

PROMPT_SISTEMA = """Ты — исследователь торговых механизмов в строгой Фабрике. Предложи ОДИН новый механизм.
Верни ТОЛЬКО JSON-объект с полями: """ + ", ".join(OBYAZATELNYE) + """.
Правила: механизм объясняет, КТО вынужден или информирован и ПОЧЕМУ цена движется; почему эффект не выбран арбитражем;
признак вычисляется только из данных, известных на момент решения (поле vremya_izvestnosti); источники — только из каталога:
""" + json.dumps(ISTOCHNIKI, ensure_ascii=False) + """
Горизонт — один из """ + ", ".join(GORIZONTY) + """. Направление: "+", "-" или "oba".
Контроль — случайное время/случайная монета/плацебо. Фальсификация — какой результат убивает идею.
ЗАПРЕЩЕНО: пороги значимости, критерии PASS, бюджеты, окна, риск, размер, плечо, ордера, статусы. Это решает не ты.
Не предлагай подстройку параметров существующих стратегий и не повторяй механизмы из списка уже убитых: {kladbische}"""


def _klyuchi(o, put=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield f"{put}.{k}" if put else k
            yield from _klyuchi(v, f"{put}.{k}" if put else k)
    elif isinstance(o, list):
        for x in o: yield from _klyuchi(x, put)


def proverit(obj):
    """Возвращает список ошибок контракта (пусто = соответствует)."""
    if not isinstance(obj, dict): return ["ответ не JSON-объект"]
    err = [f"нет поля {k}" for k in OBYAZATELNYE if k not in obj]
    lishnie = [k for k in _klyuchi(obj) if ZAPRESHCHENO.search(k.split(".")[-1])]
    err += [f"запрещённое поле {k}" for k in lishnie]
    if "id" in obj and not re.fullmatch(r"[A-Z][A-Z0-9_]{3,40}", str(obj["id"])): err.append("id: ЗАГЛАВНЫЕ_С_ПОДЧЁРКИВАНИЕМ, 4–41 символ")
    if len(str(obj.get("mehanizm", ""))) < 60: err.append("механизм слишком короткий (< 60 символов): нужен кто/почему")
    if len(str(obj.get("pochemu_ne_arbitrazhirovano", ""))) < 30: err.append("нет объяснения, почему эффект не выбран")
    ist = obj.get("istochniki_dannyh") or []
    if not isinstance(ist, list) or not ist: err.append("istochniki_dannyh: непустой список")
    err += [f"источник вне каталога: {x}" for x in (ist if isinstance(ist, list) else []) if x not in ISTOCHNIKI]
    if obj.get("gorizont") not in GORIZONTY: err.append(f"gorizont ∈ {GORIZONTY}")
    if obj.get("napravlenie") not in ("+", "-", "oba"): err.append("napravlenie ∈ +, -, oba")
    try:
        if float(obj.get("ozhidaemaya_chastota_v_mesyac", 0)) <= 0: err.append("частота должна быть > 0")
    except (TypeError, ValueError): err.append("частота — число")
    return err


def predlozhit(obj, reestr, model="neizvestno", porog_dubl=0.3):
    """Проверка контракта + кладбище → NEW-гипотеза в реестре. Возвращает dict(status, ...). Статусы не меняет."""
    err = proverit(obj)
    if err: return dict(status="OTKLONENO_KONTRAKT", oshibki=err)
    tekst = f"{obj['mehanizm']} {obj['priznak']} {obj['semya']}"
    dubl = [x for x in reestr.pohozhie(tekst, porog_dubl)]
    if dubl and not obj.get("otlichie_ot_kladbishcha"):
        return dict(status="OTKLONENO_DUBL", pohozhie=dubl[:5])
    S = reestr.sostoyanie()
    sem = S["semi"].get(obj["semya"])
    if sem and sem.get("status") == "KILL": return dict(status="OTKLONENO_DUBL", pohozhie=[(1.0, obj["semya"])])
    if not sem: reestr.semya(obj["semya"], obj["mehanizm"][:200], istochnik=f"ai:{model}")
    gid = f"AI_{obj['id']}"
    if gid in S["gipotezy"]: return dict(status="OTKLONENO_DUBL", pohozhie=[(1.0, gid)])
    reestr.gipoteza(gid, obj["semya"], json.dumps(obj, ensure_ascii=False), obj["istochniki_dannyh"], avtor=f"ai:{model}")
    return dict(status="NEW", gipoteza=gid, flag_cheloveku=bool(dubl))


OPCII_BEZOPASNO = dict(num_ctx=2048, num_predict=512, num_thread=4, temperature=0.3)   # потолки ресурсов (13.10)


def klient_ollama(model="qwen3:8b", host="http://localhost:11434", opcii=None, timeout_s=120):
    """Один ограниченный вызов: контекст/вывод/потоки ограничены, без «размышлений», модель выгружается сразу (keep_alive 0)."""
    def vyzov(sistema, zapros):
        body = json.dumps(dict(model=model, system=sistema, prompt=zapros, format="json", stream=False, think=False,
                               keep_alive=0, options=dict(OPCII_BEZOPASNO, **(opcii or {})))).encode()
        with urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", data=body,
                                                           headers={"Content-Type": "application/json"}), timeout=timeout_s) as r:
            return json.loads(json.loads(r.read())["response"])
    vyzov.model = model
    return vyzov


def raund(reestr, klient, zapros="Предложи механизм.", n=1):
    """Один раунд: n предложений модели через контракт. Ошибки модели не роняют раунд."""
    S = reestr.sostoyanie()
    kladb = ", ".join(sorted(s for s, v in S["semi"].items() if v.get("status") == "KILL"))[:800]
    sistema = PROMPT_SISTEMA.replace("{kladbische}", kladb); out = []
    for _ in range(n):
        try: obj = klient(sistema, zapros)
        except Exception as e:
            out.append(dict(status="OSHIBKA_MODELI", detal=str(e)[:200])); continue
        out.append(predlozhit(obj, reestr, getattr(klient, "model", "neizvestno")))
    return out
