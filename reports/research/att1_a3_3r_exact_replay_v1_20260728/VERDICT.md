# ATT1 A3/3R exact replay

- Verdict: **FAIL**
- Quantitative gate: **FAIL**
- Capital authority: **NO**
- Live ATT1 changed: **NO**

| variant | round trip | trades | 360d return | PF | expectancy R | positive folds | negative months | max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| champion | 4.0 bps | 321 | 52.52% | 1.601 | 0.1798 | 4/4 | 0 | 6.00% |
| champion | 7.5 bps | 321 | 47.54% | 1.543 | 0.1660 | 4/4 | 1 | 6.21% |
| champion | 11.0 bps | 321 | 41.70% | 1.475 | 0.1492 | 4/4 | 1 | 6.65% |
| a3_fixed_3r | 4.0 bps | 212 | 23.09% | 1.262 | 0.1456 | 3/4 | 3 | 16.49% |
| a3_fixed_3r | 7.5 bps | 212 | 20.27% | 1.229 | 0.1309 | 3/4 | 4 | 16.90% |
| a3_fixed_3r | 11.0 bps | 212 | 17.52% | 1.196 | 0.1163 | 3/4 | 4 | 17.46% |

The R value is the preregistered fixed-risk estimate `pnl_pct_equity / 0.0075`; all capital decisions remain blocked until forward-shadow labels and execution parity exist.

The challenger failed the preregistered worst-fold, champion expectancy, and red-month comparison checks. The production champion remains unchanged; the combined A3/fixed-3R hypothesis does not proceed to forward shadow.
