"""Tourism-recommendation evaluation metrics: numeric probes used in eval-methods.md.

Purpose: show numerically (a) how Precision/Recall/NDCG/MAP/MRR behave when the
candidate set is tiny (K=5..10), (b) how each reacts to a super-relevant
"must-visit" item at rank 1, and (c) how NDCG's 2^rel-1 gain blinds it to
mediocre-but-not-bad recommendations (the 3.8-star trap).

Run:  python research/eval_metrics_probe.py     (stdlib only, no numpy needed)
"""
from __future__ import annotations

import math


def dcg(rels: list[float]) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg(ranks_rel: list[float], ideal_rel: list[float]) -> float:
    idcg = dcg(sorted(ideal_rel, reverse=True))
    return 0.0 if idcg == 0 else dcg(ranks_rel) / idcg


def precision_at_k(ranks_rel: list[float], k: int, thresh: float) -> float:
    top = ranks_rel[:k]
    return sum(1 for r in top if r >= thresh) / k


def recall_at_k(ranks_rel: list[float], k: int, thresh: float) -> float:
    total = sum(1 for r in ranks_rel if r >= thresh)
    if total == 0:
        return float("nan")
    return sum(1 for r in ranks_rel[:k] if r >= thresh) / total


def ap(ranks_rel: list[float], thresh: float) -> float:
    hits, s = 0, 0.0
    for i, r in enumerate(ranks_rel, start=1):
        if r >= thresh:
            hits += 1
            s += hits / i
    return s / hits if hits else float("nan")


def mrr(ranks_rel: list[float], thresh: float) -> float:
    for i, r in enumerate(ranks_rel, start=1):
        if r >= thresh:
            return 1.0 / i
    return 0.0


def report(name: str, ranked: list[float], n_relevant: int, k: int = 5, thresh: float = 2.0) -> None:
    print(f"\n### {name}  (relevant = rel >= {thresh}, K={k})")
    print(f"  ranked relevance: {ranked}")
    print(f"  Precision@{k}: {precision_at_k(ranked, k, thresh):.3f}")
    print(f"  Recall@{k}   : {recall_at_k(ranked, k, thresh):.3f}  (relevant items in pool: {n_relevant})")
    print(f"  MAP (avg over 1 user, this list) : {ap(ranked, thresh):.3f}")
    print(f"  MRR: {mrr(ranked, thresh):.3f}")
    print(f"  NDCG@{k}: {ndcg(ranked[:k], ranked):.3f}")


# 1) A genuinely good list: one must-visit (rel=3) + four solid (rel=2) + four meh (rel=1)
GOOD = [3, 2, 2, 2, 2, 1, 1, 1, 1, 0]
# 2) Same top-5 quality, but the must-visit is demoted behind a "safe 4A" filler
SAFE_GRADE_TOP = [2, 2, 3, 2, 2, 1, 1, 1, 1, 0]
# 3) Star-average trap: everything 3.8-4.1 stars -> "all relevant" by a 4.0 bar,
#    nothing outstanding. rel=2 flat vs a list with two standouts.
FLAT_4 = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
TWO_STANDOUTS = [3, 3, 2, 2, 2, 1, 1, 1, 1, 1]

report("A. good list", GOOD, 9)
report("B. must-visit demoted to #3", SAFE_GRADE_TOP, 9)
report("C. every item mediocre-but-fine (the 3.8-star trap)", FLAT_4, 10)
report("D. two standouts then tail", TWO_STANDOUTS, 9)

print("\n### Gap analysis: what part of NDCG comes from the top-1 item?")
for t in (3, 4, 5):
    g = dcg(GOOD[:t])
    print(f"  top-{t} term sum={g:.3f};  share of top-5 DCG={g / dcg(GOOD[:5]):.3f}")

print("\n### K sensitivity: Precision@K for the SAME list, K=1..10 (list A)")
for k in range(1, 11):
    print(f"  P@{k}={precision_at_k(GOOD, k, 2.0):.2f}  R@{k}={recall_at_k(GOOD, k, 2.0):.2f}")

print("\n### Super-relevant handling: rank-1 must-visit vs rank-3")
print(f"  MRR  good={mrr(GOOD, 2.0):.3f}  demoted={mrr(SAFE_GRADE_TOP, 2.0):.3f}")
print(f"  NDCG@5 good={ndcg(GOOD[:5], GOOD):.3f}  demoted={ndcg(SAFE_GRADE_TOP[:5], SAFE_GRADE_TOP):.3f}")


# ---------------------------------------------------------------------------
# Second probe: the "two standouts" list above scores ~= list A on plain NDCG,
# because 2^3-1=7 for the single top-1 item dwarfs the second standout.
# alpha-NDCG (Clarke et al. 2008) with alpha=0.5 discounts repeat hits on the
# same "aspect", i.e. it rewards *distinct* things being great.
# ---------------------------------------------------------------------------
def alpha_ndcg(ranked: list, aspects: list, alpha: float = 0.5, k: int = 5):
    """aspects[i] = cluster id of item at rank i."""
    gain, discounts = {}, []
    for i, (r, a) in enumerate(zip(ranked[:k], aspects[:k])):
        before = gain.get(a, 0.0)
        g = (2 ** r - 1) * sum(alpha ** j for j in range(int(before)))
        gain[a] = before + (1.0 if r > 0 else 0.0)
        discounts.append(g / math.log2(i + 2))
    return sum(discounts)


def novel_ndcg(ranked: list, aspects: list, k: int = 5):
    seen, out = set(), []
    for i, (r, a) in enumerate(zip(ranked[:k], aspects[:k])):
        g = 0.0 if a in seen else (2 ** r - 1)
        seen.add(a)
        out.append(g / math.log2(i + 2))
    return sum(out)


# 5 distinct themes per list (categories at top-5): 1 standout + 4 solid + 1 meh
A_T = ["cut", "cut", "cut", "cut", "cut"]
D_T = ["cut", "hike", "hike", "cut", "cut"]
print("\n### Diversity-aware NDCG (alpha=0.5) / Novelty-NDCG, top-5")
print(f"  A one standout : alpha-NDCG={alpha_ndcg(GOOD, A_T):.3f}  N-NDCG={novel_ndcg(GOOD, A_T):.3f}")
print(f"  D two standouts: alpha-NDCG={alpha_ndcg(TWO_STANDOUTS, D_T):.3f}  N-NDCG={novel_ndcg(TWO_STANDOUTS, D_T):.3f}")

