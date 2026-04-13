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

`re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)` handles the common case but will produce false splits on abbreviations followed by uppercase words — e.g. "U.S. He went home" splits on the period after 'S' because the uppercase lookahead can't distinguish sentence boundaries from abbreviation+uppercase-word boundaries. Good enough for a last resort (this is the fallback before word-splitting), but the limitation should not be papered over. Needs tests: confirm correct splits on ordinary sentences, and confirm known false-positive cases (e.g. "U.S. He", "Fig. 1 The", "Dr. Smith said").

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

### whats-that-code (candidate, not yet evaluated)

- https://pypi.org/project/whats-that-code/ — alternative library for unannotated block detection
- Evaluate alongside `pygments.guess_lexer` in the language detection prototype
- **Prototype corpus:** `doc/anthropic/build-with-claude/prompt-caching.md` — contains a large annotated subdocument (~14k tokens) consisting almost entirely of code blocks; run both libraries against each block, compare predictions to actual info string annotations, record confidence scores, identify a threshold cutoff that gives acceptable accuracy

### Prototype Results and Decision

Prototype run against `prompt-caching-examples.md` (24 annotated code blocks, 8 languages: Python, TypeScript, C#, Go, Java, PHP, Ruby, Shell).

| Library | Accuracy | Coverage | Notes |
|---|---|---|---|
| pygments | 12% at any threshold | 100% | Systematic Python false positives (1.00 confidence on Go, Java, TS — all wrong) |
| whats-that-code | 38% | 100% | Confident nonsense: delphi, coldfusion, carbon, gdscript |
| codelang-detect | 50% | 100% | Better; correct on Go, Java, PHP, partial C#; blind to Ruby, Shell, TypeScript |

Per-language breakdown for codelang-detect (best performer):
- Go ✓, Java ✓, PHP ✓, JSON ✓ — reliable
- C# — 2/3 correct
- Python — 2/3 correct
- TypeScript — 0/3 (misidentified as javascript, which is syntactically nearly identical)
- Ruby — 0/3
- Shell — 0/2

**Decision: drop language detection libraries entirely.** A confident wrong label is worse than "Code" — it would cause a TypeScript block to inline as JavaScript, or silently misfile Ruby. The error rate and systematic blind spots make runtime detection unreliable for our use case. The Anthropic docs (our primary corpus) are fully annotated; well-maintained documentation generally is. Use the info string when present, normalized via `pygments.get_lexer_by_name`; label unannotated blocks as `"Code"` and exclude them from inline preference.

## Open Questions Resolved

**Language detection for unannotated blocks:** Use info string when present, normalized via `pygments.get_lexer_by_name`. Label unannotated blocks as `"Code"` and exclude them from inline preference. Detection libraries (pygments guess_lexer, whats-that-code, codelang-detect) were prototyped and rejected — best accuracy was 50% with systematic blind spots for Ruby, Shell, and TypeScript. A confident wrong label is worse than "Code". No runtime dependency on detection libraries.

**Sentence splitting:** stdlib regex is sufficient as a last resort; no NLTK needed. Known limitation: false splits on abbreviations followed by uppercase words (e.g. "U.S. He went home"). Acceptable given it's the fallback before word-splitting, but tests should exercise both the common case and known failure cases.

**Round-trip fidelity:** Use token line maps to slice original source lines. Do not render tokens back to markdown — this avoids any reformatting or content loss.
