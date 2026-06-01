# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`fit` turns a large Markdown file into a **Fitted Information Tree (FIT)**: a root document (≤ soft threshold tokens) that links to subdocuments, recursively, until every node fits. It is *not* a summarizer — all original content is preserved, just relocated across files. See `README.md` for the FIT *concept* and the **Level 0–4** taxonomy; only **Level 1 / 1.5** (mechanical split, no LLM) is implemented today.

## Commands

```bash
# install into a venv (Python 3.10+)
python3 -m venv .venv
.venv/bin/pip install -e .

# generate / measure
.venv/bin/fit generate [--dry-run] [--level 1] [-s 3000] [-t 5000] [-i 600] <path>
.venv/bin/fit measure <path>

# tests
.venv/bin/pytest tests/ -q
.venv/bin/pytest tests/test_document.py -q          # single file
.venv/bin/pytest tests/test_document.py::test_foo   # single test

# regenerate API docs (output is FIT-structured)
PYTHONPATH=src .venv/bin/griffonner generate docs/pages/ --output docs/output --template-dir docs/templates
```

`fit generate` writes in place. It backs up the original to `<name>.md.unfit` (root only — recursed subdocs are *not* backed up) before overwriting.

## Architecture

The pipeline is **Measurer → Document → driver._reduction_loop → Writer**, with the filesystem itself acting as the tree's data structure (intermediate files are written eagerly, then recursed on).

- **`measurer.py`** — `Measurer` is a deliberately crude `chars/4` (prose) or `chars/3.5` (fenced code) estimator. It's injected into Documents and Segments; replacing it with a real tokenizer is the obvious upgrade path.
- **`document.py`** — `Document.__init__` runs the full Level-1 parse: pick a segmentation target (heading level → ruled lines → …), partition, name each part (heading text slug, or numbered fallback), classify each as `inline` or `subdoc` based on `inline_threshold`, then split subdoc bodies into ordered `blocks` (paragraphs / code fences) for later reduction.
- **`segment.py`** — `Segment` owns its own reduction. `reduce()` drops blocks one at a time according to a priority (code-block language preference from `--inline-languages`, position, last-of-type protection). `is_critical_reduce()` flags when the next reduction would eliminate the last prose *or* last code block from a segment that originally had both — this is what causes the loop to abandon the soft threshold.
- **`driver.py`** — `_reduction_loop` is the heart of the algorithm. Each iteration: (1) **demote** any inline segment that has grown past the current inline threshold into a subdoc, (2) **scan** for `is_critical_reduce`; if found, permanently switch from `soft_threshold` to `hard_threshold`, (3) **reduce** every non-empty subdoc segment to the current inline threshold, then decrement that threshold by `inline_threshold_reduction_increment` and loop. Terminates when `doc.is_satisfied()`, when all segments are link-only, or when the inline threshold hits zero. **Known smell** flagged in the code itself: the demotion step reaches into `Segment._measurer` and `Document._parse_segment` — refactor candidate, leave alone unless asked.
- **`writer.py`** — `Writer` / `DryRunWriter` / `WriterFactory`. The root is rewritten as inline-segment bodies interleaved with `[name](folder/name.md) (~N tokens)` links; subdocs go in a folder named after the source file's stem.
- **`commands/`** — `cli.py` just wires `argparse` subparsers. `commands/generate/__init__.py` validates args and dispatches by `--level` to `level1.py` (the only implementation). `commands/measure.py` is a thin wrapper over `Measurer`.

### Key invariants worth knowing before editing

- **The root is not special** — it is processed by the same `process_file` as any subdoc. `is_root` / `backup` only controls whether the `.unfit` backup is written.
- **Recursion is "write then re-invoke"**, not in-memory. If you're tempted to hold the full tree in memory, re-read the README's "filesystem is the data structure" insight first.
- **Two-tier budget** — `soft_threshold` is the target. `hard_threshold` is only adopted mid-loop, and only when a critical reduce is detected; the switch is sticky.
- **`--min-segment-count` ≥ 2** is enforced at CLI startup; 1 would allow infinite recursion.
- **Out of scope (per spec)**: YAML/TOML frontmatter, raw HTML, non-UTF-8, watch mode, batch processing.

## Where to look for context

- **`docs/output/index.md`** — agent-readable API documentation, itself structured as a FIT. The root indexes every public class with file paths and line-number ranges; per-class subdocuments (`Measurer.md`, `Segment.md`, `Document.md`, …) give detailed line references for individual properties and methods as well as descriptions of their functionality. Read this instead of the actual code (when sufficient) to limit impact on context.
- `DOCUMENTATION.md` — how to write and update documentation. Read before writing or updating docstrings in the code.
- `README.md` — concept, FIT levels, CLI surface.
- `spec/001_BASIC_MECHANICAL.md` (+ `spec/001_basic_mechanical/`) — design rationale and requirements for the current Level-1 implementation.
- `spec/002_MDX_PREPROCESSING.md` — next planned feature (MDX support).
- `SCORING.md` — proposed (not yet implemented) DP/knapsack scoring model that would replace the current greedy `reduce()`.
- `FEEDBACK.md` — honest project assessment; useful for understanding which directions the author actually cares about.
- `prototypes/` — exploratory scripts; not on the import path. DO NOT READ THE FILES AT `prototypes/mdx_preprocessor/prompt-caching.md` AND `prototypes/mdx_preprocessor/prompt-caching.preprocessed.md`. THESE FILES ARE TOO LARGE AND WILL BLOAT CONTEXT, THUS MAKING YOU LESS EFFECTIVE. THEY ARE TEST DOCUMENTS AND THEIR CONTENTS ARE NOT DIRECTLY RELEVANT TO THIS TASK.
