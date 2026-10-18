# Monthly account/transport closeout — authorized ORDERS_OFF continuation

Continue the accepted Monthly/native design, not a strategy redesign. No deployment,
activation, new manager, owner-GO generation, credential access or broker mutation.

1. Reproduce two concrete holes with offline counterexamples: the existing restricted
   LIVE client rejects Monthly's frozen notional-market wire format; native Monthly
   entry does not reconcile all account positions/orders/cash immediately under lock.
2. Reuse DynamicLiveClient with an explicit Monthly wire contract, preserving its
   default routes, exact one-use permits, host/redirect restrictions and default OFF.
   Permit native Monthly dispatch only after existing durable reservations. Add a
   fresh account/clock/asset/quote/complete-custody/cash/gross admission immediately
   before a new buy. A foreign NET is a blocking dependency, never adopted.
3. Exercise actual serializers through the restricted client into fake HTTP,
   including lost responses, native protection, ratchet/rearm, exit and restart.
   Record source/test hashes and exact remaining activation/handoff/finality gates;
   update the existing board/checkpoint. Keep all VPS financial files unchanged.

Frozen signal, sizing, stop, cooldown and month-end calendar are unchanged.
Current owner approval covers this implementation, not live monetary activation.
