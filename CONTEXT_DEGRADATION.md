# Context Degradation and FIT Thresholds

> **Status: living evidence base, first compiled 2026-07-11.** Collects published
> data on long-context degradation ("context rot") for the model families that
> consume FITs, and derives threshold recommendations from it. The original
> defaults (soft 3k / hard 5k) were calibrated on Claude Sonnet 4.6 from direct
> experience; this document grounds recalibration for newer models and other
> families. Revisit when: independent Fable 5 data lands, a new primary consumer
> family is adopted, or working experience contradicts a number here.

## Why this matters to FIT

FIT thresholds control per-node granularity: the soft threshold triggers
refactoring into subdocuments, the hard threshold is the node-size ceiling. Two
session-level quantities govern how big nodes can safely be:

1. **The degradation onset** — the absolute token count where a model's working
   quality measurably declines. The session (system prompt + history + tool
   results + loaded FIT nodes + working output) should stay well inside it.
2. **The read-set budget** — the fraction of that safe zone spent on loaded
   documents. A root plus a handful of relevant subdocuments should consume a
   modest share (~15–25%) of the safe zone, leaving room for actual work.

Below the onset point, the threshold's job is **precision**, not rot avoidance:
smaller nodes mean less irrelevant text loaded per link followed. So thresholds
should scale with degradation onset, but sub-linearly — a 2× larger safe zone
does not justify abandoning split discipline.

## Reading the evidence

Three source types appear below, and they disagree in a consistent, meaningful
way:

- **Comprehension benchmarks** (Fiction.LiveBench): closest analog to reading a
  design document well — tracking state changes, subtext, cross-references.
- **Retrieval stress tests** (MRCR variants): needle-finding under distractors;
  models hold these longest. Good ceiling indicator, poor working-quality proxy.
- **Practitioner reports** (agentic coding sessions, hundreds of tool calls):
  degradation onsets *earliest* here — losing track of decisions, circular
  reasoning, thrashing. This is the failure mode that matters most for FIT
  consumers, and the numbers to weight most heavily.

Rule of thumb from the data: **retrieval outlasts comprehension, which outlasts
agentic working quality.** Calibrate thresholds to the last one.

Background: the phenomenon itself was established rigorously by Chroma's
"Context Rot" study (July 2025, 18 models including the Claude 4 generation) —
performance is non-uniform in input length even on trivial tasks. Anthropic's
own docs acknowledge it without numbers ("as token count grows, accuracy and
recall degrade").

## Anthropic (Claude) models

### Baseline: Sonnet 4.6

Direct working experience (this repo's author): significant degradation effects
around **90–100k tokens**, despite the advertised 1M window. The 3k/5k defaults
were calibrated against this. Published data corroborates the Sonnet-class
picture: Fiction.LiveBench has Sonnet 4.5 dropping to **75% by 120k** (vs.
92–94% for Opus-class at the same length).

### Opus 4.5 / 4.6

| Source type | Finding |
|---|---|
| Comprehension (Fiction.LiveBench, Apr 2026 table) | Opus 4.5 and 4.6 hold **92–94% through 120k**, essentially flat from 0k. (Both show 0.0 at 192k — as does Sonnet 4.5 — almost certainly a harness artifact at the 200k API boundary, not a real collapse. Benchmark stops at 192k and is currently on hiatus.) |
| Retrieval stress (Context Arena, 8-needle MRCR v2) | Opus 4.6 ~72% at 128k, degrading continuously; Opus 4.8 (max) 75% at 128k, AUC@1M ~42%. Hard variant — treat as ceiling data. |
| Retrieval (Verdent testing, via Developers Digest) | Onset ~400k, ~2% effectiveness loss per additional 100k, unreliable past 600k. |
| Practitioner (claude-code #34685 + corroborating heavy users) | On Opus 4.6[1m]: degradation noticed from **~200k absolute**; effective high-quality context for iterative development **~300–400k**; on 200k-window models, instruction-following degrades past **~150k (~75% of window)**. |

**Synthesis: agentic-work degradation onset for Opus 4.5/4.6-class ≈ 150–200k
absolute — roughly 1.5–2× the Sonnet 4.6 baseline.** Comprehension-style
reading holds longer; retrieval much longer.

### Fable 5

**No independent per-length data exists yet** (as of 2026-07-11). Developers
Digest states this explicitly and recommends assuming "the back half of the
window is softer than the front." Vendor-adjacent posts claim better long-session
consistency than Opus 4.8, but qualitatively and without measurement. Neither
Fiction.LiveBench nor Context Arena lists it.

**Position until data lands: treat Fable 5 as Opus-4.6-equivalent** (onset
~150–200k). Revisit when independent numbers publish — the model is ~2 months
old and the leaderboards will likely add it.

### Threshold implication (Anthropic consumers)

Scaling the Sonnet-4.6-calibrated 3k/5k by the observed 1.5–2× onset improvement
gives soft 4.5–6k / hard 7.5–10k. Recommendation: **soft 5k / hard 8k** — the
conservative end of the band, with two properties in its favor:

- The new soft threshold equals the old hard threshold (clean migration: every
  previously-compliant document remains compliant; previously-warned documents
  become split candidates).
- Session math: at 5k/8k, a root plus 4–5 subdocuments ≈ 30–40k ≈ ~20% of the
  150–200k safe zone. Comfortable.

6k/10k is defensible only if the Fable 5 improvement claims verify; at that
level split pressure mostly disappears, weakening the precision benefit. Start
5k/8k, raise later on evidence.

## OpenAI (GPT) models

### GPT-5.2 / 5.5 / 5.6-class

| Source type | Finding |
|---|---|
| Comprehension (Fiction.LiveBench, Apr 2026 table) | GPT-5.2 essentially **flat through 192k** (100 → 96.9) — best retention curve in the table. Anomaly: gpt-5.2-pro scores *lower* (75–78 at 120–192k); unexplained, possibly harness/settings. |
| Retrieval (OpenAI-published MRCR v2, via secondary coverage) | GPT-5.5: **87.5% at 128–256k, 74% at 512k–1M** (vs. GPT-5.4's 36.6% — a generational jump). GPT-5.2: near-perfect to 256k. |
| Retrieval stress (Context Arena, 8-needle MRCR v2) | GPT-5.5/5.6 variants hold the top ranks (gpt-5.6-sol: 92.4% at 128k, AUC@1M 56.2% — best listed). Top-model curve shows material drop beyond ~200k, steep by 1M. |
| Practitioner (MindStudio review, verified) | "For most practical agentic tasks (**under 100K tokens of active context**), performance is strong." Instruction fidelity degrades over very long contexts, especially with many sequential constraints. No methodology given. |
| Practitioner (search-snippet only, unverified) | A sibling MindStudio piece puts the practical ceiling for reliable factual retrieval at **~80–100k**; Codex sessions report an effective window of **~258k** (and a 1M→400k advertised-limit reduction for GPT-5.5 in Codex caused overflow bugs downstream). |

**Synthesis: the GPT family shows a distinctive asymmetry.** Benchmark retention
(comprehension and retrieval) is flatter and stronger than Claude's at equal
lengths — but practitioner-reported *agentic* safe zones are **not better, and
possibly tighter**: "strong under ~100k active context" is at or below the
Opus-class 150–200k onset. The gap between GPT's benchmark curves and its
reported working quality is wider than Anthropic's, which reinforces the rule
of thumb above: do not calibrate thresholds from retrieval curves.

### Threshold implication (GPT consumers)

**Commensurate recommendation: the same soft 5k / hard 8k.** Nothing in the GPT
data justifies higher thresholds (the agentic safe zone is not demonstrably
larger than Opus-class), and nothing forces lower ones (the ~100k "strong" zone
still accommodates a 30–40k read set at ~30–40% — acceptable, if less roomy
than the Anthropic margin; sessions that push deep past 100k should lean on
smaller read sets, not smaller thresholds).

## Cross-model recommendation

- **Soft 5k / hard 8k** for repositories consumed by current frontier Anthropic
  and OpenAI agents. Calibrate to the **weakest primary consumer**, not the
  strongest.
- The unchanged principle from the README still applies beneath these numbers:
  FITs serve consumers down to small local models. An 8k-hard node is still
  navigable from a 32k-window model (root + one or two nodes), but repositories
  whose *primary* consumers are small models should keep the original 3k/5k —
  the raised thresholds are a frontier-consumer calibration, not a new default
  for all FITs.
- The reading-skill guidance ("avoid documents that are too large") must track
  the hard threshold wherever it is restated; a stale >5k in one skill and 8k
  in another will produce inconsistent agent behavior. Single-source the
  numbers where possible (e.g., per-repository config consumed by both skills
  and `fit measure`).

## Sources

**Anthropic section:**
- [Context Arena MRCR leaderboard](https://contextarena.ai/) (8-needle MRCR v2)
- [Fable 5 with 1M Context: What Actually Works in Practice — Developers Digest](https://www.developersdigest.tech/blog/fable-5-1m-context-in-practice) (Verdent figures; Fable 5 no-data statement)
- [Claude Opus 4.6 1M context: self-reported degradation starting at 40% — anthropics/claude-code#34685](https://github.com/anthropics/claude-code/issues/34685) (practitioner timeline + heavy-user corroboration in comments)
- [Fiction.liveBench, April 04 2026 results](https://fiction.live/stories/Fiction-liveBench-Feb-19-2025/oQdzQvKHw8JyXbN87) (comprehension table; read from the published results image)
- [Context Engineering for Claude Fable 5 — Lushbinary](https://lushbinary.com/blog/claude-fable-5-context-engineering-long-sessions-guide/) (cited via search snippet only; page 403'd on fetch)
- Chroma, "Context Rot" (July 2025) — foundational study of the phenomenon.

**OpenAI section:**
- [Context Arena MRCR leaderboard](https://contextarena.ai/) (GPT-5.5/5.6 rows)
- [Fiction.liveBench, April 04 2026 results](https://fiction.live/stories/Fiction-liveBench-Feb-19-2025/oQdzQvKHw8JyXbN87) (GPT-5.2 rows)
- [Everything You Need to Know About GPT-5.5 — Vellum](https://www.vellum.ai/blog/everything-you-need-to-know-about-gpt-5-5) and [GPT-5.5 Benchmark Scores — W&B ml-news](https://wandb.ai/byyoung3/ml-news/reports/GPT-5-5-Benchmark-Scores--VmlldzoxNjY0NTYzNQ) (MRCR v2 figures, via search coverage)
- [GPT-5.5 Review — MindStudio](https://www.mindstudio.ai/blog/gpt-5-5-review-agentic-model) (verified: "under 100K active context" claim)
- [GPT-5.5 Codex context limit issues — anomalyco/opencode#24171](https://github.com/anomalyco/opencode/issues/24171) (400k/1M limit confusion; effective-window reports)

*Claims marked "search-snippet only" or "via search coverage" were not verified
against the primary page (fetch blocked or secondary reporting); weight
accordingly.*
