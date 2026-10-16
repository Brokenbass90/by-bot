# KITY final-night runtime — October 15

**CURRENT: `STATIC_READY_ORDERS_OFF_TERMS_UNCONFIRMED`.** No new intent,
selection, money GO or order. The owner's latest instruction is explicitly
read-only/no orders while investigating the missing Trading Terms prompt.

**Subsequent direct human consent received:** "Да давай все разрешаю" answers
the specific preceding legal-consent question. Recorded against proposal
`a952b806d560e1099dc57691a51c6d5c4ce57f606e968c2c093cfec3977ae257`;
this is not monetary activation. The assistant corrected its earlier offer to
send the legal acceptance on the owner's behalf: this financial-service action
requires the owner to execute it personally. **No agreement POST has been sent.**

A standalone owner-run helper is ready, separate from every trading runtime:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824 && .venv/bin/python -m research_lab.bybit_agreement_owner_once --owner-execute
```

**The human runs this command personally. Agents must never invoke the execution
flag**, remotely, through a tool, timer, service or another agent. Default mode
prints the prepared body and performs no network/credential access. Owner mode
loads the existing0600 dedicated key, verifies frozen proposal/source/consent
hashes, sends secrets over encrypted SSH stdin only, freshly verifies master
identity/Wallet permission, and implements only the fixed agreement POST. No
order/transfer route is supported. The first durable claim is retained under
`/opt/bybot-research/bybit-agreement-owner-20261016`; HTTP response bytes/hash and
terminal receipt are retained there. Timeout or unknown response never retries.
Repeated owner execution reads existing state rather than sending again. Local
result: `.private/kity_master_agreement_20261016/owner_execution_receipt.json`.

Offline10 targetedPASS, including a signed fake venue, source/role/permission
blocks, raw tamper, unknown-send, crash-claim, and local/remote source compilation.
These are not actual API acceptance evidence. The default CLI alone was executed
by the agent; no SSH invocation of the new helper or real signing request.
Full repository suite not run, root review only. See
[owner_command_preparation_v1.json](evidence/kity_master_agreement_20261016/owner_command_preparation_v1.json).
After the owner runs it, inspect the actual receipt read-only. Until then Terms
remain unconfirmed. Keep all deployed trading source/config/units unchanged;
no new money intent or carryover of October15 approvals.

**October16 06:24:53.423UTC updated-key verification PASS:** authenticated GETs
now prove MASTER/isMaster=true/parentUid0/readOnly0 and WalletAccountTransfer,
with the intended live subaccount's parent relationship matching. Withdrawal
is absent. ContractTrade/Spot/Options/Derivatives/Earn rights are also present;
they were not exercised. The prior failed role observation remains unchanged.
See [master_credential_verification_v2.json](evidence/kity_master_agreement_20261016/master_credential_verification_v2.json).

One proposed legal request is prepared, **not authorized or sent**:
`POST https://api.bybit.com/v5/user/agreement`, body
`{"categoryV2":1,"agree":true}`, proposalSHA256
`a952b806d560e1099dc57691a51c6d5c4ce57f606e968c2c093cfec3977ae257`.
Private proposal binds credential/source/identity hashes and verified master/
subaccount IDs. The official API says the metals/stock-perp agreement applies
to the master's subaccounts once signed. Owner should personally review the
[official agreement](https://www.bybit.com/en/legal/service-specific-terms/Derivative-Contract-Terms-TradFi-Perps)
before separate explicit legal approval; the agent's text reader retrieved
only its title and does not claim legal-text review. "Готово пробуй" continues
the key GET check, not consent to sign.0agreementPOST/order/transfer/key/service
mutation/newintent. No current health/position assertion from these identity
GETs. Money approval and an appropriately scoped new session remain separate;
October15 approvals are not transferred.

**October16 05:54:26.901UTC actual new-credential check:** the owner populated
the dedicated private file. GETquery-api succeeds for both provided and active
keys. The supplied key is distinct from the live bot key, but its owner is the
same **subaccount**, `isMaster=false`, readOnly0, Wallet permissions empty.
It cannot authenticate the master-only signing operation. Full UIDs/permissions
and account relationship are retained only in the0600 private capture; sanitized
[verification receipt](evidence/kity_master_agreement_20261016/master_credential_verification_v1.json)
contains no key/secret/account IDs. No agreement POST, order, key/service change
or new intent. Agent did not replace the trading credential.

Required next owner action: switch to the parent **main/master account** before
opening API Management, create a separate Read-Write key with Wallet
`AccountTransfer` only (or documented `SubMemberTransfer` alternative), and
update the same dedicated private file. Do not change the existing trading
key/profile. Then another explicitly dated read-only verification, preserving
this failed observation, must confirm role/relationship/permissions before
presenting any legal approval request. No legal approval is pending now.
October15 final-night scope and expired monetary GOs have not been carried into
October16; no entry is authorized by supplying the key.

**Subsequent owner request / actual18:58:07UTC result:** inspect existing master
credentials before suggesting support. Two distinct supplied/configured keys
were checked using only GET `/v5/user/query-api`: the active key is a subaccount,
readOnly0, Wallet permissions empty; the other returns33004/expired, so its owner
identity is not authenticated. **No usable master key in the checked sources.**
No signing POST, key mutation, order, service change or new TTL intent. See
[master_key_readonly_audit_v1.json](evidence/kity_final_night_20261015/master_key_readonly_audit_v1.json).
The scope is the existing live env/overlays and local checkout credential files,
not all possible keychains/accounts on the owner's computer. Full UIDs and raw
private account replies are not committed. The active GET's parentUid gives the
intended master/sub relationship, not an authenticated master credential.

The owner can create a dedicated **master-account** system-generated HMAC key
on the official [API Management page](https://www.bybit.com/app/user/api-management):
Read-Write and Wallet **Account Transfer** (`AccountTransfer`) only, with VPS IP
`64.226.73.119` restricted. `SubMemberTransfer` is the documented alternative;
both are not needed. Do not enable withdrawal or trading permissions for this
separate agreement credential. Existing trading credentials/config stay intact.
Exact UI translations may differ; the required documented permission is the
API value above, to be confirmed by a subsequent GET before any action.

An empty0600 private template was prepared at
`.private/kity_master_agreement_20261015/master-signing.env`; owner can save the
two new values there, not in chat. No API key has been created by the agent.
Before any further operation: authenticate the new key read-only, verify master
identity/parent relationship and minimum permission, show the official
[agreement](https://www.bybit.com/en/legal/service-specific-terms/Derivative-Contract-Terms-TradFi-Perps)
and exact proposed body `{"categoryV2":1,"agree":true}`. The document endpoint
returned its title through the text reader; its full legal text was not inspected
or accepted here. **No separate legal approval has been received.** The user's
instruction is prepare first, then ask; it is not approval to send the POST.
Money approval remains separate. The earlier support draft below is an optional
fallback, not the current required owner action.

## Actual engineering result

The separately scoped V3 kit is installed as the sole KITY physical owner.
It combines the existing V2.1 bounded-entry path with V2.2 recovery fixes;
the old kits, spent approvals, source captures and journals remain retained.
The final-night runtime does not reopen or reset the prior experiment.

- Installation completed October 15 **18:39:23.612 UTC**.
- Unit `kity-execution-micro-owner.service`, observed PID `2209853`, restarts `0`.
- App `/opt/bybot-research/kity-micro-owner-20261015/app-v3-final-night`.
- New control/state root
  `/opt/bybot-research/kity-micro-owner-20261015/runtime/night-final-20261015`.
- Config `config-v3-final-night.json` in that new root, SHA256
  `4b67083fe925735b69eada2a038e30fc9d4aaf0bd76552e7c110ea3a074f220f`.
- Unit SHA256 `39719c687fe8e9f8e541a6bad04f9847bdd7873168ab1f220cd3f81288950541`.
- Original custody root, account lock inode `818853`, wire barriers and
  heartbeat are shared; a second lease was refused. No replacement lock.
- Independent no-notify health before/after install: `HEALTHY`, `ORDERS_OFF`,
  no active plan, error `null`. Empty successful error lists normalize to
  `null`; real nonempty errors remain visible. Actual terminal/cost/flat
  proof is required before an authorized lifecycle reports ORDERS_OFF.
- Flat/open-order checks before, while quiescent and after install were zero.
  Historical POST barriers remain **3**; this upgrade added **0**.
- All 16 deployed file pins are recorded in
  [static_and_eligibility_receipt_v3.json](evidence/kity_final_night_20261015/static_and_eligibility_receipt_v3.json).

The prior f040 experiment remains TERMINAL with broker flat, posted net
`-0.07953733 USDT`, and `all_ten_complete=false`. It is a failed-safe-flat
partial-basket experiment, not a ten-leg execution PASS or research evidence.
V3 pins that filled/accounted terminal predecessor rather than pretending it
was NO_SEND. The final-night namespace refuses preparation when selection is
missing but new wire/experiment history exists. Legacy rollback is forbidden
for this namespace; do not restore old bybot/web writers beside KITY.

## Read-only account evidence and one remaining blocker

At **18:40:27.085 UTC**, authenticated account-instrument GET succeeded for
all ten exact symbols. Material contract/lot/tick/funding specification fields
matched their public instrument counterparts. API key GET reports derivatives
Order/Position permissions, readOnly=0, a subaccount, and expiry November 6.
Private account identity and raw replies remain private; public receipts contain
only sanitized assertions and hashes. `Trading` proves instrument listing in
the checked account response; it does **not** prove create acceptance or legal
agreement acknowledgement. RPI flags are unrelated to that acknowledgement.

The actual earlier XAU create was refused with `110123` / Trading Terms.
No checked GET response supplies an accepted-terms acknowledgement. The owner
now confirms opening XAUUSDT in the intended subaccount also shows no terms
prompt. This establishes the UI account check, **not acceptance**.

The official [Sign Agreement API](https://bybit-exchange.github.io/docs/v5/user/sign-agreement)
documents a **signing POST**, `/v5/user/agreement`, rather than an agreement-status
GET. It can be signed through that endpoint only by the master account; the
resulting eligibility extends to its subaccounts. Metals XAU/XAG and stock
perpetuals share `categoryV2=1` (`category=2` is the legacy equivalent).
The [official UI guide](https://www.bybit.com/en/learn/bybit-tradfi/trade-tradfi-perpetuals-bybit)
also distinguishes the metals agreement from the ordinary TradFi disclosure.
Neither endpoint signing nor personal acceptance was performed by the agent.
The earlier all-ten GET receipt remains unchanged; this later finding has its
own [source-contract addendum](evidence/kity_final_night_20261015/terms_source_contract_v1.json).

**Remaining blocker:** `TRADING_TERMS_ACKNOWLEDGEMENT_UNCONFIRMED`.
Engineering/static blocker list is empty in this bounded review. This is not
permission to test acknowledgement by placing another order. No automatic
retry or new TTL proposal is running while the owner resolves legal access.

If the prompt remains absent, the owner can ask Bybit support from the master
account (draft only; no message sent):

> My subaccount API received 110123, “You must agree to the Trading Terms”,
> for XAUUSDT. Opening TradFi → Futures on the master and intended subaccount
> shows no agreement prompt. Please confirm the metals/stock-perpetual
> agreement status inherited from the master account and provide the UI flow
> for me to review and personally accept it, without placing a trade.

No agent should accept the agreement for the owner or request broader key
permissions as a workaround.

## Frozen next operation — only after blocker closure

There is **no actionable intent/hash yet**. Do not start a ten-minute TTL while
awaiting terms. After the owner personally resolves/accepts the applicable
agreement, verify the original lock/one writer/health and fresh account sources,
then prepare exactly one proposal using the installed V3 entrypoint:

```bash
cd /opt/bybot-research/kity-micro-owner-20261015/app-v3-final-night
/root/by-bot/.venv/bin/python -B -m research_lab.kity_micro_bounded_owner_v2 \
  --config /opt/bybot-research/kity-micro-owner-20261015/runtime/night-final-20261015/config-v3-final-night.json \
  --config-sha256 4b67083fe925735b69eada2a038e30fc9d4aaf0bd76552e7c110ea3a074f220f \
  --command '{"kind":"PREPARE_BOUNDED"}'
```

This is future operator documentation, **not executed now**. Read its exact
result/immutable intent; show all ten quantities, price bands, gross and expiry.
Only a separate literal human `GO KITY_EXECUTION_MICRO_INTENT_V2 <new hash>`
allows the one GO_INTENT command for that same hash. No rehearsal, coding or
document review between that GO and dispatch. An expired proposal is not
extended or replaced automatically. This is the owner's October15 final-night
scope, not transferable permission for another day.

Bounds remain gross <=215 USDT, immediate all-in loss trigger15/accepted
execution overshoot, 30min from first durable entry intent, +/-0.5%,10min,
rounding shortfall <=20.3%, original five-long/five-short basket. No averaging,
scaling, repeat entry or research/C1–C3 inference. Existing durable native
protection, uncertain-send reconciliation, owned partial unwind and final
cost/flat readback remain mandatory. Final result must distinguish complete-ten
execution/lifecycle PASS from FAILED_SAFE_FLAT; accounting-unknown is never PASS.

## Verification and preservation

Targeted suite rerun after the source freeze: **169 passed in 7.75s**, including
nine V3 cases. Command: pytest on final_night_v3, incident_recovery_v2_2,
physical_owner_v1, physical_e2e_v1, supervisor_v1, account_bridge_v1,
bounded_owner_v2, transport_v1, pricing_intent_v2, native_protection_v1,
runtime_v1 and integration_v3 test files. Root-only review; no independent
reviewer retry, no full repository suite. Signed synthetic ten-leg/native-stop/
restart/after-expiry exit replay passes; it is not actual exchange acceptance.

No changes to Alpaca's owned LIVE management, ATT1, LIQ, Claude/research,
the original cron, or bybot/web inhibition. No legal-signing POST, order
pre-check POST or new broker order was used in this eligibility investigation.

Final read-only runtime check **18:49:45.077 UTC** independently confirms the
same16 installed pins/config/unit, PID2209853/restarts0/original lock,
HEALTHY/ORDERS_OFF/noactiveplan, no intent/selection, and only the original
three POST barriers. Old bybot/web PIDs remain0. This final check made no broker
GET or POST; the account-flat source remains the dated18:40 capture above.
See [frozen_runtime_readback_v1.json](evidence/kity_final_night_20261015/frozen_runtime_readback_v1.json).
