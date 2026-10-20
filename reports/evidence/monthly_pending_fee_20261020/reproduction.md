# Exact acceptance, 20 October 2026

Material identity and all51 file hashes are in source_manifest.json;18 test/helper
file hashes are in test_manifest.json. Local command used an isolated copy of
those sources/tests, removed the checkout from sys.path, and denied socket
connect/connect_ex/sendto/create_connection before importing pytest.

Local pytest arguments: -q --timeout=300 --rootdir APP --confcutdir APP, the
17 test modules below, and a private JUnit output. No whole-repository suite.
After pytest: check loaded manifest modules resolve inside APP (39; fallback0),
then rehash every source against the manifest.

Server command: clean environment (PATH, LANG, OPENBLAS_NUM_THREADS=1,
OMP_NUM_THREADS=1), timeout900, unshare --net, nice15, existing venv python -I -B.
Same code/tests, socket denial, private candidate basetemp; no timeout plugin
argument required on server. Final independent SSH GET rehashed all51 sources,
18 tests and93 pre-existing non-secret static pins; candidate unselected by the
existing financial/observer units. No units installed/started/reloaded.

- test_alpaca_cost_activity_source_v1.py
- test_alpaca_cost_raw_transport_v1.py
- test_alpaca_day_monitor_v1.py
- test_alpaca_monthly_account_transport_v1.py
- test_alpaca_monthly_binding_v1.py
- test_alpaca_monthly_cost_source_v1.py
- test_alpaca_monthly_cycle_custody_v1.py
- test_alpaca_monthly_e2e_rehearsal_v1.py
- test_alpaca_monthly_native_adapter_v1.py
- test_alpaca_monthly_native_binding_v1.py
- test_alpaca_monthly_notifications_v1.py
- test_alpaca_monthly_pending_fees_v1.py
- test_alpaca_monthly_release_v1.py
- test_alpaca_monthly_sizing_parity_v1.py
- test_alpaca_monthly_standing_v1.py
- test_alpaca_strategy_parity_v1.py
- test_run_alpaca_monthly_binding_v1.py

Both suites:274 PASS. The5-minute per-test local limit and15-minute server
process limit are test budgets, not changes to any production timeout.
