| source | topic | model (chosen on training) | holdout n | MAE | MASE vs naive | MAPE | 80% interval coverage | direction hit (p vs coin) |
|---|---|---|---|---|---|---|---|---|
| google | 전기차 | ses | 52 | 5.13 | 1.059 | 7.8% | 85% | 52% (p=0.4449) |
| google | 갤럭시 | naive | 52 | 6.79 | 1.0 | 11.0% | 56% | - |
| google | 스마트 안경 | mean4 | 52 | 7.13 | 1.005 | 24.8% | 98% | 50% (p=0.5561) |
| google | 피지컬 AI | only 24 forecast origins; need more than 72 | | | | | | |
| google | physical AI | naive | 52 | 6.15 | 1.0 | 14.6% | 98% | - |
| wiki | 전기차 | naive | 180 | 11.29 | 1.0 | 42.5% | 59% | - |
| wiki | 갤럭시 | ses | 180 | 143.12 | 0.845 | 54.5% | 50% | 65% (p=0.0) |
| wiki | 스마트 안경 | decay | 180 | 31.11 | 1.292 | 38.3% | 73% | 53% (p=0.2512) |
| wiki | 피지컬 AI | naive | 180 | 430.87 | 1.0 | 41.7% | 59% | - |
| wiki | physical AI | only 34 forecast origins; need more than 200 | | | | | | |

Worked examples (one real forecast each):

| source | topic | data up to | model | predicted | 80% interval | actual | naive predicted |
|---|---|---|---|---|---|---|---|
| google | 전기차 | 2026-10-04 | ses | 51.0 | 43.0–58.2 | 48.0 | 48.0 |
| google | 갤럭시 | 2026-10-04 | naive | 48.0 | 43.6–52.3 | 45.0 | 48.0 |
| google | 스마트 안경 | 2026-10-04 | mean4 | 24.2 | 0.0–75.2 | 100.0 | 23.0 |
| google | physical AI | 2026-10-04 | naive | 23.0 | 15.6–34.5 | 22.0 | 23.0 |
| wiki | 전기차 | 2026-10-11 | naive | 35.0 | 23.7–49.7 | 40.0 | 35.0 |
| wiki | 갤럭시 | 2026-10-11 | ses | 361.1 | 251.3–508.7 | 389.0 | 142.0 |
| wiki | 스마트 안경 | 2026-10-11 | decay | 45.3 | 27.8–74.0 | 152.0 | 99.0 |
| wiki | 피지컬 AI | 2026-10-11 | naive | 293.0 | 208.0–483.4 | 303.0 | 293.0 |
