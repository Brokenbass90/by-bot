#!/usr/bin/env python3
"""ai_shlyuz_v1.py — ИИ-шлюз фабрики (слой 6). 13.10.2026.

Роли ИИ в системе (чтобы не путать):
  • торговый мозг — НЕ языковая модель (ML-скорер на признаках, детерминированный, проверяемый на истории);
  • прозвонка кода — тесты, известные ответы, подсаженный край, линтеры (бесплатно, строго);
  • отчёты — шаблоны (svodka_v1);
  • гипотезы и разбор кладбища — языковая модель ЧЕРЕЗ КОНТРАКТ (ai_kontrakt_v1) и ЧЕРЕЗ ЭТОТ ШЛЮЗ.

Порядок провайдеров: локальная модель (бесплатно, ai_raund.py с потолками RAM) → DeepSeek API для качественных раундов.
Гарантии DeepSeek-клиента:
  • ключ только из переменной окружения DEEPSEEK_API_KEY; никогда не пишется в лог, не печатается;
  • перед отправкой — проверка на утечку (ключи, пароли, .env, длинные hex/base64): нашлось → отказ, ничего не уходит;
  • потолки: вход ≤ 12 000 символов, вывод ≤ 800 токенов, таймаут 90 с;
  • месячный бюджет (по умолчанию $2): до вызова считается худший случай; не помещается → отказ;
  • расход пишется в data/factory_v3/ai_rashod.jsonl (только размеры, токены, цена, sha запроса — без текста).
Цены — консервативный верх для deepseek-v4-flash, USD за 1M токенов; меняются аргументами.

    python3 research_lab/factory_v3/ai_shlyuz_v1.py --rashod
    python3 research_lab/factory_v3/ai_shlyuz_v1.py --raund [--n 1..3] [--zapisat]     # по умолчанию сухой: копия реестра
"""
import argparse, datetime as dt, fcntl, hashlib, json, os, re, shutil, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
D = HERE.parent / "data" / "factory_v3"
RASHOD = D / "ai_rashod.jsonl"
URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
CENA_VHOD, CENA_VYHOD = 0.44, 1.32            # USD / 1M токенов, верх диапазона
BYUDZHET_USD_MESYAC = 2.0
MAKS_VHOD_SIMV, MAKS_VYHOD_TOK, TIMEOUT_S = 12_000, 800, 90
UTECHKA = re.compile(r"(api[_-]?key|secret|passw|token\s*[:=]|private key|BEGIN [A-Z ]*KEY|\.env\b|signal_copy/config|"
                     r"sk-[A-Za-z0-9]{16,}|\b[0-9a-fA-F]{32,}\b|\b[A-Za-z0-9+/]{40,}={0,2})", re.I)


class OtkazShlyuza(Exception):
    pass


def _mesyac(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def potracheno(mesyac=None, put=None):
    put = Path(put or RASHOD); mesyac = mesyac or _mesyac()
    if not put.exists(): return 0.0
    with open(put) as f:
        return round(sum(r["usd"] for r in (json.loads(l) for l in f if l.strip()) if r["kogda"].startswith(mesyac)), 6)


def stoimost(vhod_tok, vyhod_tok, cv=CENA_VHOD, cvy=CENA_VYHOD):
    return (vhod_tok * cv + vyhod_tok * cvy) / 1e6


def proverit_utechku(*teksty):
    for t in teksty:
        m = UTECHKA.search(t or "")
        if m: raise OtkazShlyuza(f"похоже на секрет/конфиг в запросе (шаблон «{m.group(0)[:12]}…») — ничего не отправлено")


def _otpravit_http(url, klyuch, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {klyuch}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def klient_deepseek(model=MODEL, byudzhet_usd=BYUDZHET_USD_MESYAC, put_rashoda=None, url=URL, otpravit=_otpravit_http,
                    klyuch=None, maks_vyhod=MAKS_VYHOD_TOK):
    """Клиент с тем же интерфейсом, что klient_ollama: vyzov(sistema, zapros) -> dict (JSON-ответ модели)."""
    put = Path(put_rashoda or RASHOD)

    def vyzov(sistema, zapros):
        k = klyuch if klyuch is not None else os.environ.get("DEEPSEEK_API_KEY", "")
        if not k: raise OtkazShlyuza("нет DEEPSEEK_API_KEY в окружении — платный провайдер выключен")
        if len(sistema) + len(zapros) > MAKS_VHOD_SIMV: raise OtkazShlyuza(f"запрос длиннее {MAKS_VHOD_SIMV} символов")
        proverit_utechku(sistema, zapros)
        hudshiy = stoimost((len(sistema) + len(zapros)) / 2, maks_vyhod)        # ≥ 1 токен на 2 символа — с запасом
        put.parent.mkdir(parents=True, exist_ok=True)
        with open(put, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            uzhe = potracheno(put=put)
            if uzhe + hudshiy > byudzhet_usd:
                raise OtkazShlyuza(f"месячный бюджет ${byudzhet_usd}: потрачено ${uzhe:.4f}, худший случай вызова ${hudshiy:.4f}")
            body = dict(model=model, messages=[dict(role="system", content=sistema), dict(role="user", content=zapros)],
                        max_tokens=maks_vyhod, temperature=0.3, response_format={"type": "json_object"}, stream=False)
            otvet = otpravit(url, k, body, TIMEOUT_S)
            u = otvet.get("usage") or {}
            vh, vy = int(u.get("prompt_tokens", hudshiy and (len(sistema) + len(zapros)) // 2)), int(u.get("completion_tokens", maks_vyhod))
            f.write(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), model=model,
                                    vhod_tok=vh, vyhod_tok=vy, usd=round(stoimost(vh, vy), 6),
                                    zapros_sha=hashlib.sha256((sistema + zapros).encode()).hexdigest()[:16])) + "\n")
        return json.loads(otvet["choices"][0]["message"]["content"])
    vyzov.model = model
    return vyzov


def main(argv=None, klient=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--rashod", action="store_true"); ap.add_argument("--raund", action="store_true")
    ap.add_argument("--n", type=int, default=1); ap.add_argument("--zapisat", action="store_true")
    ap.add_argument("--zapros", default="Предложи механизм, независимый от уже убитых, на данных из каталога.")
    a = ap.parse_args(argv)
    if a.rashod or not a.raund:
        print(f"расход {_mesyac()}: ${potracheno():.4f} из ${BYUDZHET_USD_MESYAC}"); return 0
    if not 1 <= a.n <= 3: print("n ∈ [1, 3]"); return 2
    import ai_kontrakt_v1 as A
    from reestr_v1 import Reestr, PUT_PO_UMOLCHANIYU
    if a.zapisat: r = Reestr()
    else:
        tmp = Path(tempfile.mkdtemp()) / "reestr_kopiya.jsonl"
        if PUT_PO_UMOLCHANIYU.exists(): shutil.copy(PUT_PO_UMOLCHANIYU, tmp)
        r = Reestr(tmp)
    rez = A.raund(r, klient or klient_deepseek(), a.zapros, a.n)
    print(f"DeepSeek, {'ЗАПИСЬ в реестр' if a.zapisat else 'сухой прогон (в проект ничего не записано)'}; расход месяца ${potracheno():.4f}")
    for x in rez: print(" ", json.dumps(x, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
