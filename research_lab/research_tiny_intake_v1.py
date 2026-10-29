"""One-candidate KITY research intake, not a trading engine or promotion gate."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN


class IntakeBlocked(ValueError): pass


def need(ok, why):
    if not ok: raise IntakeBlocked(why)


def assess_kity(signal, c2, entry, *, dossier_legs, active_owner):
    try:
        need(c2['schema'] == 'KITY_C2_ACTUAL_SIGNAL_MATCH_V1' and
             c2['status'] == 'C2_PASS_MATCH_ONLY', 'accepted_c2_required')
        need(signal['d'] == c2['d'] == entry['d'], 'session_mismatch')
        longs, shorts = ([x['s'] for x in signal[key]] for key in ('long','short'))
        need(longs == c2['long'] and shorts == c2['short'], 'signal_c2_mismatch')
        n = signal['monet_s_priznakom']; k = min(5, max(3, n // 10))
        need(type(n) is int and c2['features'] == n and len(longs) == len(shorts) == k,
             'frozen_cardinality')
        sides = {s:side for side, group in [(1,longs),(-1,shorts)] for s in group}
        need(len(sides) == 2*k, 'duplicate_signal_symbol')
        legs = entry['pozicii']; seen=set(); gross=Decimal(0); checked=[]
        for leg in legs:
            symbol=leg['s']; need(symbol not in seen and symbol in sides and leg['side'] == sides[symbol],
                                  'entry_symbol_side_mismatch')
            seen.add(symbol)
            qty=Decimal(str(leg['kolichestvo'])); price=Decimal(str(leg['cena_vhoda']))
            need(qty.is_finite() and price.is_finite() and qty>0 and price>0, 'entry_qty_price')
            gross+=qty*price
            meta=signal.get('instrumenty',{}).get(symbol)
            lot=None
            if meta is not None:
                step,minimum,notional=(Decimal(str(meta[k])) for k in ('step','min_qty','min_notional'))
                need(all(x.is_finite() and x>0 for x in (step,minimum,notional)), 'instrument_metadata')
                units=qty/step
                # Only tolerate binary-float serialization dust from research.
                dust=abs(units-units.to_integral_value(rounding=ROUND_HALF_EVEN))
                lot=(qty>=minimum and qty*price>=notional and dust<=Decimal('1e-10'))
            checked.append({'symbol':symbol,'side':leg['side'],'research_qty':str(qty),
                            'research_price':str(price),'metadata_lot_check':lot,'research_lot_check':leg.get('lot_ok') is True,
                            'current_step_minimum_margin_fees_funding':'NOT_VERIFIED'})
        need(seen == set(sides), 'missing_entry_legs')
        need(type(dossier_legs) is int and dossier_legs>0, 'dossier_leg_contract')
        blockers=['ECONOMIC_INCONCLUSIVE','FRESH_ACCOUNT_MARGIN_QUOTES_COSTS_REQUIRED',
                  'WEEKLY_NATIVE_STOP_RECOVERY_AND_EXIT_ACCEPTANCE_REQUIRED','NEW_EXACT_OWNER_GO_REQUIRED']
        if dossier_legs != len(legs): blockers.insert(0,f'DOSSIER_LEG_COUNT_DRIFT_{dossier_legs}_VS_{len(legs)}')
        if active_owner != 'NONE': blockers.append(f'BYBIT_SINGLE_OWNER_CONFLICT_{active_owner}')
        if not all(x['metadata_lot_check'] is True for x in checked): blockers.append('RESEARCH_STEP_MINIMUM_NOT_PASS')
        if not all(x['research_lot_check'] for x in checked): blockers.append('RESEARCH_LOT_CHECK_NOT_PASS')
        return dict(schema='RESEARCH_TINY_KITY_INTAKE_V1',candidate='KITY_ORIGINAL_WEEKLY',
                    session=signal['d'],signal_parity='C2_PASS_MATCH_ONLY',leg_count=len(legs),legs=checked,
                    research_gross_usdt=str(gross),costs='UNKNOWN_FRESH_FEES_FUNDING_SLIPPAGE_REQUIRED',
                    economic_status='INCONCLUSIVE',blockers=blockers,ready_for_tiny=False,
                    money_authority=False,orders_allowed=False,broker_writes=0,
                    reuse=['existing KITY frozen selector and C2','Bybit native-stop/reconcile/recovery primitives',
                           'existing account-owner lock; never start a second writer'],
                    next_independent_gate='resolve published dossier cardinality and versioned weekly lifecycle contract')
    except (KeyError,TypeError,InvalidOperation,ValueError) as error:
        if isinstance(error,IntakeBlocked): raise
        raise IntakeBlocked('invalid_research_packet') from error
