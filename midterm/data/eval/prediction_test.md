| source | topic | model (chosen on training) | holdout n | MAE | MASE vs naive | MAPE | 80% interval coverage | direction hit (p vs coin) |
|---|---|---|---|---|---|---|---|---|
| google | 전기차 | ses | 52 | 5.74 | 1.055 | 7.9% | 83% | 58% (p=0.1659) |
| google | 갤럭시 | naive | 52 | 6.31 | 1.0 | 9.2% | 60% | - |
| google | 스마트 안경 | mean4 | 52 | 6.39 | 1.011 | 26.7% | 94% | 61% (p=0.0804) |
| google | 피지컬 AI | mean4 | 52 | 10.58 | 1.114 | 38.5% | 98% | 50% (p=0.5551) |
| google | physical AI | naive | 52 | 6.27 | 1.0 | 14.9% | 98% | - |
| wiki | 전기차 | naive | 180 | 11.17 | 1.0 | 40.2% | 60% | - |
| wiki | 갤럭시 | ses | 180 | 132.56 | 0.878 | 50.0% | 49% | 62% (p=0.0006) |
| wiki | 스마트 안경 | decay | 180 | 26.76 | 1.223 | 34.3% | 78% | 55% (p=0.1025) |
| wiki | 피지컬 AI | naive | 180 | 445.48 | 1.0 | 41.7% | 61% | - |
| wiki | physical AI | only 21 forecast origins; need more than 200 | | | | | | |

Worked examples (one real forecast each):

| source | topic | data up to | model | predicted | 80% interval | actual | naive predicted |
|---|---|---|---|---|---|---|---|
| google | 전기차 | 2026-10-04 | ses | 55.8 | 47.6–63.5 | 54.0 | 53.0 |
| google | 갤럭시 | 2026-10-04 | naive | 56.0 | 51.8–60.1 | 55.0 | 56.0 |
| google | 스마트 안경 | 2026-10-04 | mean4 | 26.0 | 0.0–62.9 | 100.0 | 33.0 |
| google | 피지컬 AI | 2026-10-04 | mean4 | 15.5 | 0.0–44.0 | 19.0 | 14.0 |
| google | physical AI | 2026-10-04 | naive | 17.0 | 11.3–25.5 | 16.0 | 17.0 |
| wiki | 전기차 | 2026-10-11 | naive | 35.0 | 23.0–49.3 | 40.0 | 35.0 |
| wiki | 갤럭시 | 2026-10-11 | ses | 361.1 | 252.4–509.8 | 389.0 | 142.0 |
| wiki | 스마트 안경 | 2026-10-11 | decay | 45.3 | 27.8–74.6 | 152.0 | 99.0 |
| wiki | 피지컬 AI | 2026-10-11 | naive | 293.0 | 203.6–493.7 | 303.0 | 293.0 |
