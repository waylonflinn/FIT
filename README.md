# Fitted Information Tree

Agentic affordance and context design pattern. A document data structure optimized for agent use.

## What Is It?

A Fitted Information Tree (FIT) is a way to structure information in an agent and context friendly way.
It allows just the right amount of information to be accessed for any given activity or task.
It leaves pointers in context for accessing additional information (via subdocuments) as the session evolves and more information becomes relevant.

It is not a summarization technique (the intent is to preserve all information available in a document) but it can leverage summarization to optimize access patterns and context usage.

This repository contains python scripts for turning a standard large markdown file into a FIT.
It also contains agent Skills for using and creating FITs.

## How to Use It? (Agentic Skill)

Follow this procedure when reading a document structured as a fitted information tree.

When it seems relevant to a task, read the root node file.
This relevance assessment might be based on memory, a simple prompt in AGENTS.md, a user prompt or your own intuition and initiative.
Once you've read the document, read any linked documents relevant to the task at hand. 
Read only documents relevant to the task.
Examine any token load information (optionally included in parentheses after the link) and avoid documents that are too large (>5k tokens).
If additional nodes become relevant later in a session, read them before proceeding.
Follow this procedure recursively down the tree.


## How to Generate One? (Agentic Skill)

> The full, current version of this skill lives at
> [skills/fit-creation/SKILL.md](skills/fit-creation/SKILL.md) — including
> per-repository threshold configuration (`.fit.toml`), born-fitted (Level 4)
> authoring, and the splitting/maintenance procedures. The summary below is the
> quick reference; on conflict, the skill file wins.

Follow this pattern when creating and editing documents that are likely to be read by an agent and loaded completely into context.

The top level node is a reasonably sized overview document that links to subdocuments that contain additional details. The top level document is not simply a bag of links. It should contain the most relevant and useful information, as well as the link to the subdocument with additional details. If one of those subdocuments subsequently grows too large, it becomes an overview with links to subdocuments. This can be formulated as a recursive process (and is implemented that way at lower FIT levels in this repository).

Sub-documents are located in a folder named after the original document, lowercased and without the extension (e.g. a top level document `BERNARD.md` links to a subdocument at `bernard/model-candidates.md`)
Links to subdocuments should use relative file paths in standard markdown link format where both the link text and target are the same and should be prefixed with an '→' character (e.g.  → [bernard/model-candidates.md](bernard/model-candidates.md))
Links to subdocuments should also include a parenthetical token estimate after the link for smarter agent context management (e.g. (~1,760 tokens)). May be estimated at ~4 chars per token.
Links to subdocuments should be the last thing in a section (in markdown this corresponds to a heading level).
Simple strategy for markdown files:
- the highest (or second highest, whichever is most used) heading level in any document defines sections
- when each section grows too large it becomes a candidate for creation of a subdocument
- when turning a section into a subdocument retain in the top level document the information which is most important or relevant
- put the full contents of the section in the subdocument

Documents over 3k tokens should be refactored. Documents should never exceed 5k tokens.

# FIT Level
A FIT can be constructed with increasing levels of capability (available intelligence) and a priori query and task knowledge.

Implementation of Levels up to 1.5 are in-progress. Higher level implementations are planned.

One might ask, "Why bother with lower levels?"

The answer is that FITs are intended to provide agentic support at multiple context sizes and capabilities. Involving a powerful LLM in the optimization of context for a simple one isn't practical and limits utility. Providing simple methods for FIT generation enables even less powerful LLMs (for example small local LLMs) to benefit. Allowing them to, in turn, provide context management and other support to more powerful LLMs (perhaps via query and task optimized FITs).

Level 4 is the aspirational standard. Each lower level asks: how close can we get with only the capabilities available?

## Level 0
Unfitted document.

## Level 1: Structural FIT
Document fitted with structural information. Relies on original document author to supply relevant semantics via structural elements in the markdown. Result is an agent navigable document tree that fits size constraints.

Capability level is Mechanical. Utilizes basic markdown and text parsing.

### Level 1.5 Structural FIT with Code Block Optimization
Structural FIT that also utilizes code block annotations supplied by original document author. Relevant programming languages (in a prioritized list) will be given space proximal to the root as space permits.

## Level 2: Weak Semantic FIT
Document fitted with basic text processing. Important elements and summarizing content are identified and inlined/hoisted with basic text processing methods.

Capability level is Low Semantic. Uses classical or passive learned text processing techniques, including: n-gram analysis, lexical analysis and word embeddings.

### Level 2.5: Weak Semantic FIT with Query Optimization
Weak Semantic FIT optimized for access by matches to a small "search query". In addition to the existing prioritization and summarization, text is prioritized for inclusion (root proximity) based on matches to that query.

Unlike higher levels, the query here is a simple search string rather than a full task description — optimization is match-based, not reasoning-based. 

## Level 3: Strong Text FIT
Document fitted with low capability LLM.
Fitted document structure is optimized via LLM. Important elements are identified and summaries are generated by the LLM. Root proximity is determined by the LLM.

Capability level is Moderate Semantic: capable of semantic understanding and summary generation, but operates without full task context or the capacity for deep structural optimization — whether due to context size limits, model capability, or both.

Example models: Gemma 4 E4B (gemma-4-E4B-it-UD-Q4_K_XL.gguf), Qwen3.5 4B (Qwen3.5-4B-UD-Q4_K_XL.gguf)

### Level 3.5: Strong Text FIT with query optimization
Document fitted to query with LLM. Text proximity to root is determined by the LLM based on a shallow query or task description.

Text proximity to root is influenced by query relevance, though the optimization remains bounded by the same capability constraints as Level 3.

## Level 4: Task Optimized FIT
Document is fitted to a specific task via a capable LLM. An LLM is provided with deep task context and constructs the FIT to enable access optimized for the given task. General information and information relevant to earlier task steps is prioritized and included as close to the root node as possible. Later task steps and details are deferred to subdocuments to enable loading only the necessary information as close as possible to its relevant activity. No information is lost. All information is still made available via subdocuments, its proximity to the root is lessened and context load potentially increased based on its percieved relevance to the task. 

Capability level is Strong Semantic: capable of strong semantic understanding and deep structural optimization; adequate context for processing large documents with full task context without suffering significant long context degradation ("lost in the middle" and "context rot" failure modes).

Example models: Gemma 4 26B (gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf),  Devstral Small 2, Qwen3-Coder-30B-A3B

---

## Installation

Requires Python 3.10+. Install into a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

After installation, the `fit` command is available at `.venv/bin/fit`.

---

## Usage

### Threshold configuration

`fit generate` and `fit measure` resolve their soft and hard thresholds
independently for each command-line target:

1. An explicit `--soft-threshold` or `--hard-threshold` flag.
2. The corresponding value in the nearest `.fit.toml`, walking from the
   target's directory toward the filesystem root.
3. The package default: soft `3000`, hard `5000`.

```toml
[thresholds]
soft = 5000
hard = 8000
```

Nested `.fit.toml` files provide per-subtree overrides. Multi-file measurement
resolves each parent directory independently and applies that result to its
files. Recursive generation resolves against its root input once and uses
those values for every generated descendant.
Use `--verbose` to show each effective value and its source. Measurement emits
one threshold line per parent directory because files in one directory share
the same resolution.

An invalid `.fit.toml` is normally a hard error. Supplying both threshold flags
provides an escape hatch: FIT warns, ignores the invalid config, and uses the
fully explicit pair. Both override values must still be valid.

### `fit generate`

Generate a FIT from a markdown file. The file is split in-place; the original is backed up as `<filename>.unfit.md` before any writes.

```
fit generate [options] <path>
```

| Option | Default | Description |
|---|---|---|
| `--level` | `1` | FIT generation level |
| `--soft-threshold` | config or `3000` | Soft token target; triggers splitting |
| `--hard-threshold` | config or `5000` | Hard token ceiling; triggers warnings |
| `--inline-threshold` | `600` | Segments below this are inlined verbatim |
| `--inline-threshold-reduction-increment` | `100` | Amount inline threshold drops per iteration |
| `--trivial-extension-threshold` | `25` | Inline single-paragraph segments within this many tokens of the paragraph |
| `--min-segment-count` | `3` | Minimum segments required to split at a heading level (minimum: 2) |
| `--inline-languages` | `python,javascript,typescript` | Preferred languages for code block priority (comma-separated) |
| `--dry-run` | — | Print planned actions without writing any files |

**Example:**

```bash
# Preview first
.venv/bin/fit generate --dry-run doc/large-document.md

# Then apply
.venv/bin/fit generate doc/large-document.md
```

### `fit measure`

Estimate token counts for Markdown files and check them against their resolved
thresholds. Files and directories may be mixed in one invocation. Directory
arguments are flat by default; use `-r` / `--recursive` to sweep a subtree.
Implicit directory expansion includes `.md` files only and skips generated
backup files.

```
fit measure [options] <path> [<path> ...]
```

| Option | Default | Description |
|---|---|---|
| `--soft-threshold` | config or `3000` | Soft token target |
| `--hard-threshold` | config or `5000` | Hard token ceiling |
| `--recursive`, `-r` | off | Include Markdown files in nested directories |
| `--verbose`, `-v` | off | Show threshold origins and detailed MDX findings |

**Example:**

```bash
.venv/bin/fit measure doc/overview.md
#  2,137 tokens — fits  (doc/overview.md)

.venv/bin/fit measure --recursive docs/ design/
# ...
# Summary: 12 files — 10 fit, 2 over soft, 0 over hard; 31,420 tokens total
```

When any target exceeds its hard threshold, `fit measure` exits with status
`1`. Soft-threshold violations alone do not produce a nonzero exit.

---

## Development

### Project Layout

```
forge/fit/
├── pyproject.toml           # package metadata and entry points
├── src/
│   └── fit/
│       ├── __init__.py      # public API: Measurer, Segment, Document, Writer, ...
│       ├── cli.py           # top-level argument parsing and subcommand dispatch
│       ├── config.py        # shared per-target threshold resolution
│       ├── commands/
│       │   ├── generate/
│       │   │   ├── __init__.py   # generate subcommand args and level dispatch
│       │   │   └── level1.py     # Level 1/1.5 implementation
│       │   └── measure.py        # measure subcommand
│       ├── measurer.py      # Measurer — token count estimation
│       ├── segment.py       # Segment — named document section
│       ├── document.py      # Document — parsing and segmentation
│       ├── writer.py        # Writer, DryRunWriter, WriterFactory
│       └── driver.py        # process_file, _reduction_loop
├── tests/
│   ├── conftest.py          # shared fixtures and helpers
│   ├── test_measurer.py
│   ├── test_segment.py
│   ├── test_document.py
│   ├── test_writer.py
│   └── test_driver.py
├── spec/                    # design documents
└── prototypes/              # exploratory scripts
```

### Running Tests

```bash
.venv/bin/pytest tests/ -q
```

Run a single test file:

```bash
.venv/bin/pytest tests/test_document.py -q
```

### Using the Library

Core classes are importable directly after install:

```python
from fit import Document, Measurer

measurer = Measurer()
doc = Document(text, measurer, soft_threshold=3000)
for segment in doc:
    print(segment.name, segment.measure())
```

### Generating Docs
The griffonner library is used to generate FIT style docs for this project.

```
PYTHONPATH=src .venv/bin/griffonner generate docs/pages/ --output docs/output --template-dir docs/templates
```
If you want live reload while editing templates or page configs:
```
PYTHONPATH=src .venv/bin/griffonner watch docs/pages/ --output docs/output --template-dir docs/templates
```
