# Requirements — FIT Generator: Basic Mechanical Split

## Functional Requirements

**Size constraints (enforced, not advisory):**
- Root document: ≤3k tokens (hard target; configurable)
- Every subdocument: ≤3k tokens (hard target; configurable)
- No document in the output tree may exceed 5k tokens
- Token count estimated at ~4 chars/token throughout

**Recursive processing:**
- The split process applies recursively — subdocuments that exceed the size target are themselves split
- Recursion bottoms out when all output documents are within the size target, or no further split is possible

**Heading detection:**
- Scan each document to find which heading level has multiple occurrences (configurable threshold, default: 2)
- Search order: H1 → H2 → H3 → H4 → H5 → H6
- If a heading level has only one occurrence, inline it fully and continue scanning the next level down
- Use the first heading level with ≥ threshold occurrences as the split boundary

**Split hierarchy (when no usable headings exist):**
1. Ruled lines (`---`, `***`, `___`)
2. Code blocks (fenced: ` ``` ` or `~~~`)
3. Paragraphs (blank-line-separated)
4. Sentences (period/question/exclamation boundaries)
5. Words (whitespace boundaries)
6. If no words: do not split; emit a warning

**Code block handling:**
- When splitting on code blocks: include any preceding free-text paragraph in the same chunk as the code block
- Attempt language identification from the fenced code block info string (e.g. ` ```python `)
- Supported languages for inline preference: `python`, `javascript`, `rust`, `c`, `c++` (configurable)
- Inline up to a configurable number of code blocks in the preferred language (default: 2) rather than splitting them out
- When a synthetic subdoc is created from a code block, generate a name from context (preceding heading or paragraph text)
- Subdoc names for non-heading splits: ordered numbered filenames (e.g. `part-01.md`, `part-02.md`)

**Root document content:**
- Includes heading + first prose paragraph (or equivalent lead-in) for each section that has a subdoc
- Inline sections that are small enough to fit (within the inline threshold)
- Every link to a subdoc includes a parenthetical token estimate: `(~N tokens)`

**Token count annotation:**
- All subdoc links in the root and at every level include `(~N tokens)` based on the subdoc's actual content length ÷ 4

**Output structure:**
- Rewrites the source file in place as the root document
- Creates a subdirectory named after the source file (lowercased, no extension) for subdocuments
- Backs up the original file before any writes

## Configuration

All configurable values have uppercase constants at the top of the script as defaults. CLI args override defaults.

| Option | Default | Description |
|---|---|---|
| `--root-max-tokens` | 3000 | Maximum tokens for the root document |
| `--doc-max-tokens` | 3000 | Maximum tokens for any subdocument |
| `--split-threshold` | 2 | Minimum heading occurrences to trigger split |
| `--inline-languages` | `python` | Comma-separated preferred languages to inline |
| `--inline-max` | 2 | Max code blocks of preferred language to inline |
| `--dry-run` | false | Print what would happen without writing files |

## Constraints and Scope

- Python 3 script; markdown parsing library preferred over hand-rolled regex where one exists
- Language identification: use fenced code block info string when present; fall back to `pygments.guess_lexer` with a confidence threshold for unannotated blocks; label below-threshold blocks as `"Code"` (threshold to be confirmed by prototype — see Risks)
- If a chunk cannot be split further and still exceeds the size target, emit a warning and leave it as-is — do not silently truncate content
- The script must always produce output that is strictly better than `fit_split.py` (no regressions on any input)
- Out of scope: YAML/TOML front matter stripping, HTML markdown, non-UTF-8 encodings, watch mode, batch processing of multiple files (future specs)
