# -*- coding: utf-8 -*-
"""signal_copy — веб-интерфейс. Свой процесс, свой порт, своя база.

Запуск:
    cd signal_copy && python3 app.py
    открыть http://127.0.0.1:8766

Выключить = остановить процесс. Основной бот об этом модуле не знает.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn

import traceback
from datetime import datetime, timedelta, timezone

import chat
import config
import store
from mt5_mcp import MT5MCP, MT5Error
from pipeline import build_cards, persist_and_arm
from executor import (execute_approved, move_sl, list_positions,
                      close_position, breakeven)

app = FastAPI(title="signal_copy", docs_url=None, redoc_url=None)
_mcp = MT5MCP(config.MT5_URL, config.MT5_TOKEN)


def mcp() -> MT5MCP:
    if not _mcp.session_id:
        _mcp.connect()
    return _mcp


@app.get("/api/status")
def status():
    try:
        m = mcp()
        acc, term = m.account(), m.terminal()
        pos = m.positions()
    except MT5Error as e:
        _mcp.session_id = None
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)
    try:
        syms = [s["symbol"] for s in m.symbols() if float(s.get("bid") or 0) > 0]
    except MT5Error:
        syms = []
    return {"ok": True, "account": acc, "terminal": term, "positions": pos,
            "symbols": syms,
            "config": {"risk_pct": config.RISK_PCT, "max_risk_pct": config.MAX_RISK_PCT,
                       "max_positions": config.MAX_POSITIONS, "tp": config.DEFAULT_TP,
                       "allow_live": config.ALLOW_LIVE}}


@app.post("/api/parse")
def api_parse(text: str = Body(..., embed=True), use_llm: bool = Body(True, embed=True)):
    try:
        m = mcp()
        conn = store.connect()
        cards = build_cards(text, m, conn, use_llm=use_llm)
        cards = persist_and_arm(cards, text, m, conn)
        return {"ok": True, "cards": [c.as_dict() for c in cards]}
    except MT5Error as e:
        _mcp.session_id = None
        return {"ok": False, "error": str(e)}


@app.post("/api/execute")
def api_execute(token: str = Body(..., embed=True)):
    try:
        return execute_approved(token, mcp(), store.connect())
    except MT5Error as e:
        _mcp.session_id = None
        return {"ok": False, "error": str(e)}
    except Exception as e:
        # Ничего не должно вылетать наверх: 500 в браузере не объясняет, что
        # случилось, и не говорит, ушёл ордер или нет.
        tb = traceback.format_exc()
        print("\n=== СБОЙ ПРИ ОТПРАВКЕ ОРДЕРА ===\n" + tb, flush=True)
        try:
            store.log(store.connect(), None, "execute_crash", tb)
        except Exception:
            pass
        return {"ok": False, "error": f"внутренний сбой: {type(e).__name__}: {e}",
                "traceback": tb.splitlines()[-6:]}


@app.post("/api/move_sl")
def api_move_sl(group_id: int = Body(...), new_sl: float = Body(...)):
    return move_sl(group_id, new_sl, mcp(), store.connect())


@app.get("/api/positions")
def api_positions():
    try:
        return {"ok": True, "positions": list_positions(mcp(), store.connect())}
    except MT5Error as e:
        _mcp.session_id = None
        return {"ok": False, "error": str(e), "positions": []}


@app.post("/api/close")
def api_close(ticket: int = Body(...), symbol: str = Body(...)):
    try:
        return close_position(ticket, symbol, mcp(), store.connect())
    except MT5Error as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/breakeven")
def api_breakeven(ticket: int = Body(...), symbol: str = Body(...)):
    try:
        return breakeven(ticket, symbol, mcp(), store.connect())
    except MT5Error as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/chat")
def api_chat(message: str = Body(""), images: list = Body(default=[])):
    try:
        return chat.ask(message, mcp(), store.connect(), images=images or None)
    except MT5Error as e:
        _mcp.session_id = None
        return {"ok": False, "error": str(e)}


@app.post("/api/chat/clear")
def api_chat_clear():
    chat.clear_history()
    return {"ok": True}


@app.get("/api/chat/history")
def api_chat_history():
    return {"history": chat.load_history()}


PERIOD_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
              "H1": 60, "H4": 240, "D1": 1440}


@app.get("/api/chart")
def api_chart(symbol: str = "EURUSD", period: str = "H1", bars: int = 300):
    """Свечи берём у самого терминала — те же данные, по которым торгуем."""
    period = period.upper()
    if period not in PERIOD_MIN:
        return {"ok": False, "error": f"неизвестный таймфрейм {period}"}
    span = timedelta(minutes=PERIOD_MIN[period] * max(10, bars) * 2)
    now = datetime.now(timezone.utc)
    try:
        got = mcp().call("get_chart_history", symbol=symbol, period=period,
                         datetime_from=(now - span).strftime("%Y-%m-%dT%H:%M:%S"),
                         datetime_to=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                         limit=int(bars))
    except MT5Error as e:
        _mcp.session_id = None
        return {"ok": False, "error": str(e)}
    rows = got.get("rates") or got.get("candles") or got.get("bars") or []
    if isinstance(got, list):
        rows = got
    out = []
    for r in rows:
        t = r.get("time") or r.get("datetime") or r.get("ts")
        if isinstance(t, str):
            t = t.replace(" ", "T").replace(".", "-", 2)
            try:
                t = int(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp())
            except ValueError:
                continue
        out.append({"time": int(t),
                    "open": float(r.get("open", 0)), "high": float(r.get("high", 0)),
                    "low": float(r.get("low", 0)), "close": float(r.get("close", 0))})
    out.sort(key=lambda x: x["time"])
    return {"ok": True, "symbol": symbol, "period": period, "candles": out,
            "raw_keys": list(rows[0].keys()) if rows else []}


@app.post("/api/input")
def api_input(text: str = Body(""), images: list = Body(default=[]),
              use_llm: bool = Body(True)):
    """Одно окно ввода. Сам решает: это сигнал канала или вопрос к боту."""
    from parser_v2 import split_signals, classify
    body = (text or "").strip()
    kinds = {classify(b) for b in split_signals(body)} if body else set()
    is_signal = bool(kinds & {"SIGNAL", "MOVE_SL_BE", "MOVE_SL",
                              "RESULT_TP", "RESULT_SL", "CLOSE_PARTIAL", "CLOSE_ALL"})
    if images or not is_signal:
        try:
            r = chat.ask(body, mcp(), store.connect(), images=images or None)
        except MT5Error as e:
            _mcp.session_id = None
            r = {"ok": False, "error": str(e)}
        return {"mode": "chat", **r}
    try:
        m, conn = mcp(), store.connect()
        cards = persist_and_arm(build_cards(body, m, conn, use_llm=use_llm), body, m, conn)
        return {"mode": "signal", "ok": True, "cards": [c.as_dict() for c in cards]}
    except MT5Error as e:
        _mcp.session_id = None
        return {"mode": "signal", "ok": False, "error": str(e)}


@app.get("/api/testsignal")
def api_testsignal(symbol: str = "EURUSD", side: str = "BUY", risk_r: float = 1.0):
    """Собрать тестовый сигнал вокруг ЖИВОЙ цены — чтобы он не был протухшим.

    Нужен только для проверки цепочки: формат один в один как у канала.
    """
    try:
        spec = mcp().symbol(symbol)
    except MT5Error as e:
        return {"ok": False, "error": str(e)}
    bid, ask = float(spec.get("bid") or 0), float(spec.get("ask") or 0)
    if bid <= 0:
        return {"ok": False, "error": f"нет котировок по {symbol}"}
    digits = int(spec.get("digits") or 5)
    point = float(spec.get("point") or 10 ** -digits)
    side = side.upper()
    # стоп на расстоянии ~30 спредов, цели по 1..4 R
    spread = max(ask - bid, point * 5)
    dist = max(spread * 30, point * 100)
    r = lambda x: round(x, digits)
    if side == "BUY":
        lo, hi = r(bid - spread * 2), r(ask + spread * 2)
        sl = r(bid - dist)
        tps = [r(ask + dist * k) for k in (0.6, 1.2, 2.0, 3.0)]
        arrow, tag = "📈", "BUY"
    else:
        lo, hi = r(bid - spread * 2), r(ask + spread * 2)
        sl = r(ask + dist)
        tps = [r(bid - dist * k) for k in (0.6, 1.2, 2.0, 3.0)]
        arrow, tag = "📉", "SELL"
    pretty = symbol[:3] + "/" + symbol[3:] if len(symbol) == 6 else symbol
    text = (f"{arrow}{tag} {pretty}\n\n{lo} - {hi}\n\n"
            f"📌Stop loss (SL): {sl}\n\n"
            + "\n".join(f"• Take profit {i+1}: {t}" for i, t in enumerate(tps)))
    return {"ok": True, "text": text, "bid": bid, "ask": ask,
            "note": "сигнал собран вокруг текущей цены, поэтому не протухший"}


@app.get("/api/trades")
def api_trades():
    conn = store.connect()
    return {"trades": [dict(r) for r in store.recent_groups(conn, 40)]}


PAGE = r"""<!doctype html><html lang=ru><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>signal_copy</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.js"></script>
<style>
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:#12141a;color:#e8eaf0;font:15px/1.5 -apple-system,system-ui,sans-serif;
  display:flex;flex-direction:column;overflow:hidden}
.top{padding:10px 16px;border-bottom:1px solid #1f2430;display:flex;gap:16px;
  align-items:center;flex-wrap:wrap;font-size:13px;flex:0 0 auto}
.top h1{font-size:15px;margin:0 14px 0 0;font-weight:600;white-space:nowrap}
.top b{color:#fff}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.on{background:#3fb950}.off{background:#f85149}
.mid{flex:1 1 auto;display:flex;min-height:0}
.feed{flex:1 1 auto;display:flex;flex-direction:column;min-width:0;border-right:1px solid #1f2430}
#log{flex:1 1 auto;overflow-y:auto;padding:16px}
.rail{width:290px;flex:0 0 290px;overflow-y:auto;padding:12px;background:#0f1117}
.rail h3{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#6e7681;
  margin:12px 0 7px;font-weight:600}
.bottom{flex:0 0 auto;border-top:1px solid #1f2430;background:#0f1117}
.chartbar{padding:7px 14px;display:flex;gap:8px;align-items:center;font-size:13px}
#chart{height:230px}
.compose{padding:10px 16px;border-top:1px solid #1f2430;flex:0 0 auto}
textarea{width:100%;background:#0d0f14;color:#e8eaf0;border:1px solid #272b38;
  border-radius:10px;padding:10px;font:14px/1.45 ui-monospace,Menlo,monospace;
  resize:none;min-height:62px;max-height:180px}
button{background:#2f6feb;color:#fff;border:0;border-radius:8px;padding:7px 14px;
  font-size:13px;font-weight:600;cursor:pointer}
button:hover{filter:brightness(1.15)}button:disabled{background:#3a3f4d;cursor:not-allowed}
.ghost{background:#272b38}.go{background:#238636}.red{background:#8b2c2c}
.mini{padding:4px 9px;font-size:12px}
select{background:#1a1d26;color:#e8eaf0;border:1px solid #272b38;border-radius:7px;padding:5px 8px}
.row{display:flex;gap:8px;align-items:center;margin:9px 0;flex-wrap:wrap}
.b{max-width:78%;padding:9px 13px;border-radius:13px;margin:8px 0;white-space:pre-wrap;font-size:14px}
.me{background:#2f6feb;color:#fff;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1e222c;border-bottom-left-radius:4px}
.b img{max-width:100%;border-radius:8px;margin-top:6px;display:block}
.card{background:#1a1d26;border:1px solid #272b38;border-left-width:4px;border-radius:10px;
  padding:12px 14px;margin:10px 0;max-width:640px}
.card.ok{border-left-color:#3fb950}.card.no{border-left-color:#f85149}
.card.info{border-left-color:#6e7681}
.t{font-size:15px;font-weight:600;margin-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0}
td{padding:2px 10px 2px 0;color:#9aa3b2;vertical-align:top}
td.v{color:#e8eaf0;font-family:ui-monospace,Menlo,monospace}
.msg{font-size:13px;padding:6px 10px;border-radius:6px;margin:4px 0}
.err{background:#3d1418;color:#ff8b8b}.warn{background:#3a3016;color:#f0c674}
.good{background:#12331c;color:#7ee787}
.eng{font-size:11px;color:#6e7681;margin-top:6px;font-family:ui-monospace,monospace}
pre{background:#0d0f14;border-radius:8px;padding:8px;font-size:12px;overflow:auto;
   color:#8b949e;white-space:pre-wrap;margin:6px 0 0}
.pin{background:#1a1d26;border:1px solid #272b38;border-left:3px solid #6e7681;
  border-radius:8px;padding:8px 10px;margin:6px 0;cursor:pointer;font-size:13px}
.pin:hover{background:#20242f}
.pin.sel{border-color:#2f6feb;background:#1c2333}
.pin.win{border-left-color:#3fb950}.pin.lose{border-left-color:#f85149}
.pin b{font-size:13px}
.pin .sub{color:#6e7681;font-size:12px;font-family:ui-monospace,Menlo,monospace}
.thumb{display:inline-block;position:relative;margin:5px 6px 0 0}
.thumb img{height:44px;border-radius:6px;border:1px solid #272b38;display:block}
.thumb span{position:absolute;top:-6px;right:-6px;background:#8b2c2c;color:#fff;
  border-radius:50%;width:17px;height:17px;font-size:11px;line-height:17px;
  text-align:center;cursor:pointer}
@media(max-width:860px){.rail{display:none}#chart{height:170px}}
</style>

<div class=top>
  <h1>signal_copy</h1>
  <span id=bar>загружаю…</span>
</div>

<div class=mid>
  <div class=feed>
    <div id=log></div>
    <div class=compose>
      <div id=att></div>
      <textarea id=ci placeholder="Вставь сигнал из канала или просто спроси. Enter — отправить, Shift+Enter — новая строка, Cmd+V — картинка"></textarea>
      <div class=row>
        <button onclick=send()>Отправить</button>
        <button class="ghost mini" onclick="document.getElementById('f').click()">Картинка</button>
        <input type=file id=f accept="image/*" multiple style="display:none" onchange=pickFiles(event)>
        <button class="ghost mini" onclick=testSignal()>Тестовый сигнал</button>
        <button class="ghost mini" onclick=clearChat()>Очистить ленту</button>
        <label style="font-size:12px;color:#6e7681;margin-left:auto">
          <input type=checkbox id=llm checked> ИИ при непонятном</label>
      </div>
    </div>
  </div>

  <div class=rail>
    <h3>Открытые позиции</h3><div id=pos></div>
    <h3>Разобранные сигналы</h3><div id=sigs></div>
  </div>
</div>

<div class=bottom>
  <div class=chartbar>
    <select id=cs onchange=drawChart()></select>
    <select id=cp onchange=drawChart()>
      <option>M5</option><option>M15</option><option>M30</option>
      <option selected>H1</option><option>H4</option><option>D1</option>
    </select>
    <button class="ghost mini" onclick=drawChart()>Обновить</button>
    <span id=cinfo style="color:#6e7681;font-size:12px"></span>
  </div>
  <div id=chart></div>
</div>

<script>
const $=s=>document.querySelector(s), log=$('#log'), ci=$('#ci');
const n=(v,d=5)=>v==null?'—':(+v).toFixed(d).replace(/\.?0+$/,'');
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const dgOf=s=>String(s||'').startsWith('XAU')?2:5;
let PICS=[], SEL=null;

function scroll(){log.scrollTop=log.scrollHeight}

/* ───────── шапка ───────── */
async function boot(){
  const r=await (await fetch('/api/status')).json();
  if(!r.ok){$('#bar').innerHTML='<span class="dot off"></span>нет связи с MetaTrader 5: '+
    esc(r.error)+' — запусти терминал';return}
  const a=r.account,tm=r.terminal,c=r.config;
  $('#bar').innerHTML=
    `<span><span class="dot ${tm.server_connected?'on':'off'}"></span><b>${a.login}</b> ${a.server}</span>`+
    `<span>${a.type!=='demo'?'⚠ РЕАЛ':'демо'}</span>`+
    `<span><b>${(+a.equity).toFixed(2)} ${a.currency}</b></span>`+
    `<span>позиций <b>${r.positions.length}/${c.max_positions}</b></span>`+
    `<span>риск <b>${c.risk_pct}%</b></span><span>цель <b>TP${c.tp}</b></span>`;
  const sel=$('#cs');
  if(!sel.options.length&&r.symbols){
    r.symbols.forEach(s=>{const o=document.createElement('option');o.textContent=s;sel.appendChild(o)});
    drawChart();
  }
}
boot();setInterval(boot,15000);

/* ───────── лента ───────── */
function bubble(role,text,imgs){
  const d=document.createElement('div');
  d.className='b '+(role==='user'?'me':'ai');
  d.innerHTML=esc(text)+(imgs||[]).map(s=>`<img src="data:image/png;base64,${s}">`).join('');
  log.appendChild(d);scroll();return d;
}
function pushCard(html){
  const d=document.createElement('div');d.innerHTML=html;
  log.appendChild(d);scroll();return d;
}
(async()=>{const r=await (await fetch('/api/chat/history')).json();
  (r.history||[]).forEach(h=>bubble(h.role,h.content));})();

ci.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
ci.addEventListener('paste',e=>{for(const it of (e.clipboardData||{}).items||[])
  if(it.type.startsWith('image/'))addFile(it.getAsFile())});
function pickFiles(e){[...e.target.files].forEach(addFile);e.target.value=''}
function addFile(f){if(!f)return;const r=new FileReader();
  r.onload=()=>{PICS.push(r.result.split(',')[1]);drawAtt()};r.readAsDataURL(f)}
function drawAtt(){$('#att').innerHTML=PICS.map((s,i)=>
  `<span class=thumb><img src="data:image/png;base64,${s}"><span onclick="PICS.splice(${i},1);drawAtt()">×</span></span>`).join('')}

async function send(){
  const msg=ci.value.trim(); if(!msg&&!PICS.length)return;
  bubble('user',msg,PICS);
  const imgs=PICS.slice(); PICS=[]; drawAtt(); ci.value='';
  const wait=bubble('assistant','…');
  const r=await (await fetch('/api/input',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:msg,images:imgs,use_llm:$('#llm').checked})})).json();
  if(r.mode==='signal'){
    wait.remove();
    if(!r.ok){pushCard(`<div class="card no"><div class=t>Ошибка</div>${esc(r.error)}</div>`);return}
    r.cards.forEach(c=>pushCard(render(c)));
    loadRail();
  }else{
    if(!r.ok){wait.innerHTML='<span style="color:#ff8b8b">'+esc(r.error)+'</span>';return}
    wait.innerHTML=esc(r.reply)+`<div class=eng>${esc(r.engine||'')}</div>`;
    if(r.action&&r.action.ticket){const a=r.action;
      wait.insertAdjacentHTML('beforeend',
        `<div class=row><button class="${a.action==='close'?'red':'ghost'} mini"
          onclick="chatAct('${a.action}',${a.ticket},'${a.symbol}',this)">${
          a.action==='close'?'Закрыть '+a.symbol:'Стоп в безубыток'}</button></div>`)}
  }
  scroll();boot();loadRail();
}

function render(c){
  const cls=c.kind!=='SIGNAL'?'info':(c.can_execute?'ok':'no'), dg=dgOf(c.symbol);
  let h=`<div class="card ${cls}"><div class=t>${esc(c.title||c.kind)}</div>`;
  if(c.kind==='SIGNAL'){
    h+=`<table>
      <tr><td>зона канала</td><td class=v>${n(c.entry_min,dg)} — ${n(c.entry_max,dg)}</td>
          <td>войдём по</td><td class=v><b>${n(c.entry_used,dg)}</b></td></tr>
      <tr><td>стоп</td><td class=v>${n(c.stop_loss,dg)}</td>
          <td>цель</td><td class=v>${n(c.chosen_tp,dg)}</td></tr>
      <tr><td>рынок</td><td class=v>${n(c.market_bid,dg)} / ${n(c.market_ask,dg)}</td>
          <td>спред</td><td class=v>${c.spread_points??'—'} п.</td></tr>
      <tr><td><b>ЛОТ</b></td><td class=v><b style="color:#fff">${c.lot??'—'}</b></td>
          <td>риск</td><td class=v>${c.risk_cash!=null?(+c.risk_cash).toFixed(2)+' '+c.currency:'—'}
          ${c.risk_pct!=null?'('+(+c.risk_pct).toFixed(2)+'%)':''}</td></tr>
      <tr><td>осталось взять</td><td class=v>${c.rr!=null?c.rr+'R':'—'}
        ${c.rr>0?'<span style="color:#6e7681">нужен винрейт '+(100/(1+c.rr)).toFixed(0)+'%</span>':''}</td>
          <td>уход от зоны</td><td class=v>${c.drift_r!=null?c.drift_r+'R':'—'}</td></tr>
      <tr><td>все цели</td><td class=v colspan=3>${(c.take_profits||[]).map(x=>n(x,dg)).join(' · ')||'—'}</td></tr>
    </table>`;
  }
  (c.blockers||[]).forEach(b=>h+=`<div class="msg err">⛔ ${esc(b)}</div>`);
  (c.warnings||[]).forEach(w=>h+=`<div class="msg warn">⚠ ${esc(w)}</div>`);
  if(c.can_execute&&c.token)
    h+=`<div class=row><button class=go onclick="go('${c.token}',this)">ОТКРЫТЬ ${c.symbol} ${c.side} ${c.lot}</button>
        <button class="ghost mini" onclick="this.closest('.card').style.opacity=.4;this.disabled=true">Пропустить</button></div>`;
  if(c.symbol)h+=`<div class=row><button class="ghost mini" onclick="showOn('${c.symbol}',${c.entry_used||0},${c.stop_loss||0},${c.chosen_tp||0})">Показать на графике</button></div>`;
  return h+`<div class=eng>${esc(c.engine)}${c.group_id?' · сделка #'+c.group_id:''}</div></div>`;
}

async function go(token,btn){
  btn.disabled=true;btn.textContent='отправляю…';
  const r=await (await fetch('/api/execute',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token})})).json();
  const box=btn.closest('.card');
  box.insertAdjacentHTML('beforeend', r.ok?`<div class="msg good">✅ Открыто. Тикет ${r.ticket}</div>`
    :`<div class="msg err">⛔ ${esc(r.error||'не открылось')}</div>`);
  btn.textContent=r.ok?'Открыто':'Не удалось';
  if(!r.ok&&r.response)box.insertAdjacentHTML('beforeend','<pre>'+esc(JSON.stringify(r.response,null,1))+'</pre>');
  scroll();boot();loadRail();
}
async function chatAct(action,ticket,symbol,btn){
  btn.disabled=true;
  const r=await (await fetch(action==='close'?'/api/close':'/api/breakeven',
    {method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({ticket,symbol})})).json();
  btn.insertAdjacentHTML('afterend', r.ok?'<div class="msg good">✅ выполнено</div>'
    :'<div class="msg err">⛔ '+esc(r.error)+'</div>');
  loadRail();boot();
}
async function clearChat(){await fetch('/api/chat/clear',{method:'POST'});log.innerHTML=''}

async function testSignal(){
  const sym=$('#cs').value||'EURUSD';
  const r=await (await fetch(`/api/testsignal?symbol=${sym}&side=BUY`)).json();
  if(!r.ok){bubble('assistant','не смог собрать: '+r.error);return}
  ci.value=r.text;ci.focus();
}

/* ───────── правая полка ───────── */
async function loadRail(){
  const [p,t]=await Promise.all([
    (await fetch('/api/positions')).json(),
    (await fetch('/api/trades')).json()]);
  const pb=$('#pos');
  if(!p.ok){pb.innerHTML='<div class=sub style="color:#6e7681">нет связи</div>'}
  else if(!p.positions.length){pb.innerHTML='<div class=sub style="color:#6e7681">пусто</div>'}
  else pb.innerHTML=p.positions.map(x=>{
    const dg=dgOf(x.symbol),buy=String(x.type).includes('b'),pl=+x.profit||0;
    return `<div class="pin ${pl>=0?'win':'lose'}" onclick="showOn('${x.symbol}',${x.price_open},${x.sl||0},${x.tp||0})">
      <b>${x.symbol} ${buy?'BUY':'SELL'} ${x.volume}</b>
      <span style="float:right;color:${pl>0?'#3fb950':(pl<0?'#f85149':'#9aa3b2')}">${pl>0?'+':''}${pl.toFixed(2)}</span>
      <div class=sub>вход ${n(x.price_open,dg)} · стоп ${x.sl?n(x.sl,dg):'НЕТ'} · цель ${x.tp?n(x.tp,dg):'—'}</div>
      <div class=row style="margin:6px 0 0">
        <button class="ghost mini" onclick="event.stopPropagation();be(${x.ticket},'${x.symbol}',this)">Безубыток</button>
        <button class="red mini" onclick="event.stopPropagation();closePos(${x.ticket},'${x.symbol}',this)">Закрыть</button>
      </div></div>`}).join('');

  const sb=$('#sigs'), tr=(t.trades||[]).slice(0,15);
  sb.innerHTML=tr.length?tr.map(g=>{
    const dg=dgOf(g.symbol);
    return `<div class="pin" onclick="showOn('${g.symbol}',${g.entry_max||g.entry_min||0},${g.stop_loss||0},${g.chosen_tp||0})">
      <b>#${g.id} ${g.symbol} ${g.side}</b> <span class=sub>${g.status}</span>
      <div class=sub>стоп ${n(g.stop_loss,dg)} · цель ${n(g.chosen_tp,dg)}</div></div>`}).join('')
    : '<div class=sub style="color:#6e7681">пока ничего</div>';
}
loadRail();setInterval(loadRail,5000);

async function be(ticket,symbol,btn){
  btn.disabled=true;
  const r=await (await fetch('/api/breakeven',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ticket,symbol})})).json();
  bubble('assistant', r.ok?`✅ ${symbol}: стоп перенесён в ${r.new_sl}`:`⛔ ${symbol}: ${r.error}`);
  loadRail();
}
async function closePos(ticket,symbol,btn){
  btn.disabled=true;btn.textContent='…';
  const r=await (await fetch('/api/close',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ticket,symbol})})).json();
  bubble('assistant', r.ok?`✅ ${symbol}: позиция закрыта`:`⛔ ${symbol}: ${r.error}`);
  loadRail();boot();
}

/* ───────── график ───────── */
let chartObj=null,series=null,lines=[];
function showOn(symbol,entry,sl,tp){
  const sel=$('#cs');
  if(![...sel.options].some(o=>o.value===symbol||o.textContent===symbol)){
    const o=document.createElement('option');o.textContent=symbol;sel.appendChild(o)}
  sel.value=symbol;SEL={entry,sl,tp};
  document.querySelectorAll('.pin').forEach(x=>x.classList.remove('sel'));
  drawChart();
}
async function drawChart(){
  const symbol=$('#cs').value||'EURUSD', period=$('#cp').value;
  $('#cinfo').textContent='загружаю…';
  const r=await (await fetch(`/api/chart?symbol=${symbol}&period=${period}&bars=300`)).json();
  if(!r.ok||!(r.candles||[]).length){
    $('#cinfo').textContent='нет данных'+(r.error?': '+r.error:'');return}
  if(!chartObj){
    chartObj=LightweightCharts.createChart($('#chart'),{
      layout:{background:{color:'#0d0f14'},textColor:'#9aa3b2'},
      grid:{vertLines:{color:'#181c25'},horzLines:{color:'#181c25'}},
      timeScale:{timeVisible:true,borderColor:'#272b38'},
      rightPriceScale:{borderColor:'#272b38'},autoSize:true});
    series=chartObj.addCandlestickSeries({upColor:'#3fb950',downColor:'#f85149',
      borderVisible:false,wickUpColor:'#3fb950',wickDownColor:'#f85149'});
    new ResizeObserver(()=>chartObj&&chartObj.timeScale().fitContent()).observe($('#chart'));
  }
  series.setData(r.candles);
  lines.forEach(l=>{try{series.removePriceLine(l)}catch(e){}});lines=[];
  if(SEL){
    const add=(price,color,title)=>{if(price&&+price>0)
      lines.push(series.createPriceLine({price:+price,color,lineWidth:1,
        lineStyle:2,axisLabelVisible:true,title}))};
    add(SEL.entry,'#2f6feb','вход');add(SEL.sl,'#f85149','стоп');add(SEL.tp,'#3fb950','цель');
  }
  chartObj.timeScale().fitContent();
  $('#cinfo').textContent=`${symbol} ${period} · ${r.candles.length} свечей`;
}
</script></html>"""


@app.middleware("http")
async def _never_500(request, call_next):
    """Любой необработанный сбой возвращаем как JSON, а не как пустой 500."""
    try:
        return await call_next(request)
    except Exception as e:
        tb = traceback.format_exc()
        print("\n=== НЕОБРАБОТАННЫЙ СБОЙ ===\n" + tb, flush=True)
        return JSONResponse({"ok": False,
                             "error": f"{type(e).__name__}: {e}",
                             "traceback": tb.splitlines()[-6:]}, status_code=200)


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


if __name__ == "__main__":
    print(f"База:      {store.DB_PATH}")
    print(f"Терминал:  {config.MT5_URL}")
    print("Открой:    http://127.0.0.1:8766\n")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="warning")
