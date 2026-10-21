# PUMP4 reference plan component

`parity.json`: actual frozen producer -> callable ORDERS_OFF plan on65unique
fixtures,1ASTER missing source. This is reference geometry, not execution/restart,
fill-price, native protection or net-return proof. No R/judge/outcomes rerun.
Source/fixture/window hashes checked; source files and research inputs unchanged.
The verifier pins adapter bytes before the run and rechecks them afterwards.

From the execution checkout (read-only research sibling):

```sh
.venv/bin/python -B -m pytest -q tests/test_pump4_execution_plan_v1.py
.venv/bin/python -I -B reports/evidence/pump4_execution_plan_20261021/verify.py \
  --research-root /path/to/bybit-bot-clean-v28 \
  --fixtures /path/to/published/pump4_fixtures_v1_20261020.json \
  --output /path/to/new-exclusive-parity.json
```

Fixtures are the published file from research commitb138735,
`research_lab/results/pump4_fixtures_v1_20261020.json`, SHA256
f6badf311e888fab05a3d4131559f98152f8589d49b35c7b034e306617726ca4.
The verifier reads existing cached H1 sources; it cannot fetch/repair them or
write into the research checkout. Socket traffic is denied. Output must be new.

`tests.xml`:12root tests. `review.json`: one independentastra/high bounded review,
12overlapping tests, no findings; verifier/receipt inspection, not a second full
parity execution. No financial authority or actual broker test.
