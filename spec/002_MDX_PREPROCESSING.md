# FIT Generator — MDX Preprocessing

_Effort: Focused (2)_

_Capability: Compositional (2)_

_Elapsed: ~0d_

_Daily logs: Prototype/Requirements: 2026-04-24.md_

_Status: Requirements (1/10)_

_Requires: 001_

_Updated: 2026-04-24_

---

## Goal

Mintlify documentation sources embed JSX components in markdown that the FIT generator cannot split correctly — structural tags create opaque token boundaries that prevent valid split points from being found. This spec adds a `fit preprocess` subcommand that normalizes Mintlify/MDX documents to standard CommonMark before generation, a guard in `fit generate` that detects and rejects unprocessed documents, and a softer warning in `fit measure`. Together these make the full pipeline — download → preprocess → generate — safe and explicit.

---

## Requirements

### `fit preprocess <path>`

- Operates in-place. Backs up the original as `<basename>.orig.md` before writing.
- Processes all structural tags (hard blockers) and content-wrapper tags.
- After preprocessing, the output file contains only standard CommonMark markdown — no JSX components.
- Prints a summary of transformations applied (tag counts per type).

### Tag taxonomy

Two categories, matching the Extension in 001:

**Structural — hard blockers** (affect split boundaries; `generate` aborts on detection):

| Tag | Handling |
|-----|----------|
| `<section title="...">` / `</section>` | Convert open to heading at depth+1 relative to nearest preceding heading; discard close |
| `<CodeGroup>` / `</CodeGroup>` | Discard wrapper; keep content blocks |
| `<Tabs>` / `</Tabs>` | Discard wrapper; keep tab content blocks |
| `<Tab title="...">` / `</Tab>` | Discard wrapper; keep content |
| `<AccordionGroup>` / `</AccordionGroup>` | Discard group wrapper |
| `<Accordion title="...">` / `</Accordion>` | Convert open to heading at depth+1; discard close |
| `<Steps>` / `</Steps>` | Discard wrapper |
| `<Step title="...">` / `</Step>` | Convert open to numbered list item; discard close |
| `<CardGroup>` / `</CardGroup>` | Discard group wrapper |
| `<Card title="...">` / `</Card>` | Convert open to heading at next lower level (cap at H6, drop heading if already H6); discard close |

**Content wrappers — warn only** (unlikely to affect split quality; `generate` warns but does not abort):

| Tag | Handling |
|-----|----------|
| `<Tip>`, `<Note>`, `<Warning>`, `<Info>`, `<Danger>` | Convert to blockquote with bold label: `> **Note:** ...` |
| `</Tip>`, `</Note>`, `</Warning>`, `</Info>`, `</Danger>` | Discard close |
| `<Frame>` / `</Frame>` | Discard wrapper; keep content |
| `<ResponseField>` / `</ResponseField>` | Best-effort conversion (TBD at design time) |
| `<ParamField>` / `</ParamField>` | Best-effort conversion (TBD at design time) |

### Guard in `fit generate`

- Before constructing `Document`, scan raw text for structural tag patterns.
- If any structural tag is found: print the tags found, recommend `fit preprocess`, exit nonzero.
- `--force` bypasses the guard entirely.
- Detection is regex against raw text (no parsing) — fast, no extra dependencies.

### Guard in `fit measure`

- If structural tags are detected: print a warning that token counts may be slightly inaccurate.
- Continue with measurement and print results normally.
- No `--force` required.

### Integration constraints

- Tag detection logic lives in a shared module (`fit/mdx.py`) used by `preprocess`, `generate`, and `measure`.
- The preprocessor is implemented as a proper library module integrated with existing `fit` patterns — not a transplant of the prototype code. Prototype findings (token-walk approach, heading depth tracking, line_map reconstruction, indented-tag discovery) inform the design; the prototype code is fungible.
- Refactors to existing library modules are permitted where they enable clean integration.

### Known issue (deferred)

Tags indented by 4 spaces are parsed by markdown-it-py as `code_block` content and are invisible to the token walker. Discovered in prototype with two `<CodeGroup>` instances in `prompt-caching.md`. Correct fix is a source-level pre-pass that de-indents the block before parsing. This is out of scope for this spec — tracked as an Extension.

### Out of scope

- Recursive preprocessing (only one file at a time)
- Downloading or fetching source documents
- Any tag not listed in the taxonomy above
- Handling mixed/inconsistent indentation in the de-indent pre-pass (deferred Extension)

---

## Research

### Inspiration

- **mdx2md** (`github.com/icyJoseph/mdx2md`) — Rust library for converting MDX to standard markdown. Investigate: what tags does it handle, what's the conversion approach, is there anything reusable or worth adapting into the Python implementation?

