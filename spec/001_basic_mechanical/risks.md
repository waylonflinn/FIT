# Risks — FIT Generator: Basic Mechanical Split

---

## High Risk — Load-bearing assumptions that haven't been verified

**R1. `_had_paragraph`/`_had_code` flags go stale after `_parse` initial reduction** ✅ Resolved

Flags are intentionally set at construction from the original block list and do not update after the initial reduce. If the initial reduce (step 6 of `_parse`) removes all non-code blocks, `_had_paragraph` remains `True` and `is_critical_reduce` correctly fires — Hard Threshold adoption at that point is the intended behavior. Design clarified in `design.md`.

---

**R2. `Document.measure()` link overhead is dynamic, not static** ✅ Resolved

The annotation is `measurer.measure(body)`, not `_cached_tokens`. `body` is immutable after construction, so the overhead is stable across the reduction loop. The design now says this explicitly and uses `measurer.measure()` throughout (not `len() // 4`). Design clarified in `design.md`.

---

**R3. Paired/nested block tokens — what is a "block"?** ✅ Resolved

Top-level paired token groups (lists, blockquotes, tables) are treated as a single block from open to matching close; nesting depth is tracked to find the correct close. Nested content is not surfaced separately. Blocks are removed as atomic units during reduction. Definition added to `_parse_segment` in `design.md`. Prototype no longer needed.

---

**R4. `pygments.get_lexer_by_name` failure modes** ✅ Resolved

`try/except ClassNotFound` is the correct pattern and works as expected. Prototype at `forge/fit/prototypes/pygments_fallback/pygments_fallback.py` tested 18 info strings including all the suspected unknowns.

Key finding: pygments knows more strings than expected — `output`, `console`, `text`, `diff`, `http` all resolve to real lexers. Only `patch` triggers `ClassNotFound` in this corpus. The fallback is still necessary (`patch` proves it), but fires rarely. Empty/whitespace strings are handled by a pre-check before `get_lexer_by_name` is called.

`get_lexer_by_name` is also case-insensitive (`PYTHON` → Python). No crashes on any input tested.

---

## Medium Risk — Fiddly bits requiring care

**R5. `trivial_extension_threshold` units are ambiguous** ✅ Resolved

All thresholds, including `trivial_extension_threshold`, are in tokens. The inline classification condition now uses `measurer.measure()` for both sides: `measurer.measure(body) <= measurer.measure(first_paragraph) + args.trivial_extension_threshold`. Design updated.

---

**R6. DriverLoop infinite loop on unsplittable oversized files** ✅ Resolved

The scenario as written was incorrect — `process_file` reads from disk, so re-queued subdoc files always have full original content, not the emptied in-memory state. The real question is whether recursion terminates at all.

It does: each split produces N ≥ `min_segment_count` pieces strictly smaller than the parent, bounded below by zero. `is_unsplittable` provides the base case. The only crack is `--min-segment-count 1`, which allows a document to produce one segment equal in size to itself and recurse infinitely. Fixed by enforcing a minimum value of 2 at startup. Design updated, config table updated.

---

**R7. DriverLoop enqueue logic — measure in loop or rely on gate?** ✅ Resolved

DriverLoop enqueues all returned paths unconditionally. The coarse initial gate in `process_file` handles filtering — this is the single decision point. Design updated.

---

**R8. markdown-it-py line map fidelity for all block types** ✅ Resolved

`token.map` is present and correct for all top-level block types tested (heading, paragraph, html_block, blockquote, bullet_list, fence). Inline tokens are not yielded at the top level and don't need maps.

Key finding: inter-block blank lines live in the gaps *between* token map ranges — not inside any token's range. Naive `lines[start:end]` slicing loses these. The fix is `lines[start:next_start]` (extending each block's slice to where the next block begins, or EOF for the last block). This absorbs the gap into the preceding block and gives byte-identical reconstruction.

Constraint: block text must never be `strip()`ed or otherwise trimmed after slicing — the trailing `\n` is load-bearing for the `next_start` scheme. Prototype: `forge/fit/prototypes/line_map/line_map.py`.

---

**R9. Segment name length — filesystem limits** ✅ Resolved

Slugs are now truncated to 200 bytes (UTF-8) in the design. The empty-slug fallback is now "any heading that slugifies to an empty string (bare headings, headings containing only punctuation, or similar)" — covers both cases explicitly. Design updated in both the `Segment` field definition and `_parse` step 3.

---

## Low Risk — Edge cases worth a test but probably fine

**R10. `is_unsplittable` boundary** ✅ Resolved

`is_unsplittable` now fires when segment count < `args.min_segment_count`. This cleanly covers both the no-headings case and the degenerate case (valid headings but too few to satisfy the minimum). The warning message in `process_file` updated to reflect the broader condition. Design updated.

**R11. `_parse_segment` re-parse fidelity**

When `_parse_segment` re-parses a segment body (during inline→subdoc demotion), it parses a fragment. Reference-style link definitions, footnotes, or other document-wide constructs defined elsewhere may not resolve correctly inside the fragment. Probably rare in practice, but worth noting for technical markdown documents.

**R12. Block removal when all blocks are already gone** ✅ Resolved

Two guards added: (1) `reduce()` is a documented no-op when `blocks` is already empty — returns 0 immediately. (2) A new `is_empty` property on `Segment` is checked as a precondition in Pass 2 of the reduction loop, skipping `reduce()` calls entirely for empty segments. Design updated.

---

## Needs a Prototype Before the Build

1. **Block grouping from `_parse_segment`** — parse a real document with lists, blockquotes, tables; establish the grouping rule before the rest of the algorithm depends on it.
2. **`pygments` fallback** — try/except around `get_lexer_by_name` with a known-bad info string, verify `"Code"` label.
3. **Line map reconstruction** — verify concatenated slices reproduce the original for a representative test document.
4. **Initial reduce + flag staleness** — construct a segment, call `reduce()`, check `is_critical_reduce` before and after.

---

## Design Risks

Anticipated refactor pressure points and design tensions for future reference.

[risks/design-risks.md](risks/design-risks.md) (~1,262 tokens)
