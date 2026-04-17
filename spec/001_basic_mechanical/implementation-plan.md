# Implementation Plan — FIT Generator: Basic Mechanical Split

---

## File and Module Structure

```
forge/fit/
├── fit_generator.py          # Single-file implementation (CLI entry point)
└── tests/
    └── test_fit_generator.py # Full unit test suite
```

Single-file approach matches the "standalone script" intent from the requirements. No package structure needed. All classes, `process_file`, `_reduction_loop`, and `DriverLoop` live in `fit_generator.py`. The test file imports from it directly.

If the file grows unwieldy during implementation (>600 lines), consider a `fit/` package with `measurer.py`, `segment.py`, `document.py`, `writer.py`, `driver.py`, and `cli.py` — but start flat and split only under pressure.

**Dependencies (already installed):**
- `markdown-it-py` — block parsing and line maps
- `pygments` — code block language normalization

**No new dependencies needed.**

---

## Implementation Order

Build bottom-up: each class depends only on what's already written and tested.

### 1. `Measurer`

No dependencies. Pure function over strings. Write first — everything else uses it.

Key implementation detail: detection is `text.strip().startswith("```") and text.strip().endswith("```")`. Nothing more — no parsing, no counting fences. Mixed content (paragraph + code block) fails this check and uses the text ratio.

### 2. `Segment` (construction + properties)

Depends on `Measurer` (injected). Write the constructor, `is_inline`, `is_empty`, `measure()`, and `_had_paragraph`/`_had_code` flags first — before any mutating methods.

**The `_had_paragraph` and `_had_code` flags are set at construction time from the initial block list and never mutated.** This is a class-level invariant, not a derived property. Do not recompute them from `self.blocks` — that list shrinks during reduction.

### 3. `Segment.reduce()`

Depends on the constructor being solid. This is the most complex method — implement it in isolation with the block removal algorithm well-understood before touching `Document`.

See the "Block Removal Algorithm" section below for implementation traps.

### 4. `Segment.is_critical_reduce()`

Depends on `_had_paragraph`, `_had_code`, and the ability to predict what `reduce()` would do without calling it. Implement as a pure read: count non-code and code blocks in `self.blocks`, compare against what `reduce(threshold)` would consume. No mutation.

### 5. `Segment.demote_to_subdoc()` and `serialize_inline_component()`

Straightforward once the core is in place. `demote_to_subdoc` recomputes `_cached_tokens` from scratch (not delta-update). `serialize_inline_component` uses `measurer.measure(self.body)` — `body` is immutable, so this value is stable.

### 6. `Document._parse_segment()`

Static method. Depends on `markdown-it-py`. Write and test independently from `Document._parse` — it's called from two call sites (during `_parse` and from `_reduction_loop` at demotion). Get byte-identical reconstruction working first; everything else depends on it.

### 7. `Document._parse()`

The most complex method in the codebase. Build in stages matching the 7-step pipeline:

1. Segmentation target detection (heading scan)
2. Text segmentation (slice source into heading-delimited chunks)
3. Name generation (slug + deduplication + empty-slug fallback)
4. Inline/subdoc classification
5. Block splitting (delegate to `_parse_segment`)
6. Initial subdoc reduction
7. Construct and return segments

Each stage is independently testable via `Document._parse(text, measurer, args)` as a static method.

### 8. `Document` interface

`__iter__`, `names`, `measure()`, `is_satisfied()`, `is_unsplittable`. All thin once `_parse` works.

`measure()` adds per-subdoc link line overhead. Compute the link line string once per segment at `_parse` time and cache the `measurer.measure(link_line)` result. Do not recompute on every `doc.measure()` call.

### 9. `process_file` and `_reduction_loop`

Write `process_file` first (thin shell). Then `_reduction_loop` — the outer iteration, demotion check, scan pass, reduce pass, and threshold switch logic.

### 10. `Writer`, `DryRunWriter`, `WriterFactory`

Write last. Backup logic, root document assembly, subdoc file writes. `DryRunWriter` should print structured output — enough to verify what `Writer` would do without actually writing.

### 11. `DriverLoop` and CLI

BFS queue over paths. `argparse` CLI with the 8 config options from the requirements table. Enforce `min_segment_count >= 2` in the argument parser (before any file processing).

---

## Per-Component Implementation Notes

### Measurer

No surprises. Watch the fence detection: `text.strip().startswith("```")` — not `"` ``` python"` or any prefix variant. The fence must be at the very start of the stripped string. If a text block happens to start with a fence but doesn't end with one, it's text-ratio — that's correct.

---

### Segment — Construction

**`_cached_tokens`**: computed as `sum(measurer.measure(b) for b in blocks)` at construction. For inline segments, `blocks=[]` so `_cached_tokens = 0` — `measure()` uses `measurer.measure(body)` instead for inline. These are two separate code paths in `measure()`.

**Name slug algorithm:**
1. Strip the leading `#` characters and whitespace from the heading text
2. Replace runs of non-alphanumeric characters with `_`
3. Strip leading/trailing `_`
4. Collapse runs of `_` to single `_`
5. Encode to UTF-8, truncate to 200 bytes, decode back (be careful not to split a multi-byte character — truncate at the last valid codepoint boundary)
6. If result is empty → `heading_NN` (1-based, zero-padded to min 2 digits)
7. For ruled lines → `rule_NN`

**Deduplication:** maintain a `dict[str, int]` of seen names across the `_parse` call. First occurrence: use name as-is. Subsequent occurrences: append `_01`, `_02`, etc. (zero-padded, widening as needed). The counter tracks per-name — `Overview_01` and `Overview_02` both come from a base name of `Overview`.

---

### Segment.reduce() — Block Removal Algorithm

**The most trap-dense method in the codebase.**

**Early-stop semantics:** Check `_cached_tokens < threshold` after *each individual block removal*. Not after each step. Not after each language. After each block. Update `_cached_tokens` immediately after removal, before checking.

**Step 2 mechanics (trim priority code to one-per-language):**
- Process languages in reverse priority order (lowest priority first)
- For each language: remove all but the last instance *in reverse document order*
- "All but the last" means: find all blocks of that language, remove from the end backward until one remains
- Move to the next language only when all duplicates of the current language are exhausted
- Early-stop applies mid-language — you may stop with some duplicates still present if threshold is satisfied

The test R-05 fixture makes this concrete. Study it carefully: 3 json + 1 ts + 1 python, threshold=15. After removing json_C and json_B, the remaining count is still 30 (above 15). json_A is the last json — step 2 cannot remove it. Move to typescript (only one — skip). Move to python (only one — skip). Step 2 exhausted at 30 tokens. Fall through to step 3.

**Step 3 semantics:** Remove all-but-one of each priority language starting from lowest priority. This means `json_A` gets removed before `ts_A` before `python_A`. One block of the highest priority language (python) is preserved until step 5.

**Representing "remove all but last" vs "remove all":**
- Step 2: leaves one instance of each priority language
- Step 3: removes all lower-priority instances, leaves one of the highest only
- Step 4: removes non-code blocks until one remains (preserves the last)
- Step 5: removes the final code block (no preservation)
- Step 6: clears everything, returns 0

**Implementation tip:** work with `list` indices, remove in reverse order (pop from the end) to avoid index invalidation. Or build a new list — either works, but reverse-order removal is simpler to reason about.

---

### Segment.is_critical_reduce()

Do not simulate `reduce()`. Instead: count the blocks that *would* be removed at `threshold` by walking through the steps mentally. In practice, this means: given current `blocks` and `threshold`, determine whether the removal algorithm would eliminate all non-code blocks (when `_had_paragraph`) or all code blocks (when `_had_code`).

Simplest correct implementation: check whether the current `_cached_tokens` can fall below `threshold` by removing only non-critical blocks. If it can't, `is_critical_reduce` returns True. "Non-critical blocks" for the paragraph condition are the code blocks; for the code condition, the non-code blocks.

Watch the zero-block case: if `blocks == []`, return True whenever either flag is set (the segment is already past the critical point).

---

### Document._parse_segment() — Block Slicing

**This is where the `next_start` scheme lives. Get it exactly right.**

The `markdown-it-py` token stream: call `md.parse(text)` which gives a flat list of tokens. Block-level tokens have `token.map = [start_line, end_line]` (0-indexed, end exclusive). Paired structures (lists, blockquotes, tables) have matching open/close tokens — track nesting depth to find top-level boundaries.

**The `next_start` slice:**
```python
lines = text.split('\n')
blocks = []
top_level_ranges = [...]  # list of (start_line, end_line) for each top-level block

for i, (start, end) in enumerate(top_level_ranges):
    if i + 1 < len(top_level_ranges):
        next_start = top_level_ranges[i + 1][0]
    else:
        next_start = len(lines)
    block_text = '\n'.join(lines[start:next_start])
    blocks.append(block_text)
```

**Do not call `.strip()`, `.rstrip()`, or `.lstrip()` on block text after slicing.** The trailing newline is structural — it ensures that concatenating all blocks reproduces the original body exactly (test PS-03). Stripping it breaks reconstruction.

**Nesting depth tracking:** tokens like `bullet_list_open` increment depth, `bullet_list_close` decrement. Only add a block's range when depth transitions from 1 → 0 (closing a top-level block). Top-level ranges are determined from the open token's start line to the close token's end line.

For simple blocks (paragraph, fence, hr, html_block, heading), they appear as a single token (or open/inline/close triplet) without nested pairs — these are always top-level when encountered at depth 0.

---

### Document._parse() — Segmentation Target Detection

Walk the token stream looking for `heading_open` tokens. Extract the level from `token.tag` (`"h1"` → 1, etc.). For ruled lines, look for `hr` tokens.

Search order: H1 through H6, then ruled lines. At each candidate level, count: (number of headings at this level) + (number of headings at all levels *above* this level). If that count ≥ `min_segment_count`, this is the target. The test DP-06 illustrates: 1 H1 + 2 H2 → target is H2 with count=3.

If no level qualifies, use the lowest level found (deepest heading that appears at least once) and warn. If no headings or rules at all, return a single segment covering the full document and warn.

---

### Document._parse() — Inline Classification

Two conditions, either is sufficient for inline:
1. `measurer.measure(body) < args.inline_threshold`
2. `measurer.measure(body) <= measurer.measure(first_paragraph) + args.trivial_extension_threshold`

"First paragraph" is the first non-heading, non-blank block in the segment body. Use the token stream to find it: the first `paragraph_open` token after the heading.

If a segment has no paragraphs (code-only segment), the trivial extension condition cannot apply — only the threshold condition matters.

---

### Reduction Loop — Threshold Switch

The Hard Threshold switch is one-way and permanent. Use a local variable `current_threshold` initialized to `args.soft_threshold`. Switch to `args.hard_threshold` on the first positive `is_critical_reduce` result, and never switch back. Use a boolean flag `hard_threshold_adopted` to suppress the scan pass in subsequent iterations.

**After threshold switch:** re-check `doc.is_satisfied(args.hard_threshold)` immediately. If already satisfied at the hard threshold, write and return without further reduction.

**Demotion check** runs at the start of each outer iteration before scan and reduce passes. Any inline segment whose `measurer.measure(segment.body) > current_inline_threshold` gets demoted. After demotion, the segment participates in the reduce pass for that same iteration.

`current_inline_threshold` starts at `args.inline_threshold` and decrements by `args.inline_threshold_reduction_increment` each outer iteration. The demotion check uses the *new* (decremented) threshold.

---

### Writer — Backup Ordering

Backup must be written *first*, before any other file operation. If `docs/overview.md` is the source, write `docs/overview.unfit.md` before writing `docs/overview.md` (the rewritten root) or any subdoc. If the backup already exists (re-run), overwrite it.

Subdocs go to `<source_stem>/` — i.e., `source_path.parent / source_path.stem / segment.name + ".md"`. Create the directory if it doesn't exist.

Return value: list of `Path` objects for all subdoc files written (not the root, not the backup). These are fed back into the `DriverLoop` queue.

---

## Test Scaffolding

**Single file:** `tests/test_fit_generator.py`. Import all classes directly from `fit_generator`.

**Structure:** one `pytest` class per tested class, with test methods named after the test IDs from tests.md (e.g. `test_M01_plain_text`, `test_S01_name_slug`). This makes test IDs traceable to the spec.

**Shared fixtures (at module level or via `pytest.fixture`):**

```python
@pytest.fixture
def measurer():
    return Measurer()

@pytest.fixture
def default_args():
    """argparse Namespace with all defaults from the requirements table."""
    return argparse.Namespace(
        soft_threshold=3000,
        hard_threshold=5000,
        inline_threshold=600,
        inline_threshold_reduction_increment=100,
        trivial_extension_threshold=25,
        min_segment_count=3,
        inline_languages=["python", "javascript", "typescript"],
        dry_run=False,
    )

@pytest.fixture
def small_args(default_args):
    """Tight thresholds useful for reduction loop and Writer tests."""
    default_args.inline_threshold = 100
    default_args.soft_threshold = 200
    default_args.hard_threshold = 400
    return default_args
```

**Document construction helpers:** many tests construct a `Document` from a string. Write a `make_doc(text, args, measurer)` helper that calls `Document._parse(text, measurer, args)` and returns the result as a list. This avoids building full markdown strings for every test.

**Segment construction helper:** for low-level `Segment` tests (reduce, is_critical_reduce), construct segments directly without going through `Document._parse`. Write a `make_segment(blocks, measurer, is_inline=False, heading="## Test", body=None)` helper that assembles a `Segment` from a list of raw strings.

**Block fixture factory:** the reduction algorithm tests need blocks with controlled token counts. Write `make_block(chars, lang=None)` that returns either `"x" * chars` (prose) or `` f"```{lang}\n{'x' * chars}\n```" `` (code). Pair with `Measurer` to verify expected token counts before using in tests.

**Writer tests use `tmp_path` (built-in pytest fixture):** write source files to `tmp_path`, run `Writer.write(doc, tmp_path / "source.md")`, assert on filesystem state.

---

## Integration Milestones

Build toward end-to-end in this order:

### Milestone 1 — Measure and Reconstruct
`Measurer` + `Document._parse_segment()` working. Verify byte-identical block reconstruction on a real document from `doc/anthropic/`. This proves the `next_start` slicing scheme before anything depends on it.

### Milestone 2 — Parse a Real Document
`Document._parse()` working. Point it at a mid-sized document (e.g. `doc/anthropic/build-with-claude/tool-use/overview.md` at ~2137 tokens). Verify: segmentation target selected correctly, segment names are sane, inline/subdoc classification matches expectations. No reduction yet.

### Milestone 3 — Single-File Dry Run
`process_file` + `_reduction_loop` + `DryRunWriter`. Run on a document that needs splitting, check that the dry-run output describes a plausible split. No filesystem writes.

### Milestone 4 — Single-File Write
Swap in `Writer`. Run on a real document that needs splitting. Verify: backup written, root document contains inline segments verbatim and subdoc links, subdoc files exist with correct content, concatenating subdoc bodies reproduces the original sections.

### Milestone 5 — Baseline Regression
Run the full tool against the 5 baseline documents from `tests/baseline-implementation.md`. Verify all "strictly better" criteria. This is the acceptance gate.

---

## Known Risks and Implementation Traps

### 1. `next_start` slicing and nesting depth
The most likely source of incorrect block boundaries. Test `_parse_segment` on bodies with nested structures (blockquote > paragraph, list > list, table with inline code) before relying on it. The byte-identical reconstruction test (PS-03) is the canary — run it on every non-trivial body during development.

Token stream nesting: `markdown-it-py` uses matched open/close tokens for container blocks. Track depth explicitly. A common mistake is treating `heading_open`/`heading_close` pairs as containers — they're not (the inline content lives in an `inline` token between them, but heading depth tracking uses the heading level tag, not nesting). Only structural containers (lists, blockquotes, tables) contribute to block depth.

### 2. `_had_paragraph` / `_had_code` mutated inadvertently
These must be set once at construction and never touched again. Any code path that inspects `self.blocks` to decide on these flags is wrong — by the time `reduce()` has run, the block list no longer reflects original state. Set from the initial block list, store as instance variables, done.

### 3. `reduce()` step 2 off-by-one: "all but the last"
The condition is "remove all but the last instance of that language." "Last" means highest document order index. Remove from the end backward. It is easy to accidentally remove the last instance when iterating — use `len(instances_of_lang) > 1` as the guard before each removal.

### 4. Early-stop fires at the wrong granularity
Early-stop must check `_cached_tokens < threshold` after *each individual block removal*, inside the innermost loop. Checking only after a full step or language pass will over-reduce. The tests R-03 and R-05a specifically target this — make them pass before moving on.

### 5. `_cached_tokens` recomputed instead of delta-updated
After block removal, subtract `measurer.measure(removed_block)` from `_cached_tokens`. Do not re-sum all blocks. The whole point of caching is to avoid re-measuring the surviving blocks. The only place full recomputation is correct is `demote_to_subdoc()`.

### 6. `is_critical_reduce` simulates `reduce()` incorrectly
The scan pass must detect critical conditions *before* mutation. If `is_critical_reduce` calls `reduce()` internally (even on a copy), the implementation is wrong. Derive the answer from the current block list and `_had_*` flags only. The implementation is a count-based check, not a simulation.

### 7. Segmentation target: "count at-or-above" vs "count at exactly"
Test DP-06 is the key case: 1 H1 + 2 H2. The candidate level is H2. The count includes H1 (which is above H2). If the implementation counts only H2 headings, it gets 2 ≥ 3? No → falls through incorrectly. The correct count is (H1 count) + (H2 count) = 3 ≥ 3 → target is H2.

### 8. Name slug: UTF-8 truncation at non-boundary
If the slug ends in a multi-byte character (e.g. Japanese text), truncating at byte 200 may split a character. After `.encode("utf-8")[:200]`, call `.decode("utf-8", errors="ignore")` to drop the partial final character cleanly.

### 9. Hard Threshold switch: re-check satisfaction immediately
After switching to `hard_threshold`, re-check `doc.is_satisfied(hard_threshold)` before running the reduce pass. Some documents are already satisfied at the hard threshold without further reduction — not re-checking wastes a loop iteration and may reduce unnecessarily.

### 10. `process_file` is_root parameter
The current design signature includes `is_root=False`. Its purpose is not yet defined in the design — do not use it to gate any current behavior. Leave it as a no-op parameter for now; document that it's a placeholder for future use (e.g. recursive descent tracking, different warning behavior at the root level).

### 11. `DryRunWriter` return value
`DryRunWriter.write()` must return a list of `Path` objects following the same schema as `Writer.write()` — even though no files are created. The `DriverLoop` feeds return values back into the queue. If `DryRunWriter` returns `[]` or `None`, the driver loop won't recurse — correct for dry-run semantics, but make this explicit and tested (W-06).

### 12. `markdown-it-py` API version
Confirm the API before writing parsing code:
```python
from markdown_it import MarkdownIt
md = MarkdownIt()
tokens = md.parse(text)
```
`token.map` is present for block tokens. Not all token types have a map — `inline` tokens do not. Hedge with `if token.map:` guards when walking the token stream.
