# Design — FIT Generator: Basic Mechanical Split

---

## Class Overview

```
Measurer
  └─► Segment (injected via Document constructor)
        └─► Document (owns list of Segments)
              └─► process_file (external; iterates Document)
                    └─► Writer (factory-created)
                          └─► DriverLoop (queue of paths)
```

---

## Core Classes

### Measurer

Single responsibility: estimate token count from a string.

- `measure(text: str) -> int` — detects code blocks internally.
  - `chars ÷ 4` for text
  - `chars ÷ 3.5` for code blocks (detected via three-backtick fence at start and end of string after stripping)

Constants are class-level, making the estimation model swappable (e.g. replace with an exact tokenizer) without touching anything else. Injected into `Document`; `Document` passes it down to each `Segment`.

---

### Segment

The backbone of the design. Encapsulates a single named section of the document — its content, inline/subdoc state, cached token count, and reduction behavior.

**Construction:** `Segment(name, heading, body, blocks, measurer, is_inline)`

- `name: str` — slug key, used as filename stem for subdocs. Heading-derived: spaces and punctuation → `_`, collapsed. Bare headings → `heading_NN` (1-based index, zero-padded min 2 digits). Ruled lines → `rule_NN`. Duplicates suffixed with zero-padded integer starting at `01`.
- `heading: str` — raw heading or ruled line that partitions this segment (included verbatim in `body`)
- `body: str` — full content for disk write (heading included); also used by inline segments for `measure()` and `serialize_inline_component()`
- `blocks: list[str]` — raw content blocks in document order (for subdoc segments); empty for inline segments
- `_cached_tokens: int` — cached sum of `measurer.measure()` over current blocks. Updated after each block removal in `reduce()`. Never recomputed from scratch except on `demote_to_subdoc()`.
- `is_inline: bool` — True if segment body is rendered verbatim in the root doc; False if replaced by heading + inline component + subdoc link
- `_had_paragraph: bool` — class-level flag set at construction. True if the original block list contained at least one non-code block. (Name uses "paragraph" loosely — means any non-code block.) Used by `is_critical_reduce()`.
- `_had_code: bool` — class-level flag set at construction. True if the original block list contained at least one code block. Used by `is_critical_reduce()`.

**Key methods:**

- `measure() -> int` — returns `_cached_tokens` for subdoc segments; `measurer.measure(body)` for inline segments.

- `is_critical_reduce(threshold: int) -> bool` — returns True if reducing at this threshold would result in no non-code blocks remaining (when `_had_paragraph` is True) or no code blocks remaining (when `_had_code` is True). Does not mutate state. The flags prevent false positives from segments that never had both block types. Returns True for zero-block segments when either flag is set — a segment already emptied is already past the critical point. `is_critical_reduce = (self._had_paragraph and no_noncoded_blocks_remain) or (self._had_code and no_code_blocks_remain)`. Used by the outer loop's scan pass to detect Hard Threshold conditions before mutation occurs.

- `reduce(threshold: int, priority_languages: list[str] = None) -> int` — removes blocks per the priority algorithm, checking `_cached_tokens` against `threshold` after each removal and stopping as soon as the token count falls below `threshold`. Updates `_cached_tokens` after each removal. Returns `_cached_tokens`. Returns 0 (and sets blocks to `[]`) if threshold is zero.

- `demote_to_subdoc(blocks: list[str])` — transitions an inline segment to subdoc status. Sets `is_inline = False`, sets `blocks`, recomputes `_cached_tokens` from scratch. Caller passes `Document._parse_segment(segment.body)` to produce the block list.

- `serialize_inline_component() -> str` — returns the heading + inline component (current blocks joined) + subdoc link with `(~N tokens)` annotation, where N is `len(body) // 4`. Used by Writer to assemble the root document.

**Block removal algorithm:**

After each block removal, check `_cached_tokens` against `threshold`; stop and return as soon as the count falls below threshold. If the count never drops below threshold after exhausting all removal steps, return 0 and set blocks to `[]`.

Removal steps in order:
1. Remove non-priority code blocks in reverse document order
2. Trim priority code blocks to one of each priority type, in reverse priority order then reverse document order (e.g. for `['python', 'typescript', 'json']`: trim `json` instances to one, then `typescript` to one, then `python` to one)
3. Remove priority code blocks in reverse priority order until only the highest-priority type remains
4. Remove non-code blocks in reverse document order until one non-code block remains
5. Remove the final code block
6. Set blocks to `[]`, return 0

---

### Document

Structured container for an ordered collection of Segments. Handles parsing, segmentation target detection, name generation, inline/subdoc classification, and the document-level `measure` cascade.

**Construction:** `Document(text: str, measurer: Measurer, args)`

Calls `Document._parse(text, measurer, args)` internally and assigns the result. `_parse` is a static method (Python's alternative to constructor overloading) that returns a list of `Segment` objects. It can be called independently for testing.

**`Document._parse(text, measurer, args) -> list[Segment]`** — static method. Full parsing pipeline:

1. **Segmentation Target:** Scan the token stream for heading levels (H1–H6) and ruled lines. Search in order H1 → H2 → H3 → H4 → H5 → H6 → ruled lines. At each level, count headings at that level plus all levels above. Return the first level where that count ≥ `args.min_segment_count`. If no level meets the threshold, use the lowest level found and warn. If no headings or rules exist: warn and return a single segment containing the full document (no split possible).

2. **Segmentation:** Partition the document into segments at the target level (and all levels above it). Each heading at or above the target level begins a new segment. The content between two consecutive such headings (exclusive of the heading line itself) is the segment body.

3. **Name generation:** For each segment, derive a name from its heading text (slug: spaces and punctuation → `_`, collapse runs). Bare headings (e.g. `##` with no text) → `heading_NN`. Ruled lines → `rule_NN`. Track duplicates across the document; suffix with zero-padded integer starting at `01` (widen as needed). The name generator is stateful per `_parse` call and resets between documents.

4. **Inline/subdoc classification:** A segment is initially inline if either condition holds:
   - Token count < `args.inline_threshold`
   - `len(body) <= len(first_paragraph) + args.trivial_extension_threshold` (single paragraph plus a little)
   Inline segments get `blocks=[]` and `is_inline=True`. Subdoc segments get their body split into blocks and `is_inline=False`.

5. **Block splitting:** For subdoc segments, split the body into blocks using the markdown parser. All block types are included in document order; only code blocks receive special treatment in the reduction algorithm.

6. **Initial subdoc reduction:** For each subdoc segment, call `segment.reduce(args.inline_threshold, args.inline_languages)` to trim the inline component below the Inline Threshold before the document-level reduction loop begins.

7. **Construct and return** a list of `Segment` objects in document order, with `measurer` injected into each.

**`Document._parse_segment(body: str) -> list[str]`** — static method. Splits a segment body string into an ordered list of blocks. Extracted from `_parse` step 5 for reuse at the inline→subdoc demotion call site. All block types returned by the markdown parser are included; only code blocks receive special treatment elsewhere in the pipeline.

**Interface:**

- `__iter__` — yields `Segment` objects in document order
- `names` — property returning segment names in document order (for Writer and external consumers)
- `measure() -> int` — sums `segment.measure()` across all segments, plus a per-subdoc-segment overhead for the inline component link line. The link line format follows the FIT standard: `[path/name.md](path/name.md) (~N tokens)` preceded by a heading; overhead is estimated at `len(link_line) // 4` tokens, computed once per segment from its name and path at construction time.
- `is_satisfied(threshold: int) -> bool` — `self.measure() <= threshold`
- `is_unsplittable` — property. Returns `True` if `_parse` produced exactly one segment (the no-headings fallback case). Used by `process_file` to skip the reduction loop and emit a warning instead of attempting reduction on an unsegmentable document.

---

### Writer (Factory Pattern)

`WriterFactory.create(args) -> Writer` — returns a `Writer` or `DryRunWriter` based on `args.dry_run`.

Both implement the same interface:

- `write(document: Document, source_path: Path) -> list[Path]`
  - **Backup:** writes `<filename>.unfit.<ext>` once before any output, at root level only
  - **Root document:** assembled from `Document` iterator in order. Inline segments: body verbatim. Subdoc segments: `segment.serialize_inline_component()`.
  - **Subdoc files:** written to `<source_stem>/` directory; content from `segment.body`
  - Returns list of new subdoc paths created

`DryRunWriter` — prints planned actions without writing. Independently testable.

---

## process_file and Reduction Loop

`process_file` is thin: initial gate, construct objects, hand off to reduction loop and writer.

```python
def process_file(path, args, is_root=False):
    text = path.read_text()
    measurer = Measurer()

    # Coarse initial gate — operates on raw unstructured text, intentionally
    if measurer.measure(text) <= args.soft_threshold:
        log("fits, skipping")
        return []

    doc = Document(text, measurer, args)  # parsing + base segmentation

    if doc.is_unsplittable:
        log("warning: no headings found, cannot split")
        return []

    writer = WriterFactory.create(args)
    return _reduction_loop(doc, args, writer, path)
```

### Reduction Loop

Lives outside `Document`. Outer loop decrements the Inline Threshold by `args.inline_threshold_reduction_increment` each iteration. Inside each iteration, two sequential passes over the Document iterator:

**Pass 1 — Scan** (runs only while still on Soft Threshold):
```
for segment in doc:
    if segment.is_critical_reduce(current_inline_threshold):
        switch permanently to Hard Threshold
        re-measure doc at new threshold
        break
```
Once Hard Threshold is adopted, this scan is skipped for all subsequent iterations.

**Pass 2 — Reduce:**
```
for segment in doc:
    if not segment.is_inline:
        segment.reduce(current_inline_threshold, args.inline_languages)
```

After each full reduce pass: check `doc.is_satisfied(current_threshold)`. If satisfied, write and return. If all segments are link-only (empty block lists) and still unsatisfied, write link-only and warn.

**Inline→subdoc demotion:** At the start of each outer iteration, before the scan and reduce passes, check all inline segments. Any inline segment whose body now exceeds the new (decremented) Inline Threshold is demoted: call `segment.demote_to_subdoc(Document._parse_segment(segment.body))` to split its body into blocks and mark it as subdoc.

---

## Interaction Flow

```
CLI args
  └─► DriverLoop (BFS queue of file paths)
        └─► process_file(path, args, is_root)
              ├─► Measurer.measure(text)         (coarse initial gate)
              ├─► Document(text, measurer, args)
              │     └─► Document._parse(...)
              │           ├─► Segmentation Target detection
              │           ├─► Name generation
              │           ├─► Inline/subdoc classification
              │           ├─► Block splitting
              │           └─► Segment × N (measurer injected into each)
              ├─► _reduction_loop(doc, args)
              │     ├─► Inline→subdoc demotion check (each outer iteration)
              │     ├─► Pass 1: segment.is_critical_reduce() → threshold switch
              │     └─► Pass 2: segment.reduce() → _cached_tokens updated
              └─► WriterFactory.create(args).write(doc, path)
                    └─► new subdoc paths → DriverLoop queue
```

**DriverLoop** maintains a BFS queue of file paths. Feeds each through `process_file`. Any output path that exceeds the Soft Threshold is placed back on the queue. Runs until the queue is empty. BFS produces more comprehensible intermediate filesystem state if something breaks halfway through.

---

## Design Notes

**Coarse initial gate:** The Measurer applied to the raw document text before `Document` construction has no knowledge of block boundaries — it treats the entire text as one string. This is intentional: the gate is cheap and catches documents that trivially fit. Accuracy improves as the pipeline progresses and block structure becomes known. The coarser estimate is applied to the coarser decision; the more precise estimate is applied as constraints tighten toward the Hard Threshold.

**`is_critical_reduce` pre-scan:** Rather than detecting a critical reduction after the fact and restoring prior state, the scan detects the condition before mutation occurs. The `_had_paragraph` and `_had_code` flags prevent false positives from segments that never had both block types. The Hard Threshold switch is clean and one-way.

See `risks.md` for known design tensions and anticipated refactor pressure points.
