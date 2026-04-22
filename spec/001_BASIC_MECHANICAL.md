# FIT Generator — Basic Mechanical Split

_Effort: Involved (3)_

_Capability: Design (3)_

_Elapsed: ~4d_

_Daily logs: Requirements/Synthesis/Research: 2026-04-09.md_

_Status: Debug (8/10)_

_Updated: 2026-04-22_

---

## Goal

A command-line Python script that converts an arbitrarily large markdown document into a Fitted Information Tree (FIT): a root document (≤3k tokens) linking to subdocuments (≤3k tokens each), recursively, until the entire tree satisfies the size constraints. The script must handle the full range of real-world markdown structure — headings, code blocks, ruled lines, paragraphs, sentences — and produce output that is strictly better than the existing `fit_split.py` in every case. It is intended to be an implementation of Level 1.5.

---

## Requirements

**Configuration**
| Option | Default | Description |
|---|---|---|
| `--soft-threshold` | 3000 | Soft token target; triggers splitting and reduction loop |
| `--hard-threshold` | 5000 | Hard token ceiling; triggers additional warnings and below-minimum pruning |
| `--inline-threshold` | 600 | Segments below this token count are inlined in full |
| `--inline-threshold-reduction-increment` | 100 | Amount Inline Threshold is reduced per step 3/4 iteration |
| `--trivial-extension-threshold` | 25 | Single-paragraph segments are inlined if their total length is within this many tokens of that paragraph's own length (i.e. they contain little beyond the paragraph) |
| `--min-segment-count` | 3 | Minimum number of segments required to use a given heading level as segmentation target. Minimum value: 2 (enforced at startup; a value of 1 would allow infinite recursion) |
| `--inline-languages` | `python,javascript,typescript` | Comma-separated preferred languages for code block priority, in order |
| `--dry-run` | false | Print what would happen without writing files |

**Functional requirements:**
- Enforced size targets
- Recursive
- Heading detection
- Split fallback hierarchy
- Code block handling
- Document content (uniform at all levels)
- Token count annotation
- Back up original file before any writes

**Constraints and scope:**
- Python 3; prefer a markdown parsing library over hand-rolled regex
- Language identification via fenced code block info string (open question — see Research)
- If a chunk cannot be split further and still exceeds the target: warn, leave as-is, do not truncate
- Must always produce output strictly better than `fit_split.py` — no regressions
- Out of scope: YAML/TOML front matter, HTML markdown, non-UTF-8 encodings, watch mode, batch processing

Functional requirements explanation, configuration table and full details:
→ [001_basic_mechanical/requirements.md](001_basic_mechanical/requirements.md) (~1418 tokens)

---

## Synthesis

The script is a **recursive partitioning algorithm with a sizing constraint and natural persistence of intermediaries**. At every level, the same loop applies: measure the content, decide if it fits, and if not, find the best available split strategy, write the results to the filesystem, and recurse on any output that still exceeds the target.

**Core abstractions:**

- **Measure** — token estimate (chars ÷ 4) drives every decision; runs on every chunk at every level
- **Partition** — divide content using the richest semantic boundary available; strategies form a naturalness hierarchy ordered by author intent (headings → ruled lines → code blocks → paragraphs → sentences → words)
- **Write** — partitioned chunks are written to the filesystem immediately; the filesystem is the data structure
- **Recurse** — any written chunk that still exceeds the target is fed back through the same process; recursion is just re-invoking the algorithm on a written file
- **Name** — headings give names for free; code blocks derive names from surrounding context; all other splits use ordered numbered filenames

**Key insight:** the root document is not special. It's subject to the same sizing constraint as every subdocument. The algorithm is uniform — entry point and output nodes are all treated the same way.

**Key insight:** the filesystem is the data structure. Writing intermediaries at each level makes the process naturally resumable, debuggable, and easier to reason about — no need to solve the full tree depth in memory upfront. This also suggests a clean code structure: one function that processes a single file and returns a list of outputs that need further processing, and a driver loop that applies it until no oversized files remain.

**Key insight:** split strategy and sizing interact. A chunk split at code block boundaries may still produce pieces that are too large (e.g. a 6k-token code block). The recursion handles this naturally — each written piece is measured and re-split if needed, falling further down the hierarchy.

**Key insight:** the strategy hierarchy represents a graceful degradation of semantic richness. Headings produce meaningful, navigable structure with natural names. Each step down — ruled lines, code blocks, paragraphs, sentences — makes meaningful link names, divisions, and summaries progressively harder to construct and more likely to degrade into arbitrary numbering. A warning when falling below paragraph-level is appropriate.

The goal statement holds. No revisions needed.

---

## Research

**Foundations:** CommonMark spec governs all our split points; its structural hierarchy maps directly onto the split strategy hierarchy.

**Key findings:**
- `markdown-it-py` (already installed): use as primary parser. Token stream includes `token.map = [start_line, end_line]` for all block tokens — use the AST for structure, line maps to slice original source faithfully (no round-trip rendering)
- `pygments` (already installed): use `get_lexer_by_name` to normalize info strings; unannotated blocks labelled `"Code"` — detection libraries evaluated and rejected (see research.md for rationale)
- Sentence splitting: stdlib regex sufficient, no NLTK needed
- No existing markdown splitter covers this use case — building fresh

**Exemplar pattern (driver loop):** Unix single-file-at-a-time — `process_file(path)` returns paths of written subdocs; a driver loop feeds oversized outputs back in. BFS/DFS over paths on disk.

→ [001_basic_mechanical/research.md](001_basic_mechanical/research.md) (~2,058 tokens)

---

## Design

Object-oriented design. Core classes: `Measurer`, `Segment`, `Document`, `Writer` (factory pattern). `process_file` is thin — constructs objects and hands off to the reduction loop and writer. `DriverLoop` manages BFS queue of file paths. Inline vs. subdoc classification lives in `Document._parse`; the reduction loop progressively demotes inline segments to subdoc as the Inline Threshold decrements.

→ [001_basic_mechanical/design.md](001_basic_mechanical/design.md) (~4,337 tokens)

---

## Risks

**MDX/Mintlify component syntax in source documents**
Some documentation sources (e.g. Anthropic's docs, built with Mintlify) use JSX components embedded in markdown: `<section title="...">` as a section grouping construct and `<CodeGroup>` as a tabbed code block wrapper. markdown-it-py parses these as flat `html_block` tokens with no structural awareness. A splitter operating on standard markdown would treat them as opaque blobs, missing valid split boundaries and potentially producing oversized chunks. Mitigation: normalize at ingestion time (see Prototypes). The splitter itself sees only standard markdown and requires no changes.

→ [001_basic_mechanical/risks.md](001_basic_mechanical/risks.md) (~2,320 tokens)

---

## Prototypes

**MDX preprocessor** — Convert Mintlify/MDX component syntax to standard markdown before ingestion. Belongs in the document download/ingestion tool, not the splitter. Approach: parse source with markdown-it-py to get a token stream; walk tokens tracking heading depth; replace `html_block` tokens matching `<section title="...">` with synthetic heading tokens at depth+1; discard `<CodeGroup>`, `</CodeGroup>`, `</section>` wrapper tokens; reconstruct output using `token.map` line ranges against original source. This prototype becomes the production preprocessor — it is not throwaway. Primary test case: `doc/anthropic/build-with-claude/prompt-caching/prompt-caching-examples.md` (14k tokens, 4 sections, 3 CodeGroups).

**`pygments` fallback** ✅ — `try/except ClassNotFound` confirmed working. Tested 18 info strings; `output`, `console`, `text`, `diff`, `http` all resolve to real lexers — only `patch` triggers `ClassNotFound`. Fallback is still necessary but fires rarely. Empty/whitespace handled by pre-check. Case-insensitive (`PYTHON` → Python). Prototype: `forge/fit/prototypes/pygments_fallback/pygments_fallback.py`. (R4)

**Line map reconstruction** ✅ — `token.map` present and correct for all block types tested. Key finding: inter-block blank lines fall in gaps between token ranges. Fix: slice as `lines[start:next_start]` (extending to next block's start line, or EOF) — gives byte-identical reconstruction. Constraint: block text must never be stripped after slicing. `'\n'.join()` is not equivalent — fails on double blank lines. Prototype: `forge/fit/prototypes/line_map/line_map.py`. (R8)

---

## Implementation

→ [001_basic_mechanical/implementation-plan.md](001_basic_mechanical/implementation-plan.md) (~5,050 tokens)

---

## Tests

Five documents run through `fit_split.py`; results recorded, failure modes identified, "strictly better" criteria defined.

Primary failures: no recursion (six subdocs over 3k, four over 8k); code block blindness (prompt-caching-examples.md at 14,343 tokens); unnecessary split of a sub-target document (tool-use/overview.md at 2,137 tokens). Two documents produced clean output and serve as regression checks.

Additional test document candidates: `doc/anthropic/skills/skills/claude-api/shared/live-sources.md` (~4k tokens, do not load in full — extract URLs and download selectively as needed).

→ [001_basic_mechanical/tests.md](001_basic_mechanical/tests.md) (~6,683 tokens)

---

## Bugs

B1 (fixed) — _parse_segment silently drops container blocks (bullet_list, ordered_list, blockquote, table). Root cause: top_level_ranges was built as (open.map[0], close.map[1]) pairs, but container close tokens always have map=None in markdown-it-py. The null check if open_token.map and close_token.map silently discarded the range. Fix: use (open_token.map[0], open_token.map[1]) — the open token's map already spans the full container extent. Confirmed via prototype prototypes/close_token_maps/close_token_maps.py.

B2 (open) — Duplicate heading names are not fully suffixed. When a slug appears more than once, the first occurrence is assigned the bare name (section) and subsequent ones are suffixed (section_01, section_02). Expected behavior: all occurrences suffixed from _01. Root cause: single-pass name assignment in Document._parse — first-seen gets no suffix. Fix requires a two-pass approach: pre-scan all slugs to identify duplicates, then assign _01-onward suffixes to all instances.

---

## Extensions

Possible follow-on tasks identified during the build process. Out of scope for this spec but worth tracking.

- **Richer name generation** — keyword extraction from surrounding prose (e.g. `yake`, `rake-nltk`) to produce more meaningful subdoc names when no heading is available, rather than slugifying the nearest paragraph text or falling back to `part-NN`
- **Robust sentence splitting** — replace the stdlib regex fallback with `nltk.sent_tokenize` for better handling of edge cases (abbreviations, inline code with periods, parenthetical sentences)
- **Extractive lead-in summaries** — use `sumy` (TextRank or LSA) to generate tighter one-liner summaries for root doc entries when the first paragraph is too long to inline cleanly
- All three are optional dependencies — tool works without them, they improve output quality when present; pattern fits well for a standalone script intended for external use
