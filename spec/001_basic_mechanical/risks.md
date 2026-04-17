# Risks — FIT Generator: Basic Mechanical Split

---

## High Risk — Load-bearing assumptions that haven't been verified

**R1. `_had_paragraph`/`_had_code` flags go stale after `_parse` initial reduction**

`_parse` step 6 calls `segment.reduce(inline_threshold)` *after* constructing each subdoc segment. The flags are set at construction from the full block list. If the initial reduce removes all non-code blocks from a segment, `_had_paragraph` is still `True`. Then on the reduction loop's first scan pass, `is_critical_reduce` checks "are there no non-code blocks remaining?" — there aren't (already removed) — so it returns `True` immediately and switches permanently to Hard Threshold before the loop has done anything. False positive, unnecessary Hard Threshold adoption.

*Smallest test that resolves it:* a document where a subdoc segment has only one non-code block and `inline_threshold` is high enough that the initial reduce removes it. Verify `is_critical_reduce` behavior before and after `_parse`.

*Fix candidate:* `_had_paragraph`/`_had_code` need to reflect current state, not original. Either set them after the initial reduce, or compute them lazily from the current block list.

---

**R2. `Document.measure()` link overhead is dynamic, not static**

The design says overhead is "computed once per segment from its name and path at construction time." But the link line is `[path/name.md](path/name.md) (~N tokens)` — and `N` is the subdoc token count, which changes throughout reduction. The static part (name, path) is fixed; the annotation isn't. Either:
- The annotation is computed from `segment.body` length (fixed — `body` never changes), making it a reasonable approximation that's stable, or
- It reflects `_cached_tokens` (accurate but changes each reduction step)

Which one is intended? If it's `len(body) // 4` (the `serialize_inline_component` formula), then the overhead is actually stable and the design is fine — but it should say that explicitly, not "computed from name and path."

*Smallest test:* measure two identical documents where one subdoc has had blocks removed. Verify `Document.measure()` changes vs. stays the same.

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

**R5. `trivial_extension_threshold` units are ambiguous**

The condition is `len(body) <= len(first_para) + trivial_extension_threshold`. `len()` is character count. The config table says the default is `25` and describes it in "tokens." 25 tokens ≈ 100 characters. If the comparison is character-based (as written), a threshold of 25 means 25 *characters* — very tight. If it should be 25 *tokens* (~100 chars), the implementation needs `trivial_extension_threshold * 4`. The requirements use "tokens" in the description but the formula as written uses raw `len()`. One of these is wrong.

---

**R6. DriverLoop infinite loop on unsplittable oversized files**

When `process_file` exhausts all reduction steps and the document still exceeds Soft Threshold, it writes link-only output and warns. The DriverLoop enqueues outputs that exceed Soft Threshold — but this file is above the threshold and `is_unsplittable` is `False` (it has headings and segments). So it gets re-queued. `process_file` runs again. Finds all segments already empty. Writes link-only again. Re-queued again. Infinite loop.

The DriverLoop needs a visited-paths set, or `process_file` needs a signal to the loop that re-processing would be futile. This isn't addressed in the design.

---

**R7. DriverLoop enqueue logic — measure in loop or rely on gate?**

The design says "any output path that exceeds the Soft Threshold is placed back on the queue." This implies DriverLoop measures each returned path before enqueuing. But `process_file` already has a gate that skips files below Soft Threshold. So DriverLoop could enqueue everything — the gate handles it. Which is it? If DriverLoop measures, it needs to instantiate a `Measurer` and read the file — redundant with `process_file`'s gate. If it enqueues everything, a large BFS run will process many small files unnecessarily. Needs a decision.

---

**R8. markdown-it-py line map fidelity for all block types**

The design relies on `token.map` to slice original source. This is documented for block-level tokens, but:
- Inline tokens (the content inside paragraphs) don't have maps
- HTML blocks: `html_block` tokens do have maps, but the content is opaque
- Tight vs. loose lists behave differently in the token stream

The assumption that "slice by line map = original bytes" needs to be verified, particularly for documents with Windows-style line endings or trailing whitespace that the parser may normalize.

*Smallest test:* parse a document containing a bullet list, a blockquote, an HTML comment, and a fenced code block; verify that concatenating all top-level block slices reconstructs the original exactly.

---

**R9. Segment name length — filesystem limits**

Long headings produce long slug names. Linux ext4 limit is 255 bytes per filename component. Unicode headings can produce multi-byte filenames. The current design has no truncation step.

Also: heading text that's *entirely* punctuation slugifies to an empty string. The design says this produces `heading_NN` — but this branch is only mentioned for "bare headings" (headings with no text at all). All-punctuation headings aren't "bare." Edge case.

---

## Low Risk — Edge cases worth a test but probably fine

**R10. `is_unsplittable` boundary**

`is_unsplittable` fires when `_parse` returns exactly one segment. But `_parse` also returns one segment if the document has exactly one heading at the target level and nothing above it. That's a valid (if degenerate) segmentation, not a no-headings failure. The warning emitted would be misleading. Consider checking for the no-headings condition explicitly (e.g., a flag from `_parse` rather than segment count).

**R11. `_parse_segment` re-parse fidelity**

When `_parse_segment` re-parses a segment body (during inline→subdoc demotion), it parses a fragment. Reference-style link definitions, footnotes, or other document-wide constructs defined elsewhere may not resolve correctly inside the fragment. Probably rare in practice, but worth noting for technical markdown documents.

**R12. Block removal when all blocks are already gone**

`reduce(threshold)` step 6 "sets blocks to `[]`, return 0" after exhausting all steps. Calling `reduce()` again on an already-empty segment should be a no-op (it returns 0 immediately). This is implied but not stated. The reduction loop calls `reduce()` on every subdoc segment every outer iteration — verify it handles the already-empty case without error.

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
