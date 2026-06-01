# 002 MDX Preprocessing — Implementation Plan

_Updated: 2026-05-26_

## Context

Spec 002 adds three things on top of the existing FIT pipeline: a `fit preprocess` subcommand, a guard in `fit generate` that refuses unprocessed MDX, and a softer warning in `fit measure`. All three need the same detection logic and share a tag taxonomy (14 structural + 7 content-wrapper tags). The prototype at `prototypes/mdx_preprocessor/mdx_preprocessor.py` already proves the token-walk + line-map approach against a real Mintlify document (`prompt-caching.md`), but covers only `<section>` and `<CodeGroup>` and is structured as a script — it's a reference, not a transplant.

The goal of this work is to ship the spec as a clean library module that the three commands share, with no required changes to `Document` or `Segment`.

## Design

**Single `MdxDocument` class** in `src/fit/mdx.py`:

- Constructor runs a cheap regex scan over the source and populates `structural_tags` / `content_wrapper_tags`. No markdown-it-py parse here — the `generate` guard and `measure` warning pay only the regex cost.
- `preprocess()` runs the markdown-it-py token walk and applies handlers. Deferred until called, so callers that don't need it don't pay for it.
- A module-level `TAGS: dict[str, TagSpec]` registry is the single source of truth, consumed both by the constructor's scan and by `preprocess`'s dispatch.
- A `PreprocessContext` dataclass threads running state (heading depth, step counter, active `<ParamField>` / `<ResponseField>` list run) through pure handler functions.

**`<ParamField>` / `<ResponseField>` handling: Option C (coalesced bullets).** Consecutive field tags become a single bullet list; the `field_run_tag` field on `PreprocessContext` marks the active run so the handler knows when to open and close it. Single-paragraph bodies fit naturally; multi-paragraph bodies are emitted as a bullet entry followed by indented continuation paragraphs (best-effort — the spec permits some loss).

**No required `Document` or `Segment` changes.** The preprocessor sits upstream of `Document` construction; `Document` only ever sees CommonMark. The prototype's `top_level_tokens` and line-map slice helpers do conceptually overlap with `Document._parse_segment`, but the two have different outputs (text reconstruction vs. block list). Bundling them into a shared utility is YAGNI today; flag it as a candidate refactor only if a third caller appears.

## Files

**New:**

- `src/fit/mdx.py` — `MdxDocument`, `TagSpec`, `TAGS`, `PreprocessContext`, per-tag handlers. Skeleton already in place; fill in implementations.
- `src/fit/commands/preprocess.py` — argparse + I/O wrapper. Skeleton already in place.
- `tests/test_mdx.py` — class-level tests for scan + preprocess. Already in place; will pass once `mdx.py` is implemented.
- `tests/test_preprocess_command.py` — single smoke test: writes `<name>.orig.md` backup, overwrites the source, prints a summary. To be added.

**Modified:**

- `src/fit/cli.py` — register the `preprocess` subparser (one import + one call, matching the existing `generate` / `measure` wiring on lines 20–24).
- `src/fit/commands/measure.py` — after reading text, construct `MdxDocument(text)`; if `has_structural_tags` or `has_content_wrappers`, print the findings as a warning before the normal token-count line. No `--force` flag, no abort.
- `src/fit/commands/generate/__init__.py` — add `--force` boolean argument.
- `src/fit/commands/generate/level1.py` — before the BFS queue is constructed, read the root path's text, construct `MdxDocument(text)`; if `has_structural_tags` and not `args.force`, print findings + recommendation, raise `SystemExit(1)`.

## Existing methods to reuse

- `markdown_it.MarkdownIt().parse(source)` — already used by `Document`; the preprocessor uses the same parser for its token stream.
- `fit.measurer.Measurer` — optional, for an informational before/after token count in the preprocess summary.
- The `add_parser` / `run` convention from `src/fit/commands/measure.py` and `src/fit/commands/generate/__init__.py`. The new `preprocess.py` follows the same shape.
- The prototype at `prototypes/mdx_preprocessor/mdx_preprocessor.py` is the reference implementation for the token walk, line-map reconstruction (`lines[token.map[0]:next_top.map[0]]`), and the heading-depth tracking pattern. Lift the algorithm; rewrite the structure into the registry+handlers shape.

## Implementation phases

Roughly the order to fill things in. Each phase keeps the test suite green where it can.

1. **Registry skeleton** — populate `TAGS` with all 21 tags (14 structural + 7 content-wrapper), each with `open_re` / `close_re` and a `handler=None` placeholder where the handler isn't yet written. Constructor's scan can be fully implemented at this point.
2. **Scanning** — implement `__init__`, `has_structural_tags`, `has_content_wrappers`, `format_findings`. `TestScan` in `tests/test_mdx.py` should pass after this phase.
3. **Handlers (structural)** — implement handlers for `<section>`, `<CodeGroup>`, `<Tabs>`/`<Tab>`, `<Accordion>`/`<AccordionGroup>`, `<Steps>`/`<Step>`, `<Card>`/`<CardGroup>`. Heading-depth and step-counter logic comes from `PreprocessContext`.
4. **Handlers (content)** — `<Tip>` / `<Note>` / `<Warning>` / `<Info>` / `<Danger>` → blockquote with bold label. `<Frame>` → discard wrapper. `<ParamField>` / `<ResponseField>` → coalesced bullet list (uses `field_run_tag` on the context).
5. **Token walk** — implement `preprocess()`: parse with markdown-it-py, walk top-level tokens, classify each `html_block` against the registry, dispatch to the handler with the current context, reconstruct text via line-map slicing for non-tag blocks. Update `summary` per dispatch.
6. **`preprocess` command** — flesh out `add_parser` (path arg, `--dry-run`, `--verbose`) and `run` (read → MdxDocument → preprocess → backup → overwrite → print summary).
7. **CLI registration** — wire `preprocess` into `cli.py`.
8. **Generate guard** — add `--force` to `commands/generate/__init__.py`; add the pre-queue check in `commands/generate/level1.py`.
9. **Measure warning** — add the pre-measure check in `commands/measure.py`.
10. **End-to-end verification** — run against `prototypes/mdx_preprocessor/prompt-caching.md`; diff the output against the existing `.preprocessed.md` reference (expect differences from the new tags handled, but the `<section>` and `<CodeGroup>` transformations should match).

## Verification

```bash
.venv/bin/pytest tests/test_mdx.py -q                # unit tests for MdxDocument
.venv/bin/pytest tests/ -q                           # full suite (no regressions in existing tests)

# End-to-end smoke against the prototype's known-good input
.venv/bin/fit preprocess prototypes/mdx_preprocessor/prompt-caching.md
diff prototypes/mdx_preprocessor/prompt-caching.md \
     prototypes/mdx_preprocessor/prompt-caching.preprocessed.md   # transformations should overlap

# Guard behavior
.venv/bin/fit generate prototypes/mdx_preprocessor/prompt-caching.orig.md  # expect: abort, listing tags
.venv/bin/fit generate --force prototypes/mdx_preprocessor/prompt-caching.orig.md  # expect: proceed

# Measure warning
.venv/bin/fit measure prototypes/mdx_preprocessor/prompt-caching.orig.md   # expect: warning, then count
```

## Out of scope (carried from spec 002)

- Indented tags (4-space code blocks). markdown-it-py parses them as `code_block` content; the token walker doesn't see the tag. Source-level de-indent pre-pass is deferred as an Extension.
- Recursive preprocessing across linked files.
- Tags outside the 21-tag taxonomy.
