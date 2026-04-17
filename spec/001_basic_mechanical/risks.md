# Risks — FIT Generator: Basic Mechanical Split

---

## High Risk — Load-bearing assumptions that haven't been verified

**R1. `_had_paragraph`/`_had_code` flags go stale after `_parse` initial reduction** ✅ Resolved

Flags are intentionally set at construction from the original block list and do not update after the initial reduce. If the initial reduce (step 6 of `_parse`) removes all non-code blocks, `_had_paragraph` remains `True` and `is_critical_reduce` correctly fires — Hard Threshold adoption at that point is the intended behavior. Design clarified in `design.md`.

---

**R2. `Document.measure()` link overhead is dynamic, not static** ✅ Resolved

The annotation is `measurer.measure(body)`, not `_cached_tokens`. `body` is immutable after construction, so the overhead is stable across the reduction loop. The design now says this explicitly and uses `measurer.measure()` throughout (not `len() // 4`). Design clarified in `design.md`.

---

**R3. Paired/nested block tokens — what is a "block"?**

`Document._parse_segment` splits a body string into "an ordered list of blocks." markdown-it-py returns paired open/close tokens for lists (`bullet_list_open`/`close`, `list_item_open`/`close`), blockquotes (`blockquote_open`/`close`), and tables. These are not atomic. The question of how to group them into blocks is unspecified.

Options:
- Treat each top-level paired structure as one block (list → one block, blockquote → one block)
- Flatten to inline content and treat each paragraph-level leaf as a block

The reduction algorithm operates on blocks. If a blockquote containing three paragraphs is one block, it gets removed as a unit. If it's three blocks, they get removed individually. These produce different output. This decision is load-bearing and currently unspecified.

*Smallest test:* run `_parse_segment` on a body containing a bullet list and inspect the returned block list. Make the decision explicit in the design.

---

**R4. `pygments.get_lexer_by_name` failure modes**

Info strings in real-world documents include: `python3`, `py`, `js`, `tsx`, `sh`, `bash`, `console`, `output`, `text`, `diff`, `patch`, `yaml`, `json5`, `http`. Some of these have `pygments` aliases; many don't. The design says unknown info strings should be labelled `"Code"` (same as unannotated) — but this isn't stated in the design doc, only implied by requirements.

More critically: `get_lexer_by_name` raises `ClassNotFound` for unknown strings. If this exception isn't caught, it's a crash on any document with an unusual language tag. The fallback behavior needs an explicit try/except and should be tested against a real corpus.

*Smallest test:* pass `"output"`, `"console"`, `"text"`, `"diff"` through `get_lexer_by_name` and verify the exception handling path produces `"Code"`.

---

## Medium Risk — Fiddly bits requiring care

**R5. `trivial_extension_threshold` units are ambiguous** ✅ Resolved

All thresholds, including `trivial_extension_threshold`, are in tokens. The inline classification condition now uses `measurer.measure()` for both sides: `measurer.measure(body) <= measurer.measure(first_paragraph) + args.trivial_extension_threshold`. Design updated.

---

**R6. DriverLoop infinite loop on unsplittable oversized files**

When `process_file` exhausts all reduction steps and the document still exceeds Soft Threshold, it writes link-only output and warns. The DriverLoop enqueues outputs that exceed Soft Threshold — but this file is above the threshold and `is_unsplittable` is `False` (it has headings and segments). So it gets re-queued. `process_file` runs again. Finds all segments already empty. Writes link-only again. Re-queued again. Infinite loop.

The DriverLoop needs a visited-paths set, or `process_file` needs a signal to the loop that re-processing would be futile. This isn't addressed in the design.

---

**R7. DriverLoop enqueue logic — measure in loop or rely on gate?** ✅ Resolved

DriverLoop enqueues all returned paths unconditionally. The coarse initial gate in `process_file` handles filtering — this is the single decision point. Design updated.

---

**R8. markdown-it-py line map fidelity for all block types**

The design relies on `token.map` to slice original source. This is documented for block-level tokens, but:
- Inline tokens (the content inside paragraphs) don't have maps
- HTML blocks: `html_block` tokens do have maps, but the content is opaque
- Tight vs. loose lists behave differently in the token stream

The assumption that "slice by line map = original bytes" needs to be verified, particularly for documents with Windows-style line endings or trailing whitespace that the parser may normalize.

*Smallest test:* parse a document containing a bullet list, a blockquote, an HTML comment, and a fenced code block; verify that concatenating all top-level block slices reconstructs the original exactly.

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
