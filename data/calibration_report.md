# Calibration report (2026-09-23)

705 rows, 348 tokens, 1 day(s) (2026-09-22 to 2026-09-22). Target: cost of selling immediately across all measured venues, vs consolidated mid. 5-fold CV grouped by token.
563 more sales could not be absorbed by the merged book at all (no venue truncated). They can't be fitted, so they're scored instead: 'false comfort' = share a model prices under 10%. Dropped: 126 sales where a venue capped its levels (thin vs truncated unknowable); 0 token-days with no CMC volume/sigma.

| model | Y | delta | median abs err | median factor off | R^2 (log) | false comfort |
|---|---|---|---|---|---|---|
| textbook sqrt, global Y **(shipped)** | 1.94 | 0.500 | 15.8 bps | x1.87 | 0.510 | 79% |
| power law, global Y | 8.53 | 0.715 | 18.5 bps | x1.84 | 0.552 | 44% |
| learned Y per token | per token | 0.715 | 15.8 bps | x1.78 | 0.626 | 45% |

Median absolute error by order size (out-of-fold, bps):

| size | n | sqrt | power | learned |
|---|---|---|---|---|
| $10,000 | 311 | 8.7 | 8.6 | 7.8 |
| $100,000 | 282 | 24.8 | 33.3 | 25.9 |
| $1,000,000 | 90 | 29.8 | 33.2 | 37.3 |
| $10,000,000 | 22 | 182.3 | 146.7 | 176.6 |

What predicts a token's Y (GBM feature importance): log_sigma 0.44, history_days 0.17, log_volume 0.14, turnover 0.12, log_mcap 0.12

The learned model did not beat the power law by the required 5%, so the power law ships. Published as a negative result.
