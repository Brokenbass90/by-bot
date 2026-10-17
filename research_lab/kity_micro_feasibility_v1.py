"""Transport-free pre-money capacity proof using unchanged quantity/depth math."""
from decimal import Decimal as D,ROUND_FLOOR
from pathlib import Path
import hashlib,json
from bot.kity_m3_orders_off import _levels,_vwap
from research_lab.kity_micro_preflight_v1 import build_preflight
from research_lab.kity_execution_micro_v1 import first_target_within_rounding,sizing_floor,basket_geometry
from research_lab.kity_execution_micro_runtime_v1 import BASKET,_owner_bounds


def future_owner_proposal(feasibility):
    """An inert next-decision packet, never a policy or repeat of today's GO."""
    if (feasibility.get('schema')!='KITY_PRE_MONEY_FEASIBILITY_V1'
        or feasibility.get('cap_usdt')!='215' or feasibility.get('orders_allowed') is not False
        or feasibility.get('money_authority') is not False
        or feasibility.get('status') not in {'CAPACITY_BLOCKED','CAPACITY_FITS_SAVED_CAPTURE'}):raise ValueError('CAPACITY_EVIDENCE_REQUIRED')
    try:
        gross=D(feasibility['minimum_required_reference_gross'])
        if not gross.is_finite() or gross<=0 or (gross>D('215'))!=(feasibility['status']=='CAPACITY_BLOCKED'):
            raise ValueError('CAPACITY_EVIDENCE_REQUIRED')
    except (KeyError,ArithmeticError,TypeError) as exc:raise ValueError('CAPACITY_EVIDENCE_REQUIRED') from exc
    return {'schema':'KITY_FUTURE_MICRO_OWNER_PROPOSAL_V1',
        'status':'CAPACITY_BLOCKED_NO_GO_PACKET' if feasibility['status']=='CAPACITY_BLOCKED' else 'PREPARED_AWAIT_FRESH_SOURCE_AND_OWNER',
        'capacity_evidence_sha256':hashlib.sha256(json.dumps(feasibility,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'minimum_required_reference_gross':feasibility['minimum_required_reference_gross'],
        'preserved_scope':{'gross_cap_usdt':'215','collar_bps':'50','common_cts_max_ms':2000,'entry_window_ms':60000,
                          'all_in_exit_trigger_usdt':'15','duration_ms':1800000,'attempts':1},
        'required_before_personal_execution':['NEW_EXPLICIT_OWNER_AUTHORIZATION','NEW_DATED_POLICY_AFTER_FRESH_FEASIBILITY_PASS',
            'ORIGINAL_CUSTODY_ACCOUNT_WRITER_CHECKS','ONE_POST_GO_CAPTURE_AND_UNCHANGED_FINAL_GATES'],
        'old_attempt_reusable':False,'new_policy_created':False,'owner_command':None,'orders_allowed':False,'money_authority':False}


def assess_market_geometry(rows,bounds):
    bounds=_owner_bounds(bounds)
    if D(bounds['max_gross_usdt'])!=D('215'):raise ValueError('ORIGINAL_CAP_REQUIRED')
    if [(r['symbol'],r['side']) for r in rows]!=list(BASKET):raise ValueError('EXACT_BASKET_REQUIRED')
    floor=sizing_floor(rows);target=first_target_within_rounding(rows,bounds['max_rounding_shortfall_fraction'])
    geometry=basket_geometry(rows,target);legs=[];reference=limit=band_gross=D(0)
    for row,leg in zip(rows,geometry):
        qty=D(leg['quantity']);levels=_levels(row['asks'],False) if row['side']=='Buy' else _levels(row['bids'],True)
        vwap,notional=_vwap(levels,qty);remaining=qty
        for price,available in levels:
            remaining-=min(remaining,available)
            if remaining==0:break
        if remaining:raise ValueError('INSUFFICIENT_DEPTH')
        tick=D(row['tick']);upper=(price*D('1.005')/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        reference+=notional;limit+=qty*price;band_gross+=qty*upper
        legs.append({**{k:row[k] for k in ('symbol','side','price','bid','step','minimum','min_notional','maximum','tick')},
                     'qty':leg['quantity'],'limit_price':str(price),'limit_notional':str(qty*price),'depth_notional':str(notional),
                     'rounding_shortfall_fraction':leg['rounding_shortfall_fraction']})
    needed=max(reference,limit);cap=D('215')
    return {'schema':'KITY_PRE_MONEY_FEASIBILITY_V1','status':'CAPACITY_BLOCKED' if needed>cap else 'CAPACITY_FITS_SAVED_CAPTURE',
        'quantity_rule':'MINIMUM_APPROVED_ROUNDING_FRONTIER_FROM_SINGLE_POST_GO_CAPTURE','cap_usdt':'215',
        'minimum_common_target':str(target),'venue_floor_common_target':str(floor),'minimum_required_reference_gross':str(needed),
        'reference_gross':str(reference),'planned_limit_gross':str(limit),'over_cap_usdt':str(max(D(0),needed-cap)),
        'collar_high_envelope_gross':str(band_gross),'collar_bps':'50','legs':legs,
        'capacity_fit_is_money_permission':False,'source_fresh_for_dispatch':False,'orders_allowed':False,'money_authority':False,
        'broker_requests':0,'broker_writes':0,
        'minimality_scope':'EXACT_FROZEN_COMMON_TARGET_FLOOR_QUANTITY_RULE; no arbitrary resizing/substitution',
        'proof':'first_target is earliest feasible target; quantities and executable-depth gross cannot decrease at later targets'}


def assess_saved_capture(path,expected_sha,bounds):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('CAPACITY_INPUT_PATH')
    raw=path.read_bytes()
    if len(raw)>2000000 or hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('CAPACITY_INPUT_HASH')
    dossier=build_preflight(path,expected_sha,bounds);source=json.loads(raw)['response'];caps=source['captures'];rows=[]
    for instrument in dossier['instruments']:
        symbol=instrument['symbol'];book=caps['book:'+symbol]['body']['result']
        venue=caps['instrument:'+symbol]['body']['result']['list'][0]['lotSizeFilter']
        rows.append(dict(symbol=symbol,side=instrument['side'],price=book['a'][0][0] if instrument['side']=='Buy' else book['b'][0][0],
             bid=book['b'][0][0],step=instrument['quantity_step'],minimum=instrument['minimum_quantity'],tick=instrument['tick_size'],
             min_notional=instrument['minimum_notional'],maximum=venue['maxMktOrderQty'],bids=book['b'],asks=book['a']))
    result=assess_market_geometry(rows,bounds)
    if (D(result['reference_gross'])!=D(dossier['plan']['reference_gross_usdt'])
        or D(result['planned_limit_gross'])!=D(dossier['plan']['planned_limit_gross_usdt'])):raise ValueError('CAPACITY_REPLAY_CONFLICT')
    result.update(capture_sha256=expected_sha,capture_started_ms=source['started_ms'],capture_completed_ms=source['completed_ms'],
                  original_blocked_reasons=dossier['plan']['blocked_reasons'],common_clock_at_capture=dossier['common_clock_at_capture'],same_capture_replay=True)
    return result
