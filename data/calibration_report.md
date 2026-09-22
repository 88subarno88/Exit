# Calibration report (2026-09-22)

619 rows, 340 tokens, 1 day(s) (2026-09-22 to 2026-09-22). Target: cost of selling immediately across all measured venues, vs consolidated mid. 5-fold CV grouped by token.
619 more sales could not be absorbed by the merged book at all (no venue truncated). They can't be fitted, so they're scored instead: 'false comfort' = share a model prices under 10%. Dropped: 152 sales where a venue capped its levels (thin vs truncated unknowable); 0 token-days with no CMC volume/sigma.

| model | Y | delta | median abs err | median factor off | R^2 (log) | false comfort |
|---|---|---|---|---|---|---|
| textbook sqrt, global Y | 1.66 | 0.500 | 9.3 bps | x1.66 | 0.483 | 85% |
| power law, global Y **(shipped)** | 4.44 | 0.646 | 9.3 bps | x1.61 | 0.484 | 62% |
| learned Y per token | per token | 0.646 | 8.9 bps | x1.54 | 0.637 | 63% |

Median absolute error by order size (out-of-fold, bps):

| size | n | sqrt | power | learned |
|---|---|---|---|---|
| $10,000 | 307 | 7.1 | 6.8 | 6.6 |
| $100,000 | 239 | 16.6 | 19.7 | 15.4 |
| $1,000,000 | 62 | 8.1 | 7.2 | 9.3 |
| $10,000,000 | 11 | 8.1 | 9.7 | 12.5 |

What predicts a token's Y (GBM feature importance): log_sigma 0.53, turnover 0.16, history_days 0.14, log_mcap 0.09, log_volume 0.08

The learned model did not beat the power law by the required 5%, so the power law ships. Published as a negative result.
