# Design Risks — FIT Generator: Basic Mechanical Split

Design tensions and anticipated refactor pressure points. Named precisely so future-Waylon can recognize the symptom when it appears.

---

### 1. Dual-State `Segment.body` (High Likelihood)

**The tension:** A segment is either inline (`is_inline=True`, body is a string) or subdoc (`is_inline=False`, body is a block list). Every method on `Segment` that touches body content branches on `is_inline`. The branching tax is currently small — three or four methods. As the class grows, each new method pays it again.

**The clean fix and why it doesn't work cleanly:** Two classes (`InlineSegment`, `SubdocSegment`) with a shared base eliminates the flag. But segments *transition* from inline to subdoc during the reduction loop. If the object is immutable, `Document` must swap list entries, moving the branching up one level and making mutation louder. The domain is genuinely two-state; neither modeling choice eliminates the friction.

**When you'll feel it:** When adding a new method that branches on `is_inline` and the branching feels like a copy-paste from a previous method. That's the signal to revisit the class boundary.

**Current call:** Accept the dual-state field. The mutable single-class design is right for this scale.

---

### 2. `Segment.reduce()` Role Inversion Under DP (Medium Likelihood, High Impact)

**The tension:** `Segment.reduce()` currently owns the removal algorithm — it decides which blocks to evict. This works for the greedy Phase 1 implementation. When `SCORING.md`'s DP optimizer is integrated, the optimizer needs joint visibility across *all* segments simultaneously to allocate the token budget globally. A segment-local decision cannot guarantee global optimality.

**What changes:** `Segment.reduce()` as a decision-maker becomes `Segment.states()` or `Segment.enumerate_trims()` as a state-enumerator — returning a list of possible (blocks_removed, token_cost, value) tuples. The optimizer, living in the external reduction loop layer, selects the globally optimal combination and applies it via something like `segment.apply_trim(state_index)`.

**What doesn't change:** `Document` remains a container with an iterator. The external loop layer is where the intelligence lives in both designs — greedy now, DP later. The seam is already in the right place.

**The `is_critical_reduce` loop optimization** is also superseded: the DP naturally handles the two-tier budget (Soft/Hard Threshold) as dual capacity constraints, without a preliminary scan. The scan is a clean Phase 1 optimization; don't over-invest in it.

**When you'll feel it:** When integrating `SCORING.md`. Plan for `Segment.reduce()` to become state enumeration at that point. The refactor is a role inversion, not a rewrite.

---

### 3. `Segment` Boundary Width (Low Likelihood, Worth Watching)

**The tension:** `Segment` currently holds: reduction algorithm, serialization format knowledge (`(~N tokens)` annotation, subdoc link syntax), cache management, inline/subdoc state, and the demotion transition. It's large but cohesive around a genuine axis — all of these concern the state and representation of one named section. It's not a god object yet.

**Where it could break:** Serialization format changes (new FIT levels, debug output, alternate formats) that shouldn't require touching `Segment`. If `serialize_inline_component()` needs to vary by context, the format knowledge becomes a liability. The current design assumes FIT format is stable, which is reasonable for Phase 1.

**When you'll feel it:** If you add a second serialization mode. At that point, extract serialization to a `SegmentRenderer` or pass format parameters in — don't add another branch to `serialize_inline_component()`.

---

### 4. `Document.names` Encapsulation Leak (Low Likelihood)

**The tension:** Exposing `Document.names` (segment names in document order) breaks encapsulation slightly — internal consumers can iterate `Document` directly and never need names; the property exists for external consumers (Writer, diagnostics). It's a known rough edge.

**When you'll feel it:** If the pattern of external access to `names` grows beyond the Writer. The way it gets used will point toward the right refactor — possibly a richer `Document` interface, possibly moving more responsibility into `Document.write()`.

**Current call:** Leave it visible. The friction is informative.

---

### 5. `NameGenerator` Scoping (Low Likelihood, Easy to Miss)

**The tension:** `NameGenerator` is stateful — it tracks duplicate counts and heading indices per document. It's instantiated inside `Document.__init__` and resets naturally between documents. If it were ever extracted and injected externally (e.g., for testing), reuse across documents would bleed dedup state across document boundaries.

**When you'll feel it:** If you inject a shared `NameGenerator` instance for testing and see unexpected `_01` suffixes on segment names. Reset between documents or instantiate fresh per `Document`.
