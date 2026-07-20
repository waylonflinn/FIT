---
name: fit-creation
description: Create and maintain Fitted Information Trees (FITs) — agent-optimized document structures that load the right amount of information per task. Use when authoring or restructuring markdown intended for agent consumption (design docs, roadmaps, references, hand-off documents), when a document approaches its token thresholds, or when converting an existing large document. Covers born-fitted authoring (Level 4), threshold configuration via .fit.toml, splitting procedure, read-set design, and maintenance.
---

# Creating FITs

A FIT structures a body of information as a tree of markdown documents: a root
node carrying the most load-bearing content plus annotated links to
subdocuments holding detail. The goals, in order: (1) any single task loads
only what it needs, (2) pointers remain in context so later-relevant material
is reachable, (3) **no information is lost** — FIT is not summarization,
though it may use summaries to optimize access.

## Thresholds

Node sizes are governed by two numbers: **soft** (split trigger) and **hard**
(never exceed). They are *calibrated per repository* to its primary consumer
models — never treat them as universal constants.

**Resolution order:**
1. An explicit `--soft-threshold` or `--hard-threshold` CLI flag.
2. The corresponding key in `.fit.toml` in the document's own directory, then
   each ancestor directory up to the repository root. **Closest file wins**
   (this enables per-subtree overrides, e.g. a work unit calibrated tighter
   than its repo).
3. The package defaults: soft 3000 / hard 5000.

Soft and hard resolve independently. The CLI performs this resolution for
`measure` and `generate`; do not manually repeat config values as flags unless
you intend to override them.

If a broken `.fit.toml` prevents work on a tree, provide both threshold flags
as an explicit escape hatch. FIT warns and ignores the invalid config only
when neither effective threshold depends on it. Then, repair the broken config
when convenient.

```toml
# .fit.toml
[thresholds]
soft = 5000
hard = 8000
```

```bash
.venv/bin/fit measure doc/FILE.md
.venv/bin/fit measure --recursive doc/
.venv/bin/fit measure --soft-threshold 5000 --hard-threshold 8000 doc/FILE.md
```

**Why configurable:** thresholds track the *agentic* degradation onset of the
weakest primary consumer (see `CONTEXT_DEGRADATION.md` at this repo's root for
the evidence base). As of 2026-07: frontier Anthropic/OpenAI consumers → 5k/8k;
small local models as primary consumers, or subtrees kept comparable across
model classes → 3k/5k. When writing prose that mentions a threshold, reference
the config file rather than inlining the number — inlined numbers go stale.

## Structural conventions

- **Subdocument folder:** named after the parent document, lowercased, no
  extension. `BERNARD.md` → `bernard/model-candidates.md`.
- **Link format:** `→ [bernard/model-candidates.md](bernard/model-candidates.md) (~1,760 tokens)`
  — the `→` prefix marks a FIT descent link; link text = target path; relative
  paths; token estimate in parentheses (~4 chars/token is fine).
- **Links are the last element of their section** (a markdown heading scope).
- **The root is not a bag of links.** Each section keeps its most important,
  most frequently needed content inline; the link carries the rest. A reader
  who loads *only* the root should leave correctly oriented, not merely
  redirected.

## Born-fitted authoring (preferred)

When you author with full task context, you are the capable LLM in the
"Level 4: Task Optimized FIT" sense — fit the document at write time instead
of splitting it after it bloats:

1. **Enumerate the anticipated read sets first.** Which tasks/phases will read
   this material, and what does each actually need in context? A FIT is
   designed around its read sets the way an API is designed around its calls.
2. **Size the root for the common denominator:** what every reader needs
   (orientation, invariants, current state) plus navigation to everything else.
3. **Defer phase-specific detail** to one subdocument per coherent concern.
   Prefer subdocument boundaries that match task boundaries — the ideal read
   set is root + exactly one subdocument.
4. **Start large sections as subdocuments.** If a section's projected content
   clearly exceeds roughly half the soft threshold, don't write it inline and
   split later; write it in its subdocument from the first draft.
5. **Annotate and verify:** add token estimates to every link, run
   `fit measure` on each node, adjust.

**Read-set budget:** the total for any single anticipated task (root + its
relevant subdocuments) should stay near **15–25% of the consumer's safe
context zone**. At the frontier calibration (~150–200k safe zone) that means
roughly 30–40k tokens per read set. If an anticipated read set busts the
budget, the tree is shaped wrong for its tasks — restructure (usually: the
root carries detail that belongs one level down).

## Splitting an oversized document

Manual procedure (use when you understand the content):

1. Identify section boundaries at the dominant heading level.
2. For each section moving out: **retain in the parent** the most important /
   most-frequently-needed information; move the **full contents** to the
   subdocument; append the annotated link as the section's last element.
3. Check cross-references — links and anchors from other documents into the
   moved content must be updated; internal references between moved sections
   become cross-subdocument links.
4. Re-measure parent and every new child against the resolved thresholds.
5. Verify no information was lost (the moved text is a superset check, not a
   rewrite opportunity).

Mechanical fallback: `fit generate` (Level 1) for documents you lack context
on. Always `--dry-run` first; the original is backed up as `<name>.unfit.md`.
Prefer the manual procedure when you can — structural splitting cannot judge
what deserves to stay near the root.

## Maintenance

- After any substantial edit, re-run `fit measure`; it resolves the target's
  thresholds automatically against a present `.fit.toml` file. Over soft → split candidate at the next natural
  pause; over hard → split now.
- Editing a subdocument changes its size: refresh the parent's token
  annotation when it drifts more than ~20%.
- When a subdocument outgrows the thresholds, recurse: it becomes an overview
  with its own folder (`bernard/model-candidates.md` →
  `bernard/model-candidates/…`).
- When *authoring within* an existing FIT (adding a section, extending a
  node), honor the conventions above — don't append past the soft threshold
  because splitting feels like a separate chore. It is part of the edit.

## Verification checklist

- [ ] Every node ≤ hard threshold; roots at or under soft.
- [ ] Every descent link: `→` prefix, relative path, text = target, current
      token estimate, last element of its section.
- [ ] Subdocuments live in the correctly named folder.
- [ ] The root reads as a useful standalone overview, not an index.
- [ ] No information lost relative to the pre-split content.
- [ ] Each anticipated read set fits the budget (15–25% of consumer safe zone).

## Companion: reading a FIT

When a FIT root seems relevant to the task, read it; then read only the linked
subdocuments relevant to the task at hand, checking the token annotations
before descending (skip nodes larger than the hard threshold until confirmed
necessary). If more nodes become relevant later in the session, read them
before proceeding. Recurse down the tree the same way.
