from __future__ import annotations

import json
import sqlite3
import asyncio
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from bot import deepseek_usage as usage
from bot.deepseek_overlay import DeepSeekOverlay, DeepSeekBudgetError
from web.routes import ai_routes


@pytest.fixture(autouse=True)
def isolated_budget(monkeypatch, tmp_path):
    monkeypatch.setenv('DEEPSEEK_ATTEMPT_LEDGER_PATH', str(tmp_path/'attempts.sqlite3'))
    monkeypatch.setenv('DEEPSEEK_AUDIT_LOG_PATH', str(tmp_path/'audit.jsonl'))
    monkeypatch.setenv('DEEPSEEK_USAGE_LOG_PATH', str(tmp_path/'usage.jsonl'))
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP', '0.003')


def reserve(**kwargs):
    return usage.reserve_deepseek_attempt(source='cash_test', model=usage.CURRENT_DEEPSEEK_MODEL,
        max_tokens=400, prompt_chars=0, daily_cap=100, **kwargs)


def test_cash_reservation_blocks_second_call_even_when_daily_slots_remain():
    # Missing the monthly check would admit both, despite their combined ceiling >$0.003.
    assert reserve() is not None
    assert reserve() is None
    rows=usage.read_deepseek_attempts()
    assert len(rows)==1
    assert rows[0]['charge_usd_micros']==2938


def test_concurrent_cash_reservations_do_not_overspend(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','0.01')
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(lambda _: reserve(),range(24)))
    assert len([r for r in results if r is not None])==3
    assert sum(r['charge_usd_micros'] for r in usage.read_deepseek_attempts())==8814


def test_timeout_keeps_the_full_reservation_across_restart():
    r=reserve(); assert r is not None
    assert usage.finalize_deepseek_attempt(r,latency_ms=1,status='error',error_type='Timeout')
    assert reserve() is None
    assert usage.read_deepseek_attempts()[0]['charge_usd_micros']==2938


def test_verified_usage_releases_only_unused_ceiling():
    r=reserve(); assert r is not None
    assert usage.finalize_deepseek_attempt(r,latency_ms=1,status='ok',response_payload={
        'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}})
    assert usage.read_deepseek_attempts()[0]['charge_usd_micros']==54
    assert reserve() is not None


@pytest.mark.parametrize('payload',[{}, {'usage':{'prompt_tokens':100}},
    {'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':1}}])
def test_missing_or_inconsistent_billing_never_releases_money(payload):
    r=reserve(); assert r is not None
    assert usage.finalize_deepseek_attempt(r,latency_ms=1,status='ok',response_payload=payload)
    assert reserve() is None


def test_budget_breach_stops_following_calls(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    r=reserve(); assert r is not None
    assert usage.finalize_deepseek_attempt(r,latency_ms=1,status='ok',response_payload={
        'usage':{'prompt_tokens':100000,'completion_tokens':10000,'total_tokens':110000}})
    assert reserve() is None
    assert usage.read_deepseek_attempts()[0]['status']=='billing_contract_breach'


def test_process_cannot_raise_committed_shared_monthly_cap(monkeypatch):
    assert reserve() is not None
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    assert reserve() is None


@pytest.mark.parametrize('cap',['0','-1','NaN','Infinity','bogus'])
def test_invalid_cash_policy_denies_before_http(monkeypatch,cap):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP',cap)
    assert reserve() is None


def test_unknown_model_and_expired_price_policy_deny():
    assert usage.reserve_deepseek_attempt(source='test',model='deepseek-v4-pro',max_tokens=400,
        prompt_chars=0,daily_cap=100) is None
    expired=int(datetime(2026,12,1,tzinfo=timezone.utc).timestamp())
    assert reserve(now_ts=expired) is None


def test_old_loaded_telegram_insert_cannot_bypass_cash_guard():
    # The running old adapter still issues its original INSERT after a schema upgrade.
    r=reserve(); assert r is not None
    con=sqlite3.connect(str(r.path))
    row=usage.read_deepseek_attempts()[0]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute('''INSERT INTO provider_attempts
            (ts,ts_utc,day_utc,source,model,max_tokens,prompt_chars,status)
            VALUES(?,?,?,?,?,?,?,?)''',(row['ts'],row['ts_utc'],row['day_utc'],
            'legacy_adapter',usage.CURRENT_DEEPSEEK_MODEL,400,0,'reserved'))
    con.close()
    assert len(usage.read_deepseek_attempts())==1


def test_telegram_and_web_share_budget_and_web_denies_before_transport(monkeypatch):
    overlay=DeepSeekOverlay(); overlay.cfg.api_key='test-key'; overlay.cfg.completion_max_tokens=400
    class Response:
        status_code=200
        def json(self): return {'choices':[{'message':{'content':'answer'},'finish_reason':'stop'}]}
    monkeypatch.setattr('bot.deepseek_overlay.requests.post',lambda *a,**k:Response())
    assert overlay._request_chat_completion([{'role':'user','content':'x'}])[0]=='answer'
    def forbidden(*args,**kwargs): raise AssertionError('UNEXPECTED_PROVIDER_REQUEST')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    with pytest.raises(RuntimeError,match='budget'):
        ai_routes._deepseek_chat_completion(api_key='test-key',model=usage.CURRENT_DEEPSEEK_MODEL,
            messages=[{'role':'user','content':'x'}],max_tokens=400,temperature=.2,
            timeout_sec=2,source='web_chat')
    assert len(usage.read_deepseek_attempts())==1


def test_budget_status_reports_conservative_remaining():
    assert reserve() is not None
    status=usage.deepseek_cash_budget_status()
    assert status['cap_usd_micros']==3000
    assert status['charged_usd_micros']==2938
    assert status['remaining_usd_micros']==62


def test_legacy_finalize_update_disables_future_calls(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    r=reserve(); assert r is not None
    con=sqlite3.connect(str(r.path))
    con.execute("UPDATE provider_attempts SET status='ok',prompt_tokens=100000,completion_tokens=10000,total_tokens=110000 WHERE id=?",(r.attempt_id,))
    con.commit();con.close()
    assert usage.read_deepseek_attempts()[0]['status']=='billing_contract_breach'
    assert reserve() is None


def test_zero_cap_is_durable_for_legacy_loaded_insert(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    r=reserve(); assert r is not None
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','0')
    assert reserve() is None
    con=sqlite3.connect(str(r.path))
    row=usage.read_deepseek_attempts()[0]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute('''INSERT INTO provider_attempts
            (ts,ts_utc,day_utc,source,model,max_tokens,prompt_chars,status)
            VALUES(?,?,?,?,?,?,?,?)''',(row['ts'],row['ts_utc'],row['day_utc'],
            'legacy_adapter',usage.CURRENT_DEEPSEEK_MODEL,400,0,'reserved'))
    con.close()


def test_status_installs_lower_cap_even_without_paid_attempt(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    assert reserve() is not None
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','0.003')
    assert usage.deepseek_cash_budget_status()['cap_usd_micros']==3000
    monkeypatch.setenv('DEEPSEEK_MONTHLY_USD_CAP','1')
    assert reserve() is None


def test_web_chat_never_falls_back_to_unbudgeted_anthropic(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','')
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-only')
    monkeypatch.setattr(ai_routes,'_web_live_truth_gate',lambda:(True,[]))
    monkeypatch.setattr(ai_routes,'_check_rate',lambda _:None)
    monkeypatch.setattr(ai_routes,'_build_context',lambda:'fresh source')
    def forbidden(**kwargs): raise AssertionError('UNBUDGETED_PAID_PROVIDER')
    monkeypatch.setitem(sys.modules,'anthropic',types.SimpleNamespace(Anthropic=forbidden))
    result=asyncio.run(ai_routes.chat(ai_routes.ChatRequest(messages=[ai_routes.ChatMessage(role='user',content='hello')]),email='test@example.com'))
    assert 'DeepSeek' in result.reply
    assert 'UNBUDGETED_PAID_PROVIDER' not in result.reply


@pytest.mark.parametrize('deepseek_key', ['', 'test-only'])
def test_setup_analysis_never_uses_unbudgeted_provider(monkeypatch, deepseek_key):
    monkeypatch.setenv('DEEPSEEK_API_KEY', deepseek_key)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-only')
    monkeypatch.setenv('WEB_SETUP_AI_PROVIDER', 'anthropic')
    monkeypatch.setattr(ai_routes, '_web_live_truth_gate', lambda: (True, []))
    monkeypatch.setattr(ai_routes, '_setup_cache_get', lambda _: None)
    calls = []
    def forbidden(**kwargs):
        calls.append('anthropic')
        raise AssertionError('UNBUDGETED_PAID_PROVIDER')
    def budgeted(**kwargs):
        calls.append('deepseek')
        return ('{"verdict":"skip","reasoning":"Нет доказательства","risk_note":"Не входить"}', usage.CURRENT_DEEPSEEK_MODEL)
    monkeypatch.setitem(sys.modules, 'anthropic', types.SimpleNamespace(Anthropic=forbidden))
    monkeypatch.setattr(ai_routes, '_deepseek_chat_completion', budgeted)
    result = asyncio.run(ai_routes.analyze_setup(ai_routes.SetupAnalysisRequest(
        symbol='BTCUSDT', side='long', setup_type='test', strategy='test'), _='test@example.com'))
    assert calls == (['deepseek'] if deepseek_key else [])
    assert 'UNBUDGETED_PAID_PROVIDER' not in result.reasoning
