# Requirements — FIT Generator: Basic Mechanical Split

## Functional Requirements

**Size constraints (enforced, not advisory):**
- All documents (root and subdocuments): ≤3k tokens (hard target; configurable)
- Target is 3k tokens; hard ceiling is 5k. Documents between 3k–5k are acceptable only when further splitting would lose more than it gains (e.g., breaking a code block mid-statement).
- Token count estimated at ~4 chars/token throughout

**Recursive processing:**
- The split process applies recursively — subdocuments that exceed the size target are themselves split
- Recursion bottoms out when all output documents are within the size target, or no further split is possible

**Heading detection:**
- Scan each document to find which heading level has multiple occurrences (configurable threshold, default: 2)
- Search order: H1 → H2 → H3 → H4 → H5 → H6
- If a heading level has only one occurrence, inline it and continue scanning the next level down; "inline" means kept in the parent when the content fits — a single heading whose content exceeds the target is split at the next available boundary
- Use the first heading level with ≥ threshold occurrences as the split boundary
- Each subdocument rescans for headings starting fresh from H1

**Split hierarchy (when no usable headings exist):**
1. Ruled lines (`---`, `***`, `___`)
2. Code blocks (fenced: ` ``` ` or `~~~`)
3. Paragraphs (blank-line-separated)
4. Sentences (period/question/exclamation boundaries)
5. Words (whitespace boundaries)
6. If no words: do not split; emit a warning

**Document content (uniform at all levels, including root):**
- For each child section extracted to a subdoc: include heading + lead-in in the parent document, followed by the subdoc link with token annotation
- Lead-in: first prose paragraph following the heading (excluding code blocks, lists, and other non-prose block elements)
- Lead-in truncation: if the combined entry (heading + lead-in + token annotation) would push the parent document over the target, truncate the lead-in to its first sentence
- Inline sections that fit within the target rather than linking to a subdoc
- Every link to a subdoc includes a parenthetical token estimate: `(~N tokens)`

**Code block handling:**
- When splitting on code blocks: include any preceding free-text paragraph in the same chunk as the code block
- Attempt language identification from the fenced code block info string (e.g. ` ```python `)
- For unannotated blocks: label as `"Code"` and exclude from inline preference — language detection libraries are not used at runtime (see Research for prototype results and rationale)
- Supported languages for inline preference: `python`, `javascript`, `typescript`, `rust`, `c`, `c++` (configurable)
- Inline up to a configurable number of code blocks in a preferred language (default: 2) rather than splitting them out. If preferred language code blocks must be dropped, lowest priority will be dropped first.
- Overflow: if a paragraph + code block together exceed the target, the code block becomes its own subdoc and the paragraph becomes the lead-in for that subdoc link in the parent; if the code block alone exceeds the target, it becomes its own subdoc with a warning
- When a synthetic subdoc is created from a code block, generate a name from context:
  - Use the preceding heading, when available
  - When reliable language information is available, fall back to language tags with numbered suffix (e.g. `python-01`); when only one block for a given language appears, drop the numbering (e.g. `python`)
  - When no reliable language information is available, fall back to `code` with numbered suffix (e.g. `code-01`)
- Subdoc names for non-heading splits: ordered numbered filenames (e.g. `part-01.md`, `part-02.md`)

**Token count annotation:**
- All subdoc links at every level include `(~N tokens)` based on the subdoc's actual content length ÷ 4

**Output structure:**
- Rewrites the source file in place as the root document
- Creates a subdirectory named after the source file (lowercased, no extension) for subdocuments
- Backs up the original file before any writes, using `.orig` between filename and extension (e.g. `document.orig.md`)

## Configuration

All configurable values have uppercase constants at the top of the script as defaults. CLI args override defaults.

| Option | Default | Description |
|---|---|---|
| `--max-tokens` | 3000 | Maximum tokens for any document (root or subdocument) |
| `--split-threshold` | 2 | Minimum heading occurrences to trigger split |
| `--inline-languages` | `python,javascript,typescript` | Comma-separated preferred languages to inline, in priority order |
| `--inline-max` | 2 | Max code blocks of preferred language to inline |
| `--dry-run` | false | Print what would happen without writing files |

## Constraints and Scope

- Python 3 script; markdown parsing library preferred over hand-rolled regex where one exists
- Language identification: use fenced code block info string when present (normalized via `pygments.get_lexer_by_name`); label unannotated blocks as `"Code"` and exclude them from inline preference — detection libraries were evaluated and rejected (see Research for results and rationale)
- If a chunk cannot be split further and still exceeds the size target, emit a warning and leave it as-is — do not silently truncate content
- The script must always produce output that is strictly better than `fit_split.py` (no regressions on any input)
- Out of scope: YAML/TOML front matter stripping, HTML markdown, non-UTF-8 encodings, watch mode, batch processing of multiple files (future specs)
