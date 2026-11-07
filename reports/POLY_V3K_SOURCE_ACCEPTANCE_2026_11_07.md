# Polymarket V3K source acceptance, 7 November 2026

Status **BLOCKED_CONTRACT**. The E2 writer manifest exists. Its producer SHA
089dc6379f5b7428b85f3937de4bdf918fc541d9c2dbea92b9f332d3fa3ce7f9 and shared
journal SHA bd9175ee7ccd10791f71d214376d03322eef4d9ff94100894de57ada5fb908ff
match disk. The V3K signal journal is absent, so there is no actual V3K
measurement or official-outcome evidence for this acceptance.

- Preregistration ca7ebaa3061926375bccb479d047f243a1a06c9ec191f88a5c260cc1910de4e1
  declares judge SHA 7e9c3d8fb9044445a3fdfceb882ec01673bd9c1304812a5e0c7d2e8dfb9ce6fa.
  The actual judge bytes are 544b762e0bc9048ddba2f9a217d5ed7059c147b2ab51d5ba5577c6c619331a3e.
- Producer policy name appends __V3K_K055 to the base V3 prereg name and emits
  the base prereg hash. The frozen V3K prereg is a separate file. The accepted
  ORDERS_OFF consumer explicitly permits only the V2 and V3 journals.
- The V3K prereg limits inclusion by game start at 6 Nov 00:00 UTC and applies
  a 60-second score delay. The producer filters quote time using base V3.OT
  (3 Nov 16:20 UTC) and selects a score frame before the book, with a separate
  allowance on delivery to Mac. These are different conditions. A pre-cutoff
  match and a frame received less than 60 seconds before the book need tests.
- Producer K=0.55 matches the prereg. Its market price proxy uses ask−0.01.
  Pin the price definition, observed book side, and effective score delay
  before comparing producer and judge on identical games.

The PM acceptance task is to recover the declared judge bytes or supply a
versioned prospective amendment, bind the exact V3K policy SHA, test match
cutoff and score availability against the frozen rule, and then verify the
first genuinely fresh E2 observation through the existing ORDERS_OFF path.
Historical replay, tuning K, and money admission are outside this check.
