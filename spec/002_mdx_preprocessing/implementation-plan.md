# 002 MDX Preprocessing — Implementation Plan

_Updated: 2026-07-13_

## Context

Spec 002 adds a `fit preprocess` subcommand, an aborting MDX guard in
`fit generate`, and warnings in `fit generate` and `fit measure`. All three use
one taxonomy: 10 structural element types and 8 content-wrapper element types.
This plan and spec 002 are authoritative for the feature; the preliminary MDX
Extension notes in historical spec 001 are not implementation instructions.

The prototype proves two useful ideas against a real Mintlify document:
heading-depth context matters, and untouched markdown must be reconstructed from
source ranges rather than normalized from parsed tokens. Its top-level
`html_block` dispatch does not generalize to the full taxonomy, however:
markdown-it-py can place an entire component tree in one `html_block`, while
one-line components commonly appear as `html_inline` children. Production code
therefore uses a source-span component scanner and treats the prototype as
research rather than code to lift.

No `Document` or `Segment` changes are expected. The preprocessor remains an
upstream normalization step.

## Design

### Public surface

Keep a single user-facing `MdxDocument` class in `src/fit/mdx.py`:

- Construction performs a cheap source scan and populates structural,
  content-wrapper, and unknown-component findings.
- `preprocess()` transforms and validates in memory. It performs no filesystem
  writes and raises a domain-specific diagnostic error when safe conversion is
  impossible.
- `summary` is empty until `preprocess()` runs, then contains stable opening-tag
  transformation counts, discarded presentation attributes, and diagnostics.
- `format_findings()` is shared by all three commands.

Internal dataclasses keep scanning and rendering explicit:

- `TagSpec` — name, category, required/semantic attributes, self-closing policy,
  and handler kind.
- `SourceSpan` — start/end character offsets plus line/column information.
- `ComponentNode` — matched open/close spans, parsed attributes, indentation,
  and nested component children.
- `ScanResult` — recognized roots, counts, fenced ranges, unknown components,
  and diagnostics.
- `RenderContext` — active heading depth and scoped step/field state.
- `PreprocessDiagnostic` / `MdxPreprocessError` — stable errors suitable for CLI
  output and unit assertions.

Private scanner and renderer helpers may be separate classes if that makes
state ownership clearer. `MdxDocument` remains the library facade; forcing all
logic into one large class is not a goal.

### Source scanner

The scanner is a dependency-free, single forward pass over source text:

1. Identify backtick and tilde fenced-code extents and exclude their contents
   from component detection. Fence matching follows CommonMark marker character
   and minimum-length rules. Within an indented recognized component, evaluate
   fence indentation relative to that component's common indentation.
2. Outside fences, recognize JSX tag boundaries with a quote-aware character
   walk. Do not use one regex to parse a complete opening tag.
3. Parse supported string and boolean attributes, retaining all attribute names
   for preservation diagnostics.
4. Pair non-self-closing tags with a stack, producing a nested component tree.
5. Diagnose mismatched/unclosed tags, unsupported recognized forms, JSX
   expressions/spreads, mid-line components, and unknown uppercase components.
6. For recognized component roots indented by four or more spaces, compute and
   validate common indentation across the complete extent. Record the amount to
   remove during rendering. Mixed indentation is a hard diagnostic.

Element matching is case-sensitive. Known lowercase `<section>` is recognized;
unknown lowercase tags are raw HTML. Unknown uppercase names are JSX components
and prevent preprocessing from writing.

The cheap guard path uses this scanner but does not invoke markdown-it-py or the
renderer. Scanning remains linear in source length.

### Heading context

After scanning succeeds, create a tag-masked copy of the source: replace JSX
tag characters with spaces while preserving every newline and all body text.
Parsing this copy with markdown-it-py exposes headings that would otherwise be
hidden inside opaque HTML blocks while retaining source line numbers.

Collect heading events from the masked parse and merge them with component
open/close events during rendering. `RenderContext.heading_depth` starts as
`None`; a synthetic heading uses H2 when no heading is active, otherwise one
level below the active heading.

Heading-producing components establish their synthetic depth while rendering
their body. Closing the component restores the containing depth. Ordinary
CommonMark headings inside the body update the active depth within that scope.
At H6, every heading-producing component renders its title as bold paragraph
text instead of emitting H7 or dropping the title, and reports the fallback in
the summary.

### Source-span rendering

Render the component tree recursively. Copy all text outside component tag
spans byte-identically. A handler receives the recursively rendered body, so it
cannot accidentally discard nested components or opaque markdown.

Handlers operate on complete elements rather than isolated open tags:

- Group/transparent wrappers return their rendered body.
- Heading wrappers emit the synthetic heading, then their rendered body.
- Admonitions prefix every output line so blank lines, lists, and fenced code
  remain within the blockquote.
- Steps render the full body as a numbered list item and indent each body line
  by three spaces. The counter is scoped to its containing `<Steps>` node.
- Parameter/response fields render the full body as a bullet entry and indent
  each body line by two spaces. Consecutive same-kind sibling fields, separated
  only by whitespace, form one list.
- Indentation normalization happens on the complete component extent before
  handler-specific indentation is applied.

Do not strip body strings. Helpers should distinguish structural whitespace
introduced by wrappers from whitespace belonging to body content.

### Postcondition validation

After rendering, scan the result again:

- any recognized component is a transformation failure;
- any unknown uppercase JSX component is a transformation failure;
- standard lowercase raw HTML is allowed; and
- JSX-looking text inside fenced code remains ignored.

The postcondition scan runs for normal and `--dry-run` preprocessing. The pure
library method returns text only after it passes.

### Filesystem transaction

`commands/preprocess.py` owns all I/O:

1. Validate that the source exists and is a regular UTF-8 file.
2. Read source, transform, and validate completely in memory.
3. If unchanged, report and return without writing, regardless of whether an
   older backup exists.
4. If a transformation is needed, refuse if the computed backup path exists.
5. Under `--dry-run`, report and return without writing.
6. Write the transformed result to a temporary file in the source directory,
   flush it, and close it.
7. Create the backup with exclusive-create semantics and write the exact
   original bytes.
8. Atomically replace the source with the staged transformed file.
9. If commit fails after creating this invocation's backup, make a best-effort
   rollback by deleting that new backup and retain the original source.

Validation failures occur before step 6 and therefore cannot modify either
path. Same-directory staging makes the final replacement atomic on the target
filesystem.

## Files

### New or already scaffolded

- `src/fit/mdx.py` — replace the placeholder token-walk design with the facade,
  source scanner, tree renderer, taxonomy, findings, and diagnostics above.
- `src/fit/commands/preprocess.py` — argparse and transactional filesystem
  wrapper.
- `tests/test_mdx.py` — revise existing examples to exact-output tests and add
  scanner, nesting, preservation, and failure coverage.
- `tests/test_preprocess_command.py` — command behavior, backup, dry-run,
  collision, validation failure, and atomicity-facing tests.
- `tests/test_mdx_guards.py` — generate/measure warning and abort matrix. This
  may instead be split between existing command test modules if that better
  matches the suite.

### Modified

- `src/fit/cli.py` — register the `preprocess` subparser.
- `src/fit/commands/measure.py` — scan after reading; warn for structural,
  content-wrapper, or unknown JSX findings, then measure normally.
- `src/fit/commands/generate/__init__.py` — add `--force`.
- `src/fit/commands/generate/level1.py` — before constructing the BFS queue,
  scan the root source. Without `--force`, abort for structural or unknown JSX
  findings and warn for content wrappers. The guard must run before any FIT
  backup or output write.

## Implementation phases

Each phase should add focused tests and keep the completed portion green.

1. **Reconcile tests with the spec** — replace substring-only assertions with
   exact expected output for the normative forms. Add explicit failing tests for
   malformed and unsupported input.
2. **Taxonomy and diagnostics** — populate all 18 `TagSpec` entries and define
   stable finding/diagnostic formatting.
3. **Fence-aware scanner** — implement source spans, quoted/boolean attributes,
   unknown detection, stack pairing, and scan-only properties.
4. **Indentation validation** — support consistently indented recognized
   component extents and reject mixed indentation.
5. **Heading events** — mask tag spans, parse headings with markdown-it-py, and
   test scoped depth including H6 behavior.
6. **Transparent and heading handlers** — section, groups, tabs, accordions, and
   cards with recursive body preservation.
7. **Container handlers** — exact multiline admonition, step, parameter-field,
   and response-field rendering.
8. **Postcondition validation** — rescan output and reject recognized/unknown
   JSX survivors.
9. **Preprocess command** — dry-run, unchanged path, collision-safe backup,
   same-directory staging, atomic replacement, and summary.
10. **CLI registration and guards** — implement the complete warning/abort
    matrix and `--force` bypass.
11. **Fixture verification** — copy the primary fixture to a temporary directory,
    run preprocessing there, verify no recognized/unknown JSX remains, then run
    `fit generate` successfully on the transformed copy.

## Verification

```bash
.venv/bin/pytest tests/test_mdx.py -q
.venv/bin/pytest tests/test_preprocess_command.py -q
.venv/bin/pytest tests/test_mdx_guards.py -q
.venv/bin/pytest tests/ -q
```

End-to-end verification must not modify the checked-in prototype fixture. Copy
it and its expected reference to a pytest temporary directory or a shell-created
temporary directory first. Verification should assert properties rather than
requiring byte equality with the prototype output, because the production
taxonomy is broader:

- all recognized components are transformed;
- unknown JSX is absent or produces a nonzero diagnostic;
- the known indented `<CodeGroup>` instances are handled;
- original body sentinel text remains in order;
- a second preprocess reports no changes and creates no new backup; and
- unforced `fit generate` accepts the successful preprocessed result.

## Out of scope

- Recursive preprocessing across linked files
- Downloading source documents
- Conversion rules for unknown JSX components
- JSX expressions, spread attributes, comments inside opening tags, and
  arbitrary JavaScript
- Mixed or inconsistent indentation within an indented component extent
