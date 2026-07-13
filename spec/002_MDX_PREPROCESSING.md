# FIT Generator — MDX Preprocessing

_Effort: Focused (2)_

_Capability: Compositional (2)_

_Elapsed: ~0d_

_Daily logs: Prototype/Requirements: 2026-04-24.md_

_Status: Requirements (1/10)_

_Requires: 001_

_Updated: 2026-07-13_

---

## Goal

Mintlify documentation sources embed JSX components in markdown. These
components can make large regions opaque to markdown-it-py and prevent FIT from
finding valid split points.

This spec adds a `fit preprocess` subcommand that converts the supported
Mintlify/MDX components to standard CommonMark before generation, a guard in
`fit generate` that rejects unprocessed structural components, and warnings in
`fit generate` and `fit measure` for lower-risk content wrappers. Together they
make the pipeline — download → preprocess → generate — safe and explicit.

This document is authoritative for MDX preprocessing and supersedes the
preliminary MDX Extension notes recorded in spec 001. `Requires: 001` means the
implemented Level 1 pipeline is a prerequisite; it does not make spec 001 part
of this feature's normative requirements.

Preprocessing is a normalization step, not summarization. It must preserve all
human-readable body content and all semantic attributes named in the taxonomy.
Formatting changes required to express that content as CommonMark are allowed;
silent content loss is not.

---

## Requirements

### `fit preprocess <path>`

- Operates on one file in place.
- On a successful transformation, backs up the original as
  `<stem>.orig<suffix>` (`guide.md` → `guide.orig.md`) before replacing it.
- When a transformation is needed, refuses to overwrite an existing backup.
  The source remains unchanged. A clean source may still report "no changes"
  when an older backup exists because it requires no write.
- Writes through a temporary file and atomically replaces the source only after
  preprocessing and postcondition checks succeed.
- If no transformation is needed, reports that result and creates no backup.
- `--dry-run` performs parsing, transformation, validation, and reporting but
  writes neither the backup nor the transformed source.
- Processes every recognized structural and content-wrapper tag outside fenced
  code blocks, including supported tags indented by four spaces.
- On success, no recognized JSX tag or unknown JSX component remains. Standard
  CommonMark raw HTML may remain.
- Prints a stable summary containing opening-tag transformation counts, unknown
  components, and diagnostics.
- On malformed nesting, an unsupported recognized form, an unknown JSX
  component, or a failed postcondition, exits nonzero and leaves the source and
  backup unchanged.

### Preservation invariant

For every successful transformation:

- Wrapper bodies retain their text, ordering, blank lines, fenced code, lists,
  and other markdown. Only indentation or line prefixes needed by the target
  CommonMark construct may change.
- Semantic attributes explicitly named below (`title`, `body`, `name`, `type`,
  and `required`) are rendered into the output rather than discarded.
- Additional attributes explicitly classified as presentation-only by the
  relevant `TagSpec` may be discarded, but their names are reported in the
  summary. Any other unsupported attribute is a diagnostic and prevents the
  write; the implementation must not guess whether an unknown value is
  semantically meaningful.
- Closing wrappers and presentation-only group wrappers contribute no content
  and may be discarded.

### Supported component syntax

The source scanner recognizes components outside fenced code blocks. JSX-like
text inside backtick or tilde fences is literal example content and must not be
detected or transformed.

Supported opening tags may:

- span multiple lines;
- contain attributes in any order;
- use single- or double-quoted string values;
- contain boolean attributes such as `required`; and
- contain additional attributes explicitly allowed by the relevant `TagSpec`,
  subject to the preservation rule above.

Element names are case-sensitive, as in JSX. Each non-self-closing recognized
wrapper must have a correctly nested matching close tag. Self-closing group and
content wrappers are allowed only when they have no body. A self-closing tag
that requires body content is rejected with a diagnostic.

JSX expressions in attribute values, spread attributes, comments within an
opening tag, and tags embedded mid-line in ordinary prose are unsupported in
this iteration. Detection of one of these forms must fail safely rather than
partially rewriting the file.

Unknown JSX components are uppercase element names not present in the taxonomy.
They are detected and reported, but not converted. Their presence prevents a
successful `preprocess` write. Unknown lowercase tags are treated as standard
raw HTML and remain unchanged.

### Tag taxonomy

There are 10 structural element types and 8 content-wrapper element types.

**Structural — hard blockers** (affect split boundaries; `generate` aborts):

| Tag | Handling |
|-----|----------|
| `<section title="...">` | Replace the open tag with a heading one level below the active containing heading; use H2 when no heading is active. Discard the close tag. |
| `<CodeGroup>` | Discard the wrapper and keep its complete body. |
| `<Tabs>` | Discard the group wrapper and keep its complete body. |
| `<Tab title="...">` | Replace the open tag with a heading one level below the active containing heading, preserving `title`; discard the close tag. |
| `<AccordionGroup>` | Discard the group wrapper and keep its complete body. |
| `<Accordion title="...">` | Replace the open tag with a heading one level below the active containing heading; discard the close tag. |
| `<Steps>` | Discard the group wrapper and start a new counter at 1. |
| `<Step title="...">` | Convert the complete element to one numbered list item. Render `title` in bold, then indent every body line as list-item content. |
| `<CardGroup>` | Discard the group wrapper and keep its complete body. |
| `<Card title="...">` | Replace the open tag with a heading one level below the active containing heading. If that would exceed H6, omit the heading marker but emit `title` as bold text. Discard the close tag. |

Synthetic heading depth is determined from the active CommonMark heading and
the recognized wrapper stack, not merely from the last heading token anywhere
in the file. Entering a heading-producing wrapper establishes that synthetic
depth for nested components; leaving it restores the containing depth. When
the active heading is H6, every heading-producing component preserves its title
as bold paragraph text rather than emitting invalid H7 or silently dropping it.

**Content wrappers — warning only in guards:**

| Tag | Handling |
|-----|----------|
| `<Tip>`, `<Note>`, `<Warning>`, `<Info>`, `<Danger>` | Convert the complete element to a blockquote. Emit `> **Type:**`, then prefix every body line (including structural blank lines) so the entire body remains inside the quote. |
| `<Frame>` | Discard the wrapper and keep its complete body. |
| `<ResponseField name="..." type="...">` | Convert to a bullet whose label preserves `name` and `type`; indent the complete body beneath it. Consecutive response fields form one list. |
| `<ParamField body="..." type="..." required>` | Convert to a bullet whose label preserves `body`, `type`, and whether `required` was present; indent the complete body beneath it. Consecutive parameter fields form one list. |

Blank lines between fields do not end a field run. Any intervening non-field
content does. Parameter and response fields are separate runs.

### Normative transformation examples

Admonition bodies remain entirely quoted:

````md
<Note>
First paragraph.

```python
print("preserved")
```
</Note>
````

becomes:

````md
> **Note:**
>
> First paragraph.
>
> ```python
> print("preserved")
> ```
````

Steps preserve multiline bodies as list-item content:

```md
<Steps>
<Step title="Install">
Run the command.

- Keep this nested item.
</Step>
<Step title="Verify">Check the result.</Step>
</Steps>
```

becomes:

```md
1. **Install**

   Run the command.

   - Keep this nested item.

2. **Verify**

   Check the result.
```

Field bodies are never summarized or dropped:

```md
<ParamField body="model" type="string" required>
The model name.

May contain a provider prefix.
</ParamField>
```

becomes:

```md
- **model** (`string`, required)

  The model name.

  May contain a provider prefix.
```

### Consistently indented components

A recognized component block consistently indented by four or more spaces is
not treated as an intentional CommonMark code block. Before component
transformation, remove the common wrapper indentation from the complete
component extent. This covers the known indented `<CodeGroup>` instances in the
primary Mintlify fixture.

Fence recognition inside such a component is relative to the component's
common indentation. An indented fence in its body remains literal fenced-code
content, and JSX-looking examples inside it are neither detected nor converted.

Mixed or inconsistent indentation within such an extent remains unsupported.
It must produce a diagnostic and leave the source unchanged rather than allow a
hard blocker to survive preprocessing.

### Guard behavior

Detection uses the shared source scanner and ignores fenced code. It does not
need a markdown-it-py parse and introduces no additional dependency.

| Command | Structural tags | Content wrappers | Unknown JSX |
|---------|-----------------|------------------|-------------|
| `fit generate` | List findings, recommend `fit preprocess`, exit nonzero | Warn and continue | List findings, recommend `fit preprocess`, exit nonzero |
| `fit generate --force` | Bypass all MDX guard messages and continue | Bypass | Bypass |
| `fit measure` | Warn, then print measurement normally | Warn, then print measurement normally | Warn, then print measurement normally |

The `generate` guard runs before constructing `Document` or writing any backup
or output file.

### Integration constraints

- Scanning, parsing, transformation, findings, and postcondition validation
  live in a shared library module (`fit/mdx.py`) used by `preprocess`,
  `generate`, and `measure`.
- The transformer operates on source spans and recognized wrapper pairs. A
  top-level markdown-it token is not assumed to correspond to one MDX tag.
- markdown-it-py may be used to identify CommonMark heading and fenced-code
  ranges, but it is not the component parser: complete component regions often
  arrive as one `html_block`, while one-line components often arrive as
  `html_inline` children.
- The filesystem wrapper is separate from the pure transformation library.
- Refactors to existing library modules are permitted where they enable clean
  integration. No `Document` or `Segment` change is expected.

### Out of scope

- Recursive preprocessing (only one file at a time)
- Downloading or fetching source documents
- Converting unknown JSX components
- JSX expressions, spread attributes, or arbitrary JavaScript
- Mixed/inconsistent indentation in an indented component extent

---

## Implementation

Detailed design, file-by-file changes, phased order, and verification:

→ [002_mdx_preprocessing/implementation-plan.md](002_mdx_preprocessing/implementation-plan.md)

---

## Research

### Inspiration

- **mdx2md** (`github.com/icyJoseph/mdx2md`) — Rust library for converting MDX
  to standard markdown. This is optional implementation research, not a gate:
  compare its supported syntax and preservation behavior before introducing a
  new dependency or adapting an algorithm.
