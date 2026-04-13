# Design — FIT Generator: Basic Mechanical Split

> ⚠️ **Initial proposal — needs critical review and evaluation before proceeding.**

## Major Components

### Driver Loop

The outermost shell. Maintains a queue of file paths to process. Feeds each through `process_file`; any output path that still exceeds the token target goes back on the queue. Runs until the queue is empty.

BFS and DFS both work — DFS is simpler and sufficient.

---

### process_file(path) → list[Path]

The core unit of work. Reads a file, measures it, decides whether and how to split, delegates to the Splitter, delegates to the Writer, returns the list of new paths created. The Driver Loop calls this repeatedly; no file is processed more than once per pass.

---

### Measurer

`chars ÷ 4` — used constantly throughout the pipeline. Worth isolating so the estimation logic lives in exactly one place.

---

### Heading Detector

Scans the `markdown-it-py` token stream for the first heading level with ≥ threshold occurrences (default: 2). Handles the single-occurrence inline rule: if a level has only one heading, skip it and scan the next level down. Returns the split level, or `None` if no usable headings exist.

Edge cases (per Requirements):
- A single heading whose content exceeds the target is not inlined — it's split at the next available boundary
- Each subdocument rescans from H1

---

### Splitter

Implements the strategy hierarchy. Takes a parsed document and returns a list of chunks. Tries strategies in order until one produces ≥ 2 chunks:

1. Headings (via Heading Detector)
2. Ruled lines
3. Code blocks (delegates to Code Block Handler)
4. Paragraphs
5. Sentences
6. Words
7. Cannot split — emit warning, return as-is

Each strategy is its own function. The Splitter tries them in order and stops at the first that yields a valid partition.

---

### Code Block Handler

Lives within the Splitter but has enough logic to stand alone. Responsibilities:

- **Info string normalization** — `pygments.get_lexer_by_name(tag)` maps info strings to canonical names; unannotated blocks are labelled `"Code"`
- **Inline preference** — collect preferred-language blocks (priority-ordered per `--inline-languages`); inline up to `--inline-max`; when over the limit, drop lowest priority first
- **Preceding paragraph pairing** — include the free-text paragraph immediately before a code block in the same chunk
- **Overflow handling** — if paragraph + code block exceed the target: code block becomes its own subdoc, paragraph becomes its lead-in in the parent; if the code block alone exceeds the target: subdoc with a warning
- **Name generation** — delegates to Name Generator

---

### Name Generator

Given a chunk and its context, produces a filename stem. Priority:

1. Preceding heading — slugified
2. Reliable language tag — with numbered suffix (e.g. `python-01`); drop suffix if only one block for that language
3. `"Code"` tag — `code-01`, `code-02`, …
4. `part-NN` — last resort for non-heading, non-code splits

---

### Writer

Takes the original file path and a list of chunks with metadata; produces the rewritten parent document and the subdoc files on disk.

Responsibilities:
- **Backup** — writes `<filename>.orig.<ext>` before any writes (once per file, not per recursion)
- **Parent document** — for each chunk: inline if it fits within the target, otherwise write a subdoc and emit heading + lead-in + link + token annotation
- **Subdoc files** — writes each non-inline chunk to the subdirectory (`<filename>/`)
- **Token annotation** — `(~N tokens)` on every subdoc link, based on actual content length ÷ 4

---

## Interaction Flow

```
CLI args
  └─► Driver Loop
          └─► process_file(path)
                  ├─► Measurer          (fits? → done)
                  ├─► Heading Detector  (→ strategy)
                  ├─► Splitter          (→ chunks)
                  │       └─► Code Block Handler  (if code block strategy)
                  ├─► Name Generator    (→ filenames)
                  └─► Writer            (→ parent doc + subdoc files on disk)
                          └─► new paths → Driver Loop queue
```

---

## Open Design Question

**Where does the inline vs. subdoc decision live?**

The Splitter produces chunks without knowing which will be inlined. The Writer knows sizes and makes the inline decision. This is probably the right split — but it means the Writer needs to re-measure each chunk and apply the inline threshold, which is logic that currently lives implicitly in the spec but hasn't been explicitly assigned to a component. Needs resolution before implementation.
