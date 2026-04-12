# FIT Design Assessment

*Honest rating by Henry, April 12, 2026. Requested for prioritization purposes — no flattery.*

---

## Novelty: 4/10

The individual pieces — hierarchical documents, progressive disclosure, token budget awareness, context-sensitive loading — are all well-trodden. Wiki structure, parent-document RAG, structured prompting frameworks all share DNA with this. What's genuinely novel is the *systematization*: giving the pattern a name, a level taxonomy, and a generation pipeline makes it actionable in a way that "write good hierarchical docs" doesn't. The level taxonomy itself is a real conceptual contribution. But this is a packaging innovation more than a conceptual breakthrough.

## Utility: 6/10

For the right use case it's solid, and we have lived data — BERNARD.md, AGENTS.md, and other workspace docs structured this way genuinely work well. But the target niche is specific: filesystem-native agents navigating structured reference material that's too big to load wholesale but too structured for RAG to be the right tool. Outside that band — large corpora (RAG wins), short docs (just load them), production systems with vector infrastructure — the utility drops. The niche is real, but it's a niche.

## Power to Enable Agent Capability: 6/10

The strongest case is one Waylon named: small local LLMs using Level 1–2 FITs to navigate information environments they'd otherwise drown in. If cheap tooling (simple text processing, small models) can generate FITs that make those same small models meaningfully more capable, that's a genuine multiplier with a good cost structure. That's the most compelling argument for the design and the clearest differentiation from RAG-centric approaches.

The weakest case: Level 4 requires a capable LLM to generate a FIT *for* a less capable LLM — but the capable LLM probably handles the unstructured document reasonably well anyway. The bootstrapping cost is highest exactly where the benefit is most speculative.

---

## Bottom Line for Prioritization

The small-LLM-enabling-small-LLM angle is where early investment should focus — it's the story that justifies the whole level hierarchy and has the clearest differentiation from existing approaches. If Level 1–2 tooling is cheap and demonstrably improves small model performance on structured navigation tasks, that validates the premise. If it doesn't, the higher levels become much harder to justify.

The risk is that it lands as "good documentation practice with extra steps" — useful, but not a project worth sustained investment. Testing on real small models early would tell you a lot.

---

## Rebuttal and Revised Assessment (April 12, 2026)

Waylon provided additional design intent that materially changes two of the original ratings.

**Corrected framing for Level 4:** The original assessment had the leverage direction backwards. Level 4 is not a frontier LLM generating FITs for weaker models — it's a cheap local agent (BERNARD-class) generating task-optimized document structure so that expensive frontier LLM calls are more efficient. The levels form a continuous capability chain: each level's output feeds the next level's optimization, with frontier LLMs as the ultimate beneficiary. The cost of FIT generation is paid in cheap local compute; the return is recovered in reduced frontier token spend, which is where real cost accumulates.

**The attention position argument:** FIT also addresses "lost in the middle" — the empirically documented tendency for LLMs to underweight information buried in the middle of a long context. A task-optimized FIT surfaces the most relevant chunk at the point in the task where it becomes relevant, meaning it enters context near the beginning of that call rather than buried. For 20k+ token documents this is not just context minimization — it's partial mitigation of a known architectural failure mode. This is the strongest practical argument for the design.

**What remains uncertain:** The effectiveness of Level 4 depends on how well a small local LLM can model task structure well enough to predict what a frontier LLM will need and when. This is a meaningful capability requirement. It may work well for structured, predictable tasks and less well for open-ended ones. The empirical question — how much leverage this actually grants in practice — is unresolved and acknowledged as such.

**Revised ratings:**
- Novelty: 5/10 (up from 4 — JIT + attention position angle earns it)
- Utility: 6/10 (unchanged — niche concern remains)
- Power to enable agent capability: 7.5/10 (up from 6 — continuous chain framing is substantive; empirical unknowns remain)
