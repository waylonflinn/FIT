# Research — FIT Generator: Basic Mechanical Split

## Foundations

**Platform:** Python 3, Linux filesystem, standard markdown (CommonMark-compatible).

**Relevant specifications:**
- CommonMark spec governs heading levels, fenced code blocks, thematic breaks (ruled lines), and paragraph boundaries — all the split points in our hierarchy
- Fenced code blocks carry an optional info string (e.g. ` ```python `) which is the standard mechanism for language annotation; CommonMark defines it but does not require it

**Design intent of CommonMark:** Headings and thematic breaks are explicit author-chosen structural signals. Paragraphs are the natural unit of prose. Code blocks are semantically distinct from prose. The spec encodes a clear hierarchy of structural salience — which maps directly onto our split strategy hierarchy.

## Libraries

### markdown-it-py (already installed, v3.0.0) ✅

**Recommendation: use this as the primary parser.**

- Parses markdown into a flat token stream with `token.map = [start_line, end_line]` for most block-level tokens
- Token types cover everything we need: `heading_open` (with `markup='#'/'##'/etc.`), `fence` (with `info='python'`), `hr`, `paragraph_open`, `inline`
- The line map is the key insight: we can use the AST to understand structure, then use line positions to slice the original source faithfully — no round-trip rendering, no reformatting, content preserved exactly
- Heading level available directly from `token.tag` (`h1`–`h6`) or `token.markup` (count `#` chars)
- Fence info string: `token.info.strip().split()[0]` gives the language identifier (or `''` if unannotated)

Token map verification (confirmed working):
```
heading_open    map=[0, 1]   markup='##'
fence           map=[8, 11]  markup='```'  info='python'
hr              map=[12, 13] markup='---'
paragraph_open  map=[14, 15]
```

### Pygments (already installed, v2.19.2) — conditional use

- `get_lexer_by_name(lang)` reliably maps CommonMark info strings to lexers for known languages
- `guess_lexer(code)` internally calls `lexer_cls.analyse_text(code)` on all lexers and picks the highest score (0.0–1.0)
- Observed scores on test snippets:
  - Substantial Python: 1.0 (Python) — unambiguous, clearly usable
  - Node.js: 0.2 (GDScript) — false positive, no JS-specific heuristic
  - Rust: 0.05 (CSS+Lasso) — noise, Rust lexer scores nothing
  - C: 0.1 (tied across C, nesC, eC, CUDA, etc.) — ambiguous, C lexer doesn't dominate
- **Conclusion:** use `get_lexer_by_name` to normalize info strings (e.g. `"py"` → `"Python"`); for unannotated blocks, use `guess_lexer` with a confidence threshold — scores above threshold use the identified language name, scores below fall back to `"Code"` as the label
- **Fiddly bit:** the right threshold is empirical. A threshold of ~0.5 looks correct based on initial tests (Python passes, all others fail cleanly) but needs prototyping against a wider range of real-world code blocks to confirm. This is a prototype candidate for Risk Analysis.

### Sentence splitting — stdlib regex (no extra dependency needed)

`re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)` handles the common case correctly, including abbreviations like "Fig. 1.2" and "U.S." that don't trigger false splits (uppercase lookahead prevents splitting mid-sentence). Good enough for a fallback — this is the last resort before word-splitting anyway.

### No existing markdown splitter/chunker found

No installed library (langchain-text-splitters, markdown-splitter, etc.) covers our use case. This is novel enough that we build it.

## Exemplars and Patterns

### LangChain MarkdownHeaderTextSplitter

LangChain has a `MarkdownHeaderTextSplitter` that splits on heading boundaries and attaches metadata. Key patterns worth borrowing:
- Treat each heading as a chunk boundary with the heading text as metadata/name
- Propagate parent heading context into child chunks (breadcrumb)

We don't need the metadata system, but the "heading as boundary + name" pattern is directly applicable.

### Unix pipeline / single-file-at-a-time

The persistence-of-intermediaries insight from Synthesis maps onto the classic Unix pattern: each invocation does one thing to one file, writes output, exits. A driver loop handles the rest. This is simpler and more debuggable than a recursive in-memory tree.

**Concrete implementation pattern:**
```
process_file(path) -> list[Path]   # returns paths of written subdocs
queue = [input_path]
while queue:
    f = queue.pop()
    if token_count(f) > MAX_TOKENS:
        new_files = process_file(f)
        queue.extend(new_files)
```

This is a BFS/DFS traversal where the frontier is paths on disk. Clean, testable, easy to reason about.

### Name generation from context

For non-heading splits, the best available name comes from the immediately preceding inline content. Pattern: walk backwards from the split point to find the nearest `inline` token; slugify its text; fall back to `part-NN` if empty or too long.

## Open Questions Resolved

**Language detection for unannotated blocks:** Use info string when present; fall back to `guess_lexer` with a confidence threshold (~0.5 based on initial tests) for unannotated blocks; label anything below threshold as `"Code"`. Threshold needs prototyping to confirm — flagged as a risk.

**Sentence splitting:** stdlib regex is sufficient; no NLTK needed.

**Round-trip fidelity:** Use token line maps to slice original source lines. Do not render tokens back to markdown — this avoids any reformatting or content loss.
