# Tests — FIT Generator: Basic Mechanical Split

## Baseline Implementation

### "Strictly Better" Criteria

The new tool must satisfy all of the following on every baseline test document:

1. **No splits on sub-target documents.** Any input already within the token target (≤3k tokens) must be left entirely unchanged. (`tool-use/overview.md` at ~2,137 tokens is the test case — fit_split.py incorrectly split it.)
2. **No output document exceeds 5k tokens.** Hard ceiling, can only be breached when the document is unsplittable (too few headings to meet min_segment_count)
3. **No output document exceeds 3k tokens** unless is_critical_reduce() applies (reducing further would destroy the last paragraph or code block) or the document is unsplittable.
4. **Root documents remain within target** for all 5 baseline inputs.
5. **`prompt-caching-examples.md` is split into multiple subdocs** with language-identified names (e.g. `python-01.md`, `typescript-01.md`), all under 3k tokens. DON'T LOAD THIS DOCUMENT INTO CONTEXT. IT IS TOO LARGE. ASK FOR HELP AND MAKE A PLAN INSTEAD.


→ [tests/baseline-implementation.md](tests/baseline-implementation.md) (~1,229 tokens)

---

## Unit Tests

### Measurer

**M-01 — Plain text token estimate**
- Class: `Measurer`
- Method: `measure(text: str) -> int`
- Fixture: `text = "a" * 400` (400 chars, no code fences)
- Expected: `100` (400 ÷ 4)

**M-02 — Code block token estimate**
- Class: `Measurer`
- Method: `measure(text: str) -> int`
- Fixture: `text = "```python\n" + "x" * 350 + "\n```"` (contains opening and closing three-backtick fence)
- Expected: `100` (350 chars ÷ 3.5 = 100; fence chars are included in the input but the estimate uses chars ÷ 3.5 for the full string when detected as code)
- Note: Detection is via three-backtick fence at start and end of string after stripping. A string that starts with ` ``` ` (after strip) and ends with ` ``` ` (after strip) is treated as code.

**M-03 — Mixed content uses text ratio**
- Class: `Measurer`
- Method: `measure(text: str) -> int`
- Fixture: `text = "Some prose.\n\n```python\nx = 1\n```\n\nMore prose."` (does not start and end with a fence after stripping)
- Expected: `len(text) // 4` (text ratio, because the whole string is not a code block)

**M-04 — Empty string**
- Class: `Measurer`
- Method: `measure(text: str) -> int`
- Fixture: `text = ""`
- Expected: `0`

**M-05 — Bare fence (open only, no close)**
- Class: `Measurer`
- Method: `measure(text: str) -> int`
- Fixture: `text = "```python\nsome code\n"` (starts with fence after strip, does not end with fence after strip)
- Expected: `len(text) // 4` (text ratio — fence must appear at both start and end after stripping)

---

### Segment — Construction and Basic Properties

**S-01 — Name slug: spaces and punctuation → underscores, collapsed**
- Class: `Segment`
- Fixture: heading `"## Hello, World! — A Test"`, constructed via `Document._parse`
- Expected: `segment.name == "Hello_World_A_Test"`
- Note: punctuation removed, runs of separators collapsed to single `_`

**S-02 — Name slug: heading that slugifies to empty string → `heading_NN`**
- Class: `Segment`
- Fixture: heading `"## ---"` (only punctuation), first such heading in the document
- Expected: `segment.name == "heading_01"`

**S-03 — Name slug: ruled line → `rule_NN`**
- Class: `Segment`
- Fixture: document contains a ruled line (`---`) as a segment boundary (segmentation target is ruled lines)
- Expected: `segment.name == "rule_01"` for the first ruled-line segment

**S-04 — Name slug: duplicate names suffixed with zero-padded integer**
- Class: `Segment` (via `Document._parse`)
- Fixture: document with two H2 headings both reading `"## Overview"`
- Expected: first segment `name == "Overview"`, second segment `name == "Overview_01"`

**S-05 — Name slug: truncated to 200 bytes (UTF-8)**
- Class: `Segment` (via `Document._parse`)
- Fixture: heading whose text slugifies to a string longer than 200 bytes
- Expected: `len(segment.name.encode("utf-8")) <= 200`

**S-06 — Inline segment: `is_inline = True`, `blocks = []`**
- Class: `Segment` (via `Document._parse`)
- Fixture: document with one H2 segment whose body is 10 tokens (well below inline_threshold=100)
- Expected: `segment.is_inline == True`, `segment.blocks == []`

**S-07 — Subdoc segment: `is_inline = False`, blocks populated**
- Class: `Segment` (via `Document._parse`)
- Fixture: document with one H2 segment whose body is 500 tokens (above inline_threshold=100)
- Expected: `segment.is_inline == False`, `len(segment.blocks) > 0`

**S-08 — `_had_paragraph` and `_had_code` set at construction, reflect original state**
- Class: `Segment`
- Fixture: segment constructed with blocks `["some prose", "```python\nx=1\n```"]`
- Expected: `segment._had_paragraph == True`, `segment._had_code == True`
- Additional: after calling `segment.reduce(0)` (which empties blocks), `_had_paragraph` and `_had_code` remain `True`

---

### Segment.measure()

**SM-01 — Inline segment: measure() delegates to measurer.measure(body)**
- Class: `Segment`
- Method: `measure() -> int`
- Fixture: inline segment with `body = "a" * 400`, `measurer = Measurer()`
- Expected: `segment.measure() == 100` (400 ÷ 4)
- Constraint: `len()` must not be called directly on body; measurement goes through `measurer.measure()`

**SM-02 — Subdoc segment: measure() returns _cached_tokens**
- Class: `Segment`
- Method: `measure() -> int`
- Fixture: subdoc segment constructed with two blocks of 40 chars each (text, no code); each block → 10 tokens
- Expected: `segment.measure() == 20` (`_cached_tokens`, not a fresh call to `measurer.measure(body)`)

**SM-03 — _cached_tokens updated after reduce(), not recomputed from body**
- Class: `Segment`
- Method: `reduce(threshold) -> int`
- Fixture: subdoc segment with two non-code blocks, each 40 chars (10 tokens each); `_cached_tokens = 20`
- Action: `segment.reduce(threshold=15)` — removes one block (10 tokens removed)
- Expected: `segment.measure() == 10`, `len(segment.blocks) == 1`

---

### Segment.is_empty

**SE-01 — is_empty True when blocks list is empty**
- Class: `Segment`
- Property: `is_empty`
- Fixture: subdoc segment with `blocks = []`
- Expected: `segment.is_empty == True`

**SE-02 — is_empty False when blocks list is non-empty**
- Class: `Segment`
- Property: `is_empty`
- Fixture: subdoc segment with one block
- Expected: `segment.is_empty == False`

**SE-03 — is_empty True after reduce empties the segment**
- Class: `Segment`
- Fixture: subdoc segment with one non-code block; call `segment.reduce(0)`
- Expected: `segment.is_empty == True`

---

### Segment.is_critical_reduce()

**IC-01 — Returns False when segment never had a paragraph (no non-code blocks)**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: segment constructed with only code blocks (`_had_paragraph = False`, `_had_code = True`)
- Expected: `is_critical_reduce(threshold)` returns `False` for the paragraph condition (only code-loss check applies)

**IC-02 — Returns True when reducing would remove the last non-code block**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: segment with `_had_paragraph = True`, currently has one non-code block and two code blocks; threshold is set such that reduce() would remove the last non-code block
- Expected: `segment.is_critical_reduce(threshold) == True`

**IC-03 — Returns False when non-code blocks would survive the threshold**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: segment with `_had_paragraph = True`, three non-code blocks; threshold removes at most one
- Expected: `segment.is_critical_reduce(threshold) == False`

**IC-04 — Returns True when reducing would remove the last code block**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: segment with `_had_code = True`, currently has one code block; threshold is set such that reduce() would remove it
- Expected: `segment.is_critical_reduce(threshold) == True`

**IC-05 — Returns True for already-empty segment when either flag is set**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: segment with `_had_paragraph = True`, `blocks = []`
- Expected: `segment.is_critical_reduce(any_threshold) == True`

**IC-06 — Does not mutate state**
- Class: `Segment`
- Method: `is_critical_reduce(threshold: int) -> bool`
- Fixture: subdoc segment with two non-code blocks
- Action: call `is_critical_reduce(threshold)` where threshold would require block removal
- Expected: `segment.blocks` unchanged, `segment._cached_tokens` unchanged after the call

---

### Segment.reduce()

**R-01 — No-op when already empty**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: subdoc segment with `blocks = []`
- Expected: returns `0`, blocks remain `[]`, no exception raised

**R-02 — Threshold zero empties segment immediately**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: subdoc segment with two non-code blocks
- Expected: `reduce(0)` returns `0`, `blocks == []`

**R-03 — Stops as soon as token count falls below threshold**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: three non-code blocks of 10 tokens each (30 total); threshold = 25
- Expected: one block removed (20 tokens remain < 25), `reduce()` returns `20`, `len(blocks) == 2`

**R-04 — Block removal order: non-priority code blocks first, reverse document order**
- Class: `Segment`
- Method: `reduce(threshold: int, priority_languages: list[str]) -> int`
- Fixture: blocks in order: `[prose_A, code_ruby, prose_B, code_python]`; `priority_languages = ["python"]`; threshold requires removing one block
- Expected: `code_ruby` is removed first (non-priority code, last in document order among non-priority code blocks)

**R-05 — Step 2: Exhausts all duplicates of lowest-priority language before moving up**
- Class: `Segment`
- Method: `reduce(threshold: int, priority_languages: list[str]) -> int`
- Fixture: `priority_languages = ["python", "typescript", "json"]`; blocks: `[json_A (10 tok), json_B (10 tok), json_C (10 tok), ts_A (10 tok), python_A (10 tok)]`; `_cached_tokens = 50`; threshold = 15 (requires removing 3 blocks to satisfy, all from json)
- Expected: `json_C` removed first (last json in document order), then `json_B`, leaving `[json_A, ts_A, python_A]` at 30 tokens; threshold not yet satisfied; `json_A` is the last remaining json block — step 2 does not remove it (that would be step 3 territory); move to `typescript`: `ts_A` is the only typescript block — skip (nothing to trim); move to `python`: same; threshold still not met after step 2 exhaustion — falls through to step 3
- Note: at 30 tokens with threshold=15, step 2 is exhausted without satisfying the threshold; the algorithm proceeds to step 3, which removes `json_A` (lowest remaining priority). After step 2, exactly `[json_A, ts_A, python_A]` remain.

**R-05a — Step 2 partial: stops mid-language trim when threshold satisfied**
- Class: `Segment`
- Method: `reduce(threshold: int, priority_languages: list[str]) -> int`
- Fixture: `priority_languages = ["python", "json"]`; blocks: `[json_A (10 tok), json_B (10 tok), python_A (10 tok)]`; `_cached_tokens = 30`; threshold = 25
- Expected: `json_B` removed (10 tok, drops to 20 < 25); returns `20`; `json_A` and `python_A` retained

**R-06 — Step 3: Remove priority code blocks in reverse priority order**
- Class: `Segment`
- Method: `reduce(threshold: int, priority_languages: list[str]) -> int`
- Fixture: `priority_languages = ["python", "json"]`; blocks: `[json_A, python_A, prose_A]`; threshold forces step 3 entry (step 1 and 2 exhausted — no non-priority code, no duplicate priority code)
- Expected: `json_A` removed before `python_A`

**R-07 — Step 4: Remove non-code blocks in reverse document order, preserving one**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: blocks `[prose_A, prose_B, prose_C, code_python]` (only code block is the last); threshold forces step 4 (all code handling exhausted)
- Expected: `prose_C` removed first, then `prose_B` if still above threshold; `prose_A` is the last non-code block and must not be removed in step 4

**R-08 — Step 5: Remove the final code block**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: one prose block and one code block remain after steps 1–4; threshold still not met
- Expected: the code block is removed in step 5; only the prose block remains

**R-09 — Step 6: Set blocks to [] and return 0 when nothing satisfies threshold**
- Class: `Segment`
- Method: `reduce(threshold: int) -> int`
- Fixture: single prose block of 50 tokens; threshold = 1 (unreachably low, forces exhaustion of all steps)
- Expected: returns `0`, `blocks == []`

**R-10 — Block text not stripped after slicing (next_start scheme)**
- Class: `Segment` (via `Document._parse_segment`)
- Constraint: Block text must never be stripped or trimmed after slicing
- Fixture: segment body with two blocks where the first block ends in a newline followed by a blank line before the second block
- Expected: `blocks[0]` ends with a newline (trailing newline preserved); concatenation of all blocks produces the original segment body exactly

---

### Segment.demote_to_subdoc()

**D-01 — Sets is_inline to False and populates blocks**
- Class: `Segment`
- Method: `demote_to_subdoc(blocks: list[str])`
- Fixture: inline segment; call `demote_to_subdoc(["block_A", "block_B"])`
- Expected: `segment.is_inline == False`, `segment.blocks == ["block_A", "block_B"]`

**D-02 — Recomputes _cached_tokens from the new blocks**
- Class: `Segment`
- Method: `demote_to_subdoc(blocks: list[str])`
- Fixture: inline segment (body-based measure would give X); call `demote_to_subdoc` with blocks whose total measure is Y ≠ X
- Expected: `segment._cached_tokens == Y`, `segment.measure() == Y`

---

### Segment.serialize_inline_component()

**SIC-01 — Returns heading + current blocks joined + subdoc link with token annotation**
- Class: `Segment`
- Method: `serialize_inline_component() -> str`
- Fixture: subdoc segment with `heading = "## Overview"`, two blocks `["block_A\n", "block_B\n"]`, `body` measures to 100 tokens
- Expected: output contains the heading, both blocks, and a link line of the form `[path/name.md](path/name.md) (~100 tokens)` (values from `measurer.measure(body)`)

**SIC-02 — Token annotation uses measurer.measure(body), which is stable across reduction**
- Class: `Segment`
- Method: `serialize_inline_component() -> str`
- Fixture: subdoc segment; call `reduce()` to remove blocks; then call `serialize_inline_component()`
- Expected: the `(~N tokens)` annotation reflects `measurer.measure(body)` (original body, immutable), not the post-reduction block count

---

### Document._parse() — Segmentation Target

**DP-01 — Selects H1 when two or more H1 headings exist (min_segment_count=2)**
- Class: `Document`
- Method: `_parse(text, measurer, args) -> list[Segment]`
- Fixture: document with 3 H1 headings and 5 H2 headings; `args.min_segment_count = 2`
- Expected: segmentation target is H1; exactly 3 segments returned

**DP-02 — Skips H1, selects H2 when only one H1 exists**
- Class: `Document`
- Method: `_parse`
- Fixture: document with 1 H1 and 4 H2s; `args.min_segment_count = 2`
- Expected: segmentation target is H2; returns segments for H1 + H2s (H1 content up to first H2 = first segment; each H2 = one segment; total ≥ 2)

**DP-03 — Uses lowest level found and warns when no level meets min_segment_count**
- Class: `Document`
- Method: `_parse`
- Fixture: document with exactly one H3 and no other headings; `args.min_segment_count = 3`
- Expected: warning emitted; segmentation proceeds at H3 level despite undershooting threshold

**DP-04 — Returns single segment and warns when no headings or rules exist**
- Class: `Document`
- Method: `_parse`
- Fixture: document with no headings and no ruled lines
- Expected: warning emitted; returns list of exactly one segment containing the full document body

**DP-05 — Ruled lines used when no headings meet threshold**
- Class: `Document`
- Method: `_parse`
- Fixture: document with no headings but 3 ruled lines (`---`); `args.min_segment_count = 2`
- Expected: 3+ segments returned; segment names follow `rule_NN` convention

**DP-06 — H1 is counted along with lower-level headings when checking a candidate level**
- Class: `Document`
- Method: `_parse`
- Fixture: document with 1 H1 and 2 H2s; `args.min_segment_count = 3`
- Expected: segmentation target is H2 (1 H1 + 2 H2 = 3 headings at-or-above H2); 3 segments returned

---

### Document._parse() — Inline/Subdoc Classification

**DC-01 — Segment below inline_threshold is classified inline**
- Class: `Document`
- Method: `_parse`
- Fixture: H2 segment with body measuring 50 tokens; `args.inline_threshold = 100`
- Expected: `segment.is_inline == True`

**DC-02 — Segment at or above inline_threshold is classified subdoc**
- Class: `Document`
- Method: `_parse`
- Fixture: H2 segment with body measuring 200 tokens; `args.inline_threshold = 100`
- Expected: `segment.is_inline == False`

**DC-03 — Trivial extension: segment with body ≤ first_paragraph + trivial_extension_threshold is inline**
- Class: `Document`
- Method: `_parse`
- Fixture: segment body where `measurer.measure(body) == measurer.measure(first_paragraph) + args.trivial_extension_threshold`; body is above inline_threshold
- Expected: `segment.is_inline == True` (trivial extension condition overrides threshold)

**DC-04 — Subdoc segment gets blocks populated; inline segment gets blocks=[]**
- Class: `Document`
- Method: `_parse`
- Fixture: document with one inline segment (small body) and one subdoc segment (large body)
- Expected: inline segment `blocks == []`; subdoc segment `len(blocks) > 0`

---

### Document._parse() — Initial Subdoc Reduction (Step 6)

**DR-01 — Initial reduce called on subdoc segments during _parse**
- Class: `Document`
- Method: `_parse` (step 6)
- Fixture: subdoc segment whose blocks total 300 tokens; `args.inline_threshold = 100`; `args.inline_languages = ["python"]`
- Expected: after `_parse`, `segment.measure() < 100` (inline component reduced below inline_threshold)

**DR-02 — Initial reduce does not affect inline segments**
- Class: `Document`
- Method: `_parse`
- Fixture: inline segment (small body)
- Expected: `segment.blocks == []` after `_parse`; `is_inline` unchanged

---

### Document — Interface

**DI-01 — __iter__ yields segments in document order**
- Class: `Document`
- Method: `__iter__`
- Fixture: document with 3 H2 sections in known order
- Expected: segments yielded in source document order (first heading → last heading)

**DI-02 — names property returns segment names in document order**
- Class: `Document`
- Property: `names`
- Fixture: document with 3 H2 sections named "A", "B", "C" (in order)
- Expected: `doc.names == ["A", "B", "C"]`

**DI-03 — measure() sums segment.measure() across segments plus subdoc link overhead**
- Class: `Document`
- Method: `measure() -> int`
- Fixture: two subdoc segments of 100 tokens each; link line for each measures to 10 tokens
- Expected: `doc.measure() == 220` (100 + 10 + 100 + 10)

**DI-04 — measure() does not add overhead for inline segments**
- Class: `Document`
- Method: `measure() -> int`
- Fixture: one inline segment of 50 tokens, one subdoc segment of 100 tokens + 10 tokens link overhead
- Expected: `doc.measure() == 160` (50 + 100 + 10; no link overhead on the inline segment)

**DI-05 — is_satisfied returns True when measure() ≤ threshold**
- Class: `Document`
- Method: `is_satisfied(threshold: int) -> bool`
- Fixture: `doc.measure() == 300`; `threshold = 300`
- Expected: `doc.is_satisfied(300) == True`

**DI-06 — is_satisfied returns False when measure() > threshold**
- Class: `Document`
- Method: `is_satisfied(threshold: int) -> bool`
- Fixture: `doc.measure() == 301`; `threshold = 300`
- Expected: `doc.is_satisfied(300) == False`

**DI-07 — is_unsplittable True when fewer than min_segment_count segments produced**
- Class: `Document`
- Property: `is_unsplittable`
- Fixture: document with no headings (yields 1 segment); `args.min_segment_count = 2`
- Expected: `doc.is_unsplittable == True`

**DI-08 — is_unsplittable False when segment count meets min_segment_count**
- Class: `Document`
- Property: `is_unsplittable`
- Fixture: document with 2 H2 headings; `args.min_segment_count = 2`
- Expected: `doc.is_unsplittable == False`

---

### Document._parse_segment()

**PS-01 — Splits body into top-level blocks**
- Class: `Document`
- Method: `_parse_segment(body: str) -> list[str]`
- Fixture: body with one paragraph, one fenced code block, one list
- Expected: returns a list of 3 strings, one per top-level block

**PS-02 — Nested content not surfaced as separate blocks**
- Class: `Document`
- Method: `_parse_segment`
- Fixture: body with one blockquote containing two paragraphs
- Expected: returns a list of 1 string (the whole blockquote as one block)

**PS-03 — Block concatenation reconstructs original body exactly**
- Class: `Document`
- Method: `_parse_segment`
- Fixture: any well-formed segment body
- Expected: `"".join(blocks) == body` — byte-identical reconstruction

---

### process_file — Initial Gate

**PF-01 — Skips file when raw measure ≤ soft_threshold**
- Function: `process_file`
- Fixture: file whose text measures ≤ `args.soft_threshold` (via `Measurer.measure(text)`)
- Expected: returns `[]`; no `Document` constructed; no files written

**PF-02 — Proceeds when raw measure > soft_threshold**
- Function: `process_file`
- Fixture: file whose text measures > `args.soft_threshold`
- Expected: `Document` is constructed; reduction loop entered (or `is_unsplittable` path taken)

**PF-03 — Skips reduction when is_unsplittable**
- Function: `process_file`
- Fixture: document with no headings; `args.min_segment_count = 2`
- Expected: warning logged; returns `[]`; no files written

---

### Reduction Loop

**RL-01 — Satisfied immediately after _parse: write and return without iterating**
- Function: `_reduction_loop`
- Fixture: document that is already satisfied at the initial threshold (all subdoc segments were reduced below inline_threshold in step 6)
- Expected: `doc.is_satisfied()` is checked first; writer called once; loop exits

**RL-02 — Inline→subdoc demotion fires at start of each outer iteration**
- Function: `_reduction_loop`
- Fixture: inline segment whose body just exceeds the decremented inline_threshold at iteration N
- Expected: at iteration N, before scan and reduce passes, `segment.demote_to_subdoc()` is called; segment participates in the reduce pass of that same iteration

**RL-03 — Scan pass triggers Hard Threshold switch when is_critical_reduce fires**
- Function: `_reduction_loop`
- Fixture: one segment where `is_critical_reduce(current_soft_threshold)` returns True; `args.hard_threshold < args.soft_threshold`
- Expected: threshold switches permanently to `hard_threshold`; re-measure happens at new threshold; scan is skipped for all subsequent iterations

**RL-04 — Scan pass skipped after Hard Threshold adoption**
- Function: `_reduction_loop`
- Fixture: same as RL-03; continue iterating after threshold switch
- Expected: no further calls to `is_critical_reduce` on any subsequent iteration

**RL-05 — Reduce pass skips inline and empty segments**
- Function: `_reduction_loop`
- Fixture: document with one inline segment and one empty subdoc segment and one non-empty subdoc segment
- Expected: `reduce()` called only on the non-empty subdoc segment

**RL-06 — Loop emits link-only warning when all segments empty and threshold not satisfied**
- Function: `_reduction_loop`
- Fixture: document where all segment blocks are emptied but `doc.measure()` still exceeds threshold (e.g. link overhead alone is over threshold — unlikely in practice but testable with a tiny hard_threshold)
- Expected: warning emitted; writer still called; returns output paths

---

### Writer

**W-01 — Backup written as <filename>.unfit.<ext> before any output**
- Class: `Writer`
- Method: `write(document, source_path)`
- Fixture: source_path = `docs/overview.md`
- Expected: `docs/overview.unfit.md` written before `docs/overview.md` and any subdoc files

**W-02 — Inline segment body written verbatim to root document**
- Class: `Writer`
- Method: `write`
- Fixture: document with one inline segment; body = `"# Title\n\nSome text.\n"`
- Expected: root document contains that exact string

**W-03 — Subdoc segment rendered via serialize_inline_component() in root document**
- Class: `Writer`
- Method: `write`
- Fixture: document with one subdoc segment
- Expected: root document contains the output of `segment.serialize_inline_component()`, not `segment.body`

**W-04 — Subdoc files written to <source_stem>/ directory**
- Class: `Writer`
- Method: `write`
- Fixture: `source_path = docs/overview.md`; one subdoc segment named `"installation"`
- Expected: `docs/overview/installation.md` written with `segment.body` as content

**W-05 — Returns list of new subdoc paths**
- Class: `Writer`
- Method: `write`
- Fixture: document with two subdoc segments
- Expected: return value is a list of two `Path` objects pointing to the created subdoc files

**W-06 — DryRunWriter prints planned actions without writing any files**
- Class: `DryRunWriter`
- Method: `write`
- Fixture: any document
- Expected: no files created; planned actions printed to stdout (or equivalent); return value follows same schema as `Writer.write`

---

### Document._parse_segment() — Block Slicing Constraint

**BS-01 — Block text is not stripped after slicing**
- Class: `Document`
- Method: `_parse_segment`
- Fixture: segment body:
  ```
  First paragraph.\n
  \n
  ```python\n
  x = 1\n
  ```\n
  ```
  (blank line between paragraph and code block)
- Expected: `blocks[0]` includes its trailing newline and the blank line up to `next_start`; `blocks[0]` is not `.strip()`-ed or `.rstrip()`-ed

**BS-02 — next_start scheme: last block runs to EOF**
- Class: `Document`
- Method: `_parse_segment`
- Fixture: segment body ending without a trailing newline
- Expected: `blocks[-1]` captures all content to end of file; no content dropped

---

### args.min_segment_count Lower Bound

**MC-01 — min_segment_count of 1 is rejected at startup**
- Scope: CLI / arg parsing
- Fixture: `--min-segment-count 1`
- Expected: error raised before any file processing begins; message indicates minimum is 2

**MC-02 — min_segment_count of 2 is accepted**
- Scope: CLI / arg parsing
- Fixture: `--min-segment-count 2`
- Expected: no error; processing proceeds normally
