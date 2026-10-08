"""Offline intake arithmetic; never changes the assessor, sources or money policy."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = Path('.private/kity_oct8_source_inventory')


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def payload(capture):
    assert capture['method'] == 'GET' and capture['http_status'] == 200 and capture['ok'] is True
    assert capture['request_ms'] <= capture['receive_ms']
    assert hashlib.sha256(capture['raw'].encode()).hexdigest() == capture['sha256']
    return json.loads(capture['raw'])


def main():
    account = load(ROOT/'binance_account_raw_archive.json')
    assert account['api_requests'] == 24
    assert account['orders_allowed'] is False and account['order_calls'] == account['remote_writes'] == 0
    for capture in account['clock_captures']:
        assert capture['http_status'] == 200 and capture['ok'] is True
        assert hashlib.sha256(capture['raw'].encode()).hexdigest() == capture['sha256']
    captures = {(c['endpoint'], c['params'].get('symbol')): c for c in account['captures']}
    assert len(captures) == len(account['captures']) == 22
    bodies = {identity: payload(c) for identity, c in captures.items()}
    permissions = bodies[('/sapi/v1/account/apiRestrictions', None)]
    config = bodies[('/fapi/v1/accountConfig', None)]
    acct = bodies[('/fapi/v3/account', None)]
    assets = {row['asset']: row for row in acct['assets']}
    assert len(assets) == len(acct['assets'])
    assert permissions['enableFutures'] is False and permissions['enableReading'] is True
    assert config['multiAssetsMargin'] is True and config['dualSidePosition'] is True
    assert assets['USDT']['walletBalance'] == assets['USDT']['availableBalance'] == '0.00000000'
    assert assets['BNFCR']['walletBalance'] == acct['availableBalance'] == '11.70137565'
    assert bodies[('/fapi/v3/positionRisk', None)] == []
    assert bodies[('/fapi/v1/openOrders', None)] == []
    assert bodies[('/fapi/v1/openAlgoOrders', None)] == []
    diag = load(PUBLIC/'actual_analysis.json')
    wire = load(PUBLIC/'closed_and_venue_archive.json')
    assert all(hashlib.sha256(value.encode()).hexdigest() == wire['sha256'][name]
               for name, value in wire['files'].items())

    def public(name):
        capture = json.loads(wire['files']['venue-evidence/'+name])
        assert capture['venue'] == 'BINANCE'
        assert hashlib.sha256(capture['raw'].encode()).hexdigest() == capture['sha256']
        return capture, json.loads(capture['raw'])

    fi_capture, fi_rows = public('binance-funding-info.json')
    fi = {row['symbol']: row for row in fi_rows}
    assert len(fi) == len(fi_rows)
    legs = []
    gross = Decimal(0)
    roundtrip_fee = Decimal(0)
    current_cap_scenario = Decimal(0)
    target = Decimal(diag['binance_diagnostic_equal_notional_target_usdt'])
    for proposed in diag['diagnostic_quantities']:
        symbol, side = proposed['symbol'], proposed['side']
        q = Decimal(proposed['quantity']); notional = Decimal(proposed['notional_usdt'])
        assert proposed['not_admitted_quantity'] is True
        fee = bodies[('/fapi/v1/commissionRate', symbol)]
        cfg = bodies[('/fapi/v1/symbolConfig', symbol)]
        assert len(cfg) == 1 and cfg[0]['symbol'] == fee['symbol'] == symbol
        assert cfg[0]['marginType'] == 'CROSSED' and cfg[0]['leverage'] == 2
        assert cfg[0]['isAutoAddMargin'] is False
        assert fee['makerCommissionRate'] == '0.000200' and fee['takerCommissionRate'] == '0.000500'
        cap = Decimal(fi[symbol]['adjustedFundingRateCap'])
        floor = Decimal(fi[symbol]['adjustedFundingRateFloor'])
        interval = fi[symbol]['fundingIntervalHours']
        assert type(interval) is int and interval > 0 and cap > 0 and floor < 0
        count = (7*24 + interval-1)//interval
        adverse = cap if side == 'LONG' else -floor
        cap_scenario = notional*adverse*count
        hc, history = public('binance-funding-'+symbol+'.json')
        times = [row['fundingTime'] for row in history]
        assert len(times) == len(set(times)) and times == sorted(times)
        assert all(type(t) is int and t <= hc['receive_ms'] for t in times)
        cash_debits = []
        for row in history:
            assert row['symbol'] == symbol
            rate, mark = Decimal(row['fundingRate']), Decimal(row['markPrice'])
            assert rate.is_finite() and mark.is_finite() and mark > 0
            cash_debits.append(q*mark*rate*(1 if side == 'LONG' else -1))
        windows=[]
        for end in times:
            start=end-7*86400000
            if start < times[0]: continue
            debits=[d for t,d in zip(times,cash_debits) if start < t <= end]
            windows.append((end, max(Decimal(0),sum(debits,Decimal(0))),
                            sum((max(Decimal(0),d) for d in debits),Decimal(0))))
        assert windows
        worst_net=max(windows,key=lambda w:w[1]); worst_gross=max(windows,key=lambda w:w[2])
        gross+=notional; roundtrip_fee+=notional*Decimal(fee['takerCommissionRate'])*2
        current_cap_scenario+=cap_scenario
        legs.append({'symbol':symbol,'side':side,'diagnostic_quantity':str(q),
            'not_admitted_quantity':True,'morning_entry_notional':str(notional),
            'entry_target_residual_fraction':str((target-notional)/target),
            'account_symbol_config':cfg[0],'actual_commission_rates':fee,
            'current_funding_info':fi[symbol],
            'funding_info_raw_sha256':fi_capture['sha256'],'funding_history_raw_sha256':hc['sha256'],
            'funding_history_points':len(times),'first_funding_ms':times[0],'last_funding_ms':times[-1],
            'observed_max_timestamp_gap_ms':max(b-a for a,b in zip(times,times[1:])),
            'observed_series_7d_windows':len(windows),
            'observed_series_completeness_certified':False,
            'observed_max_7d_net_debit_quote':str(worst_net[1]),'max_net_window_end_ms':worst_net[0],
            'observed_max_7d_gross_debit_quote':str(worst_gross[2]),'max_gross_window_end_ms':worst_gross[0],
            'current_cap_7d_constant_notional_scenario_quote':str(cap_scenario),
            'settlements_current_interval_scenario':count,'future_reserve_bound':False})
    assert gross == Decimal(diag['binance_diagnostic_gross_usdt']) == Decimal('43.73889000')
    asset_fields=('asset','walletBalance','marginBalance','availableBalance','initialMargin','maintMargin','updateTime')
    out={'schema':'KITY_SOURCE_AND_BINANCE_DOSSIER_V1','terminal':'BLOCKED_DATA',
        'binance_current_key_status':'BLOCKED_EXECUTION','bybit_exact_basket_status':'BLOCKED_EXECUTION',
        'orders_allowed':False,'money_ready':False,'research_immutable':True,
        'base_commit':'8e05160b70da596a3cde1f0efdfb445a3a3c4ced',
        'source_contract_status':'DEFINED_REVIEWED_NOT_IMPLEMENTED_NO_ACCEPTED_SEAL',
        'publication_size_lower_bound':load(ROOT/'publication_size_lower_bound.json'),
        'captured_account_started_ms':account['started_ms'],'captured_account_completed_ms':account['completed_ms'],
        'account_get_count':24,'account_fields':{
            'key_permissions':permissions,'account_config':config,
            'aggregate_available':acct['availableBalance'],'aggregate_available_unit':'MULTI_ASSETS_USD_REPRESENTATION',
            'wallet_credit':{k:assets['BNFCR'].get(k) for k in asset_fields},
            'usdt_asset':{k:assets['USDT'].get(k) for k in asset_fields},
            'observed_positions':0,'observed_normal_open_orders':0,'observed_algo_open_orders':0,
            'exclusive_ownership_proven':False,'finality_proven':False},
        'legs':legs,'diagnostic_sizing':{
            'public_book_is_current_for_dispatch':False,'gross_quote':str(gross),
            'equal_reference_quote':str(target),'max_target_residual_fraction':max(leg['entry_target_residual_fraction'] for leg in legs),
            'illustrative_initial_margin_at_captured_2x':str(gross/2),
            'actual_margin_credit_contract_verified':False,
            'taker_roundtrip_constant_notional_fee_quote':str(roundtrip_fee),
            'taker_roundtrip_constant_notional_fee_bps':'10',
            'sum_current_cap_7d_constant_notional_scenarios_quote':str(current_cap_scenario),
            'current_cap_scenario_is_approved_policy':False,'future_notional_interval_bound':False,
            'historical_12bps_research_benchmark_changed':False},
        'remaining_gates':[
            'REVIEWED_SOURCE_COMPATIBILITY_IMPLEMENTATION',
            'STRICT_EXTERNAL_RAW_REF_PROVENANCE_AND_FULL_PUBLICATION_SIZE',
            'CURRENT_INLINE_RECEIPT_EXCEEDS_2MIB_BY_MANDATORY_FIELD_LOWER_BOUND',
            'TIMELY_ACCEPTED_PROSPECTIVE_SIGNAL_SEAL',
            'BINANCE_CURRENT_KEY_FUTURES_TRADING_DISABLED',
            'SELECTED_ACCOUNT_BNFCR_COLLATERAL_MARGIN_FEES_LIABILITY_CONTRACT',
            'OWNER_ABSOLUTE_PER_LEG_PORTFOLIO_DAILY_CAPS_UNSET',
            'OWNER_EQUAL_WEIGHT_ROUNDING_TOLERANCE_UNSET',
            'FUNDING_NOTIONAL_INTERVAL_RESERVE_POLICY_UNSET',
            'EXCLUSIVE_OWNERSHIP_HEDGE_UNWIND_RESTART_FINALITY_ROLLBACK_NOT_VALIDATED',
            'SEPARATE_OWNER_MONEY_GO_ABSENT'],
        'capture_summary':[{
            'base':c['base'],'endpoint':c['endpoint'],'method':c['method'],'params':c['params'],
            'request_ms':c['request_ms'],'receive_ms':c['receive_ms'],'http_status':c['http_status'],
            'raw_sha256':c['sha256']} for c in account['captures']],
        'source_manifest':{str(p):sha(p) for p in [ROOT/'binance_account_raw_archive.json',
            ROOT/'binance_account_get_only.py',ROOT/'publication_size_lower_bound.json',
            ROOT/'publication_lower_bound.py',
            ROOT/'build_dossier.py',PUBLIC/'actual_complete_capture_bundle.json',
            PUBLIC/'actual_analysis.json',PUBLIC/'closed_and_venue_archive.json',
            Path('bot/kity_m3_orders_off.py'),Path('scripts/kity_m3_orders_off.py'),
            Path('reports/KITY_SOURCE_CONTRACT_AND_BINANCE_DOSSIER_2026_10_08.md')]},
        'authority':{'orders':0,'remote_writes':0,'product_code_changes':0,'research_judge_runs':0,
            'claude_messages':0,'alpaca_queries':0,'live_or_probe_restarts':0,
            'native_heartbeat_changes':0,'accepted_signal_published':False},
        'limitations':['historical funding diagnostics are conditional on retained series, not completeness-certified or a future bound',
            'constant proposed quantity/settlement mark quote cash is not actual BNFCR account cashflow',
            'current cap*count scenario assumes fixed future notional and intervals; not an adopted money policy',
            'sum per-leg worst windows is not asserted to be one coincident basket window',
            'captured account canTrade is not key Futures scope; key scope is explicitly false']}
    # Compare Decimal values numerically, not their string encodings.
    out['diagnostic_sizing']['max_target_residual_fraction']=str(max(Decimal(leg['entry_target_residual_fraction']) for leg in legs))
    Path('reports/KITY_SOURCE_CONTRACT_AND_BINANCE_DOSSIER_2026_10_08.json').write_text(
        json.dumps(out,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'terminal':out['terminal'],'initial_margin_diagnostic':str(gross/2),
        'roundtrip_fee_diagnostic':str(roundtrip_fee),'funding_cap_scenario':str(current_cap_scenario),
        'source_hash_checks':'PASS','observed_funding_windows_total':sum(l['observed_series_7d_windows'] for l in legs)},sort_keys=True))


if __name__=='__main__':main()
