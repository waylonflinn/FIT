# Requirements — FIT Generator: Basic Mechanical Split

## Functional Requirements

**Size constraints (enforced, not advisory):**
- Soft Threshold: 3k tokens (target; configurable). Root documents are measured against this first; subdocuments that exceed it trigger further splitting.
- Hard Threshold: 5k tokens (ceiling; configurable). Documents exceeding this after all reduction steps emit an additional warning.
- Token count estimated at ~4 chars/token throughout

**Recursive processing:**
- The split process applies recursively — subdocuments that exceed the Soft Threshold are themselves split
- Recursion bottoms out when all output documents are within the Soft Threshold, or no further split is possible
- Root document: exits (no write) if below Soft Threshold; exits with warning if no segmentation target found
- Recursive documents: skipped (no write) if below Soft Threshold

**Heading detection and segmentation target:**
- Segmentation target: the lowest heading level (H1–H6) or ruled line such that the count of all headings at and above that level is ≥ Minimum Segmentation Element Count (default: 3)
- Search order: H1 → H2 → H3 → H4 → H5 → H6 → ruled lines
- All headings above the segmentation target also produce their own segments (non-overlapping)
- If no level meets the minimum count before exhausting all heading levels, use the lowest level found; emit a warning
- If no headings or rules exist: emit a warning and leave the document as-is (block-level splitting is a future extension)
- Each subdocument rescans from H1

**Inline vs. subdoc classification (base segmentation):**
A segment is initially inlined if either condition holds (OR):
- **Threshold condition:** total token count < Inline Threshold (default: 600)
- **Trivial extension condition:** the segment consists of a single paragraph, plus any additional content within Trivial Extension Threshold tokens (default: 25) of that paragraph's length — i.e. `len(body) <= len(first_para) + trivial_extension_threshold`

These are two independent inlining mechanisms. Either alone is sufficient. Inline segments are kept fully intact through all reduction steps until step 3 begins converting them to subdocs by reducing the Inline Threshold.

Subdoc segments: everything not initially inlined. The inline component in the root doc starts with the first prose paragraph plus all priority code blocks in priority order.

**Reduction loop — inline component of subdoc segments:**
The document is measured after each reduction pass; reduction stops when satisfied. The loop progressively trims inline components of subdoc segments — removing lower-priority code blocks before higher-priority ones, and non-code content last. Inline segments remain intact until the Inline Threshold is reduced enough to demote them to subdoc status. Measurement is against the Soft Threshold until further reduction would remove the last remaining non-code or code block from any segment (detected via pre-scan); at that point measurement switches permanently to the Hard Threshold. If the final document still exceeds the Soft Threshold, emit a warning. If it exceeds the Hard Threshold, emit an additional warning. See design.md for the precise algorithm.

**Code block priority ordering:**
- Priority is defined by language, in order: `python`, `javascript`, `typescript` (configurable via `--inline-languages`)
- Within a priority tier, document order is used
- Unannotated blocks (labelled `"Code"`) are lowest priority
- Language identification: normalize fenced code block info strings via `pygments.get_lexer_by_name`; unannotated blocks labelled `"Code"`

**Token count annotation:**
- All subdoc links at every level include `(~N tokens)` based on the subdoc's actual content length ÷ 4

**Token count annotation:**
- All subdoc links at every level include `(~N tokens)` based on the subdoc's actual content length ÷ 4

**Output structure:**
- Rewrites the source file in place as the root document
- Creates a subdirectory named after the source file (lowercased, no extension) for subdocuments
- Backs up the original file before any writes, using `.unfit` between filename and extension (e.g. `document.unfit.md`)

## Configuration

All configurable values have uppercase constants at the top of the script as defaults. CLI args override defaults.

| Option | Default | Description |
|---|---|---|
| `--soft-threshold` | 3000 | Soft token target; triggers splitting and reduction loop |
| `--hard-threshold` | 5000 | Hard token ceiling; triggers additional warnings and below-minimum pruning |
| `--inline-threshold` | 600 | Segments below this token count are inlined in full |
| `--inline-threshold-reduction-increment` | 100 | Amount Inline Threshold is reduced per step 3/4 iteration |
| `--trivial-extension-threshold` | 25 | Single-paragraph segments are inlined if their total length is within this many tokens of that paragraph's own length (i.e. they contain little beyond the paragraph) |
| `--min-segment-count` | 3 | Minimum number of segments required to use a given heading level as segmentation target |
| `--inline-languages` | `python,javascript,typescript` | Comma-separated preferred languages for code block priority, in order |
| `--dry-run` | false | Print what would happen without writing files |

## Constraints and Scope

- Python 3 script; markdown parsing library preferred over hand-rolled regex where one exists
- Language identification: use fenced code block info string when present (normalized via `pygments.get_lexer_by_name`); label unannotated blocks as `"Code"` and exclude them from inline preference — detection libraries were evaluated and rejected (see Research for results and rationale)
- If a chunk cannot be split further and still exceeds the size target, emit a warning and leave it as-is — do not silently truncate content
- The script must always produce output that is strictly better than `fit_split.py` (no regressions on any input)
- Out of scope: YAML/TOML front matter stripping, HTML markdown, non-UTF-8 encodings, watch mode, batch processing of multiple files (future specs)
