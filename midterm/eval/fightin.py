"""Which words are really more frequent in recent headlines? Log-odds with a Dirichlet prior.

Monroe, Colaresi & Quinn (2008), "Fightin' Words", with an informative Dirichlet prior:
for word w with counts y_a (recent headlines) and y_b (earlier headlines), corpus sizes
n_a and n_b, and prior alpha_w = alpha0 * (y_a + y_b) / (n_a + n_b):

    delta = log((y_a + alpha_w) / (n_a + alpha0 - y_a - alpha_w))
          - log((y_b + alpha_w) / (n_b + alpha0 - y_b - alpha_w))
    var   = 1 / (y_a + alpha_w) + 1 / (y_b + alpha_w)
    z     = delta / sqrt(var)

The prior shrinks rare words toward the pooled rate, so a word seen 3 times against 0
does not get an infinite "lift" the way a share ratio does. Words with |z| > 1.96 are
kept.

alpha0 (prior strength) = 500. On the 2026-10-11 전기차 headlines (604 recent tokens,
1867 earlier) z for 카지노 / 중국차 was: pooled prior (2471) 1.85 / 1.43, 1000: 2.32 / 1.81,
500: 2.55 / 2.01, 100: 2.71 / 2.21. A prior as large as the data hides real drivers
(중국차); 500 keeps 2-vs-0 words below the cutoff. 카지노 is genuinely over-represented
there (spam flooded the feed), so the spam filter, not this test, is what removes it.
"""
import math

Z_CUTOFF = 1.96
ALPHA0 = 500


def log_odds_z(counts_a, counts_b, alpha0=ALPHA0):
    """{word: z} for every word in either corpus; z > 0 means more frequent in corpus a."""
    n_a, n_b = sum(counts_a.values()), sum(counts_b.values())
    if not n_a or not n_b:
        return {}
    out = {}
    for w in set(counts_a) | set(counts_b):
        y_a, y_b = counts_a.get(w, 0), counts_b.get(w, 0)
        alpha = alpha0 * (y_a + y_b) / (n_a + n_b)
        delta = (math.log((y_a + alpha) / (n_a + alpha0 - y_a - alpha))
                 - math.log((y_b + alpha) / (n_b + alpha0 - y_b - alpha)))
        out[w] = delta / math.sqrt(1 / (y_a + alpha) + 1 / (y_b + alpha))
    return out


def self_check():
    common = {f"w{i}": 20 for i in range(20)}
    a = {**common, "new": 30}
    b = {**common, "new": 1}
    z = log_odds_z(a, b)
    assert z["new"] > Z_CUTOFF, z["new"]                  # strongly over-represented
    assert abs(z["w0"]) < Z_CUTOFF, z["w0"]               # same rate in both
    assert log_odds_z({**common, "rare": 2}, common)["rare"] < Z_CUTOFF  # 2 vs 0 is not significant
    assert log_odds_z({}, common) == {}


if __name__ == "__main__":
    self_check()
    print("self-check ok")
