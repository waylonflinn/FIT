# FIT Generator — Scoring Model

*Discussion: Waylon Flinn and Henry — April 15, 2026*

---

## Motivation

The current `reduce_segment` algorithm uses a hand-coded priority ordering — an implicit greedy approximation of a scoring function. Making the score function explicit enables:

- Global optimization across segments (DP instead of greedy)
- Consistent extension to higher FIT levels (query-aware selection, inline vs. subdoc decisions)
- Clean integration of TF/IDF and query-match signals

---

## Algorithm: From Greedy to DP

The reduction problem maps to a **multi-choice knapsack**: each segment has multiple trimming states, each with a (tokens, value) pair. The optimizer selects one state per segment to maximize total value within the token budget.

This is polynomial: O(n · states_per_segment · W) where W is the token budget. Tractable at document scale.

The **two-tier budget** (Soft/Hard threshold) maps onto two sequential passes or a DP with dual capacity constraints.

**Cross-segment awareness:** greedy operating segment-by-segment cannot guarantee global optimality. DP does — the decision about how much to trim segment A becomes jointly optimal with segment B.

**Diversity complication:** if block values depend on which neighbors are retained, the problem becomes a sequence knapsack. DP state:

```
dp[i][last_type][tokens_used] = max value
```

O(n · |types| · W) — still tractable. Alternatively: compute diversity against original (pre-removal) neighbors. Simpler, slightly inaccurate, probably fine for phase 1.

---

## Block Value Function

For block `b` at global position `i` among `N` total blocks in the segment, and type-local position `j` among `k` blocks of its type:

```
V(b) = w(type, rank)
     · e^(-λ_g · i/N)          # global positional decay
     · e^(-λ_t · j/k)          # type-local positional decay
     · D(b)                     # diversity bonus
     · L(k)                     # last-of-type penalty
     · S(N)                     # segment scale factor
```

### Base weight: `w(type, rank)`

- `type` — code vs. prose
- `rank` — priority order within code blocks (from `--inline-languages`). Priority multiplier should be exponential: `α^rank` where α > 1, so the highest-priority language is most expensive to remove

### Global positional decay: `e^(-λ_g · i/N)`

Blocks earlier in the segment (anchors, introductions) are worth more than trailing blocks. Normalized by segment length so decay rate is consistent across segments of different sizes.

### Type-local positional decay: `e^(-λ_t · j/k)`

Independently decays within each block type. The first code block in a segment is worth more than the third. Captures the fact that a first example is load-bearing; additional examples are supplementary.

### Diversity bonus: `D(b)`

```
D(b) = 1 + δ · (left_neighbor_type ≠ type) + δ · (right_neighbor_type ≠ type)
```

A code block adjacent to a paragraph is worth more than a code block in a run of code blocks. Each cross-type neighbor adds δ. Captures the local information density of a code+prose pair vs. homogeneous runs.

### Last-of-type penalty: `L(k)`

Step function: large multiplier when k=1 (removing the last block of a type). Smooth alternative: `e^(-γ/k)`, which also penalizes second-to-last removal, grading continuously.

Applies equally to last code block and last paragraph — both are heavily penalized.

### Segment scale factor: `S(N)`

```
S(N) = 1/N   (or e^(-μ·N))
```

Per-block value scales inversely with segment size. Removing one block from a two-block segment is more consequential than removing one from a ten-block segment. Makes the optimizer conservative on small segments.

---

## TF/IDF Extension

Model each segment as a document; all segments form the corpus. Block score = sum of per-term TF/IDF weights. Enters as a multiplicative factor in `w(type, rank)` or as an additive term.

**Property:** rare terminology in one segment automatically scores higher relative to boilerplate spread across many segments. Inverse document frequency naturally captures uniqueness.

**Query-aware FIT (higher levels):** multiply each block's TF/IDF score by its query term overlap. The segment-as-document model slots in cleanly — no structural change to the optimizer, just an additional term in the value function.

---

## Extension to Higher FIT Levels

The scoring model is level-agnostic. At level 1 (mechanical split) it drives within-segment block reduction. At higher levels, the same function scores:

- Which segments to inline vs. subdoc
- Which subdocs to include in a query response
- How to rank segments for partial retrieval

TF/IDF + query match enters at higher levels without changing the optimization structure. The DP formulation makes this extension natural: adding terms to the value function, not redesigning the algorithm.

---

## Open Questions

- Exact vs. approximate diversity bonus: sequence DP (exact) vs. original-neighbor approximation (simpler). Approximate is probably sufficient for phase 1; exact matters more at higher levels with query-aware selection.
- Hyperparameter values: λ_g, λ_t, α, δ, γ, μ — need calibration, likely against a small set of representative documents.
- Integration path into `001_basic_mechanical`: deferred. This document stands alone until the integration scope is clear.
