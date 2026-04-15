# Design — FIT Generator: Basic Mechanical Split

> ⚠️ **Revised design — supersedes initial proposal.**

## Core Data Structures

**`measure_contents`** — `OrderedDict[str, str | list[str]]`
- Key: segment name
- Value: fully inlined body string (for inline segments) OR raw content blocks (for subdoc segments)

**`subdoc_contents`** — `OrderedDict[str, str]`
- Key: segment name
- Value: full subdoc body (written to disk)

---

## Major Components

### Driver Loop

Maintains a queue of file paths. Feeds each through `process_file`; any output path that exceeds Soft Threshold is placed on the queue. Runs until the queue is empty. BFS will produce more comprehensible intermediate filesystem state (useful if something breaks halfway through).

---

### process_file(path, is_root=False) → list[Path]

Core unit of work. Steps:
1. Measure; if ≤ Soft Threshold, skip (log message) and return `[]`
2. Find segmentation target (see Segmentation Target Finder)
3. If root and no target found: warn and exit (no writes)
4. Build base segmentation (see Base Segmentation)
5. Run reduction loop (see Reduction Loop)
6. Write output (see Writer)
7. Return list of subdoc paths created

---

### Segmentation Target Finder

Scans the token stream for heading levels and ruled lines. Searches H1 → H2 → H3 → H4 → H5 → H6 → ruled lines. At each level, counts headings at that level plus all levels above. Returns the first level where that count ≥ `--min-segment-count`. If no level meets the threshold, returns the lowest level found (with warning). If no headings or rules exist: warns and returns `None`.

All heading levels above and including the segmentation target produce distinct non-overlapping segments.

Implementation Note: possible implementation, maintain counter of all encountered heading levels (including ruled lines) in stream. When a heading count is incremented sum over all elements in the counter and test.

---

### Name Generator

Produces keys for `measure_contents` and `subdoc_contents` (also used as filename stems for subdocs).

- **Heading-derived:** slugify heading text (spaces and punctuation → `_`, collapse runs). If the result is empty (degenerate heading, e.g. bare `##`): use `heading_NN` where `NN` is the 1-based index of that heading among all headings in the document (zero-padded, minimum 2 digits).
- **Ruled line:** `rule_NN` (same indexing scheme, among all rules).
- **Duplicates:** suffix with zero-padded integer starting at `01` (minimum 2 digits, widen as needed).

---

### Classifier (Code Detection)

- `get_type(text: str) -> str` - 'code' | 'text' (detects markdown code blocks, three backticks at beginning and end after stripping)
- `is_code(text: str) -> bool` - syntactic sugar for `get_type == 'code'`. used in `Measurer` and `reduce_segment`
- `get_code_language(text: str) -> str` — `pygments.get_lexer_by_name(tag)` maps info strings to canonical names; unannotated blocks are `"code"`, non-code blocks are `None`

---

### Measurer

- `measure_document(measure_contents: OrderedDict) -> int` - total size of the root document as it would be rendered (concatenation of all inline bodies + all subdoc inline components + link annotations) by applying `measure_segment` to each subdoc segment and `measure_block` to each inline segment
- `measure_segment(segment: list[str]) -> int` - sums over calls to `measure_block` on each block, plus separate measure_block calls for the heading and link (variable length — not in the block list)"
- `measure_block(block: string) -> int` - can be used on blocks and inline segment text; detects code blocks
  - `chars ÷ 4` for text and blocks of unknown type
  - `chars ÷ 3.5` for code blocks

Used constantly throughout the pipeline. Worth isolating so the estimation logic lives in exactly one place.

---

### Segmenter (Base Segmentation Builder)
Given the segmentation target partitions the document into segments.

- `is_inline(text: str, inline_threshold: int) -> bool`
  - either condition holds — (a) total token count < Inline Threshold, OR (b) `len(body) <= len(first_block) + trivial_extension_threshold` (single-block-plus-a-little). These are independent mechanisms; either is sufficient.
- `segment(text: str) -> list[str]` return a list of blocks in document order
  - Example: `[paragraph, code_block_highest_priority, paragraph, code_block_lowest_priority, ..., code_block_medium_priority, paragraph]`

### Base Segmentation

Populate `subdoc_contents` and initial `measure_contents` using segment keys from Name Generator

For `measure_contents`:
- **Inline segment:** `Segmenter.is_inline == True` Value: full body string.
- **Subdoc segment:** everything else → value is a list of raw content blocks in document order (`Segmenter.segment`).
  **Construction:** After segmenting, subdoc block lists are passed to `reduce_segment` (see below) with the `priority_languages` argument populated by `--inline-languages` and the current value of Inline Threshold.
  **Measurement:**  sum of measure of all elements (plus heading and link annotation) → current inline component size.
  **Empty list:**  inline component is link-only.

For `subdoc_contents`: full subdoc body including heading or ruled line that partitions the segment

---

### Reducer (Segment Reduction)

- `reduce_segment(blocks: list[string], measurer: Measurer, threshold: int, priority_languages: list[str] = None) -> list[str]`

    - Return Value:
        return the modified list when the Measurer returns a value below the `threshold`, if `threshold` is zero returns `[]`
    - Algorithm:
        - remove non-priority code blocks, one by one, in reverse document order, testing after each removal (scan from end of array, remove first found)
        - trim priority code blocks, one by one, in reverse priority order, then reverse document order, until one of each priority type remains, testing after each removal. Example: if priority_languages=['python', 'typescript', 'json'], search backwards from end of array until you find a 'json' block, remove it; repeat with 'json' blocks until only one remains, then start trimming 'typescript' blocks until one remains, then 'python'.
        - remove priority code blocks, one by one, in reverse priority order, until only the highest priority remains, testing after each removal
        - remove non-code blocks, one by one, in reverse document order, until one non-code block remains, testing after each removal
        - remove the final code block, test
        - return an empty array
    - Implementation Note: sum of measure should be used rather than measure of concatenation, both for optimization and improved measurement on code blocks.
    - Example:


- `[paragraph, code_block_lowest_priority, paragraph, code_block_highest_priority, code_block, code_block_lowest_priority, paragraph]` →
- `[paragraph, code_block_lowest_priority, paragraph, code_block_highest_priority, code_block_lowest_priority, paragraph]` →
- `[paragraph, code_block_lowest_priority, paragraph, code_block_highest_priority, paragraph]` →
- `[paragraph, paragraph, code_block_highest_priority, paragraph]` →
- `[paragraph, paragraph, code_block_highest_priority]` →
- `[paragraph, code_block_highest_priority]` 

Steps: (1) non-priority code block removed; (2–3) lowest-priority code block instances removed tail-first; (4–5) non-code blocks removed tail-first; result: one paragraph + highest-priority code block.
---

### Reduction Loop

Operates on `measure_contents`. Measures the total size of the root document by applying `Measurer.measure_document`. Applies reduction steps in order until the document level measure condition is satisfied, using `Reducer.reduce_segment`. Loop ends when the condition is satisfied or all segments are link only. If the link only state is reached and the document level measure condition is still not satisfied, a warning is printed.

**Base state:** all subdoc segments start with their constructed block list (measure trimmed below the Inline Threshold).

Steps:

1. **Measure base state** — no removals yet; all blocks present. Measure against Soft Threshold. If satisfied, done. Inline segments untouched.
2. **Reduce Inline Threshold by increment (loop)** — 
  - Inlined segments whose string size now exceeds the reduced threshold convert to subdoc status and their `measure_contents` entry becomes a list of raw content blocks (`Segmenter.segment`).
  - All subdoc segments (new and old) are then pruned with `Reducer.reduce_segment` using the new Inline Threshold.
  - Resulting document is measured against Soft Threshold. 
  - If any call to `reduce_segment` returns fewer than two blocks, immediately switch to Hard Threshold and retest at the previous Inline Threshold (before the decrement that resulted in less than two blocks). Hard Threshold is used for all remaining steps. (implementation note: this requires testing all segments with `reduce_segment` before modifying `measure_contents`. Caching of results from `reduce_segment` is optional)
  - Terminate when the document is below the relevant threshold or all segments are link only (empty array)
3. **Prune to link only** - if all calls to `reduce_segment` return empty arrays and the document still exceeds the Hard Threshold, write link-only and warn.

---

### Writer

Takes `measure_contents` and `subdoc_contents` after the reduction loop; writes to disk.

- **Root document:** assembled from segment entries in order. Inline segments: body verbatim. Subdoc segments: heading + inline component + subdoc link with `(~N tokens)` annotation.
- **Subdoc files:** written to `<source_stem>/` directory; content from `subdoc_contents`.
- **Backup:** `<filename>.unfit.<ext>` written once before any output, only at root level.
- **Dry run:** print actions without writing.

---

## Interaction Flow

```
CLI args
  └─► Driver Loop
          └─► process_file(path, is_root)
                  ├─► Measurer                    (fits? → done)
                  ├─► Segmentation Target Finder  (→ target level or None)
                  ├─► Name Generator              (→ keys for measure_contents and subdoc_contents, filenames for subdoc segments)
                  ├─► Base Segmentation Builder   (→ measure_contents, subdoc_contents)
                  ├─► Reduction Loop              (mutates measure_contents until measure satisfied)
                  └─► Writer                      (→ root doc + subdoc files on disk)
                          └─► new subdoc paths → Driver Loop queue
```
