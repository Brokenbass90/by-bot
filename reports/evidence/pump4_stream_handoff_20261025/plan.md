# Bounded streaming continuation

Existing handoff/report is the accepted design; no strategy or architecture work.
1. Verify the exact reviewed candidate and original selected OFF state. Completed.
2. Stop only DATA timer while inactive, acquire old DATA writer lock, byte-copy
   all persistent DATA to candidate private root, preserve original in place.
   New immutable binding selects reviewed source pins. Same systemd timer/unit
   identity, restrictions, 60s gate and original account owner remain.
3. Rebind existing sole OFF owner to new DATA via separate immutable config/scope,
   only if old state has no GO/admission/flows/risk/attempts/send barriers and
   fresh broker GET flat. Stop old before selecting new; original account lock.
   Preserve old scope/config/history/claims. Existing health cron stays unchanged.
4. Actual new H1 source and durable publication timestamps; fresh source/account
   OFF diagnostics and bounded risk/cost packet. No monetary GO or POST.
5. Rollback must stop both workers and preserve candidate evidence. Copy-forward
   compatible DATA with prefix verification, restore original binding/unit/wrapper;
   reject any rollback with financial state/unknown changes. Never reset history.
