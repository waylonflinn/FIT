# DOCUMENTATION.md — Code Documentation Guidelines

Guidelines for writing code documentation. Currently focused on Python docstrings,
but the General Rules apply to any language we work with.

---

## General Rules

### Purpose and Audience

Documentation is for consumers of a class or method — developers and agents who need
to know how to use it, not how it is implemented. Write for someone who cannot see
the source.

### What to include

- What the method does, at a high level
- What arguments mean and what constraints apply
- What the return value contains
- Behavior that would surprise a consumer (edge cases, early exits, warnings emitted)
- For complex methods: outcome-focused description of the algorithm — what gets
  preserved, what gets removed, in what order — without describing the mechanism

### What to exclude

- References to private variables or methods by name. Instead, describe what they
  contain or what they return.
  - ✗ `Returns _cached_tokens after reduction`
  - ✓ `Returns the sum of token counts of all remaining blocks`
- References to how this method is used elsewhere in the codebase. Cross-references
  belong in module-level or library-level documentation, not in method docstrings.
  They create an opening for stale, wrong documentation.
  - ✗ `Used by Writer to assemble the root document`
  - ✓ *(nothing — leave it out)*
- Implementation details that aren't necessary to use the method correctly

### Code smell signal

If a method cannot be documented without referencing private variables or private
methods of another class, that is a code smell. The method probably needs to be
part of a refactor that includes its caller and nearby call sites. Document what
you can, note the smell, and leave it for the refactor.

### Complexity earns detail

Simple methods get simple docstrings. Complex methods with non-obvious behavior
(especially algorithms with ordered steps or priority rules) earn more space. The
measure is whether a consumer genuinely needs to know — not whether it's interesting.

### Args and Returns

Include `Args` and `Returns` sections for all non-trivial methods, including simple
ones where the template will render them. This keeps rendered documentation
consistent and avoids gaps in generated output.

### Markdown in docstrings

Docstrings are rendered as Markdown. Use it:

- Bulleted or numbered lists for steps, options, or ordered behavior
- **Bold** for emphasis on important terms or conditions
- `code spans` for parameter names, values, and type references
- Tables when a list is not sufficient — format them with aligned columns so they
  are legible in the raw docstring as well as rendered

### Review comment convention

After writing a docstring, note things that were considered but omitted in a
separate comment that can be reviewed and deleted or promoted:

```python
# Skipped from docstring:
# - <thing>: <reason it was left out>
```

For bugs or known implementation issues found during documentation, use:

```python
# BUG: <description>
# NOTE: <description of deviation or known issue>
```

---

## Process

1. Read the file
2. Read any relevant design documents or specs
3. Ask clarifying questions — focus on intent and "why", especially for:
   - Magic numbers or constants (empirical? heuristic? validated?)
   - Design decisions that look like bugs but aren't
   - Placeholder implementations vs. final ones
   - Intended extension points
4. Propose the full edit — do not write yet
5. Iterate on accuracy and verbosity with the reviewer
6. Write on explicit confirmation

---

## Python

### Format

Use Google-style docstrings (PEP 257 + Google extensions). Griffe parses these for
documentation generation.

```python
def method(self, arg: str) -> int:
    """One-line summary.

    Longer description if needed.

    Args:
        arg: Description.

    Returns:
        Description of return value.
    """
```

### Where to write docstrings

- **Class:** One-line or short summary of the class's role and responsibility.
  Construction details go in `__init__`, not the class docstring.
- **`__init__`:** Always document, even though it starts with `_`. It is a public
  method. Put the pipeline overview, construction behavior, and all `Args` here.
- **Public methods and properties:** Always document.
- **Private methods (`_name`):** Document when the method has meaningful behavior
  worth capturing. Some implementation detail and private variable references are
  acceptable — use sparingly. Apply the same smell test: if it requires extensive
  private cross-referencing, that is a signal.
- **`__repr__`:** Skip unless non-obvious.

### Attributes

Do not use a class-level `Attributes:` section for constructor parameters. Put them
in `__init__`'s `Args:` section instead. A class-level `Attributes:` section is
appropriate only for attributes that are set outside `__init__` or that have
meaningful public semantics beyond what the constructor documents.

### Properties

Document like methods. Include a one-line summary. Add `Returns:` when the return
value is non-obvious.

### Static methods

Document like instance methods. Callable independently, so a consumer needs the
same information.

### Signatures in rendered output

Long method signatures should be split at argument boundaries in generated
documentation. This is a planned improvement to the Griffonner templates — not
yet implemented.

### Griffe API notes (for documentation generation)

- `obj.docstring.parsed` requires `docstring_parser="google"` set in the page
  frontmatter; without it, all sections come back as raw text
- Attribute descriptions live in the class docstring's `attributes` section, not
  in `obj.attributes`
- `method.signature` is a bound method object — build signature strings manually
  from `method.parameters` and `method.returns`

Reference implementation: `forge/fit/docs/pages/` (page configs) and
`forge/fit/docs/templates/fit/` (Jinja2 templates). See the May 6 daily log for
template design decisions and key Griffe API lessons learned.

### Documentation output format

The Markdown output format is language-agnostic and should be treated as the standard.
Future documentation systems for other languages (TypeScript, etc.) must produce output
in the same format — the same class implemented and documented in two languages should
ideally produce identical Markdown output.

Reference outputs:

- `forge/fit/docs/output/index.md` — module index format
- `forge/fit/docs/output/Segment.md` — class doc format (most complete example)
- Other files in `forge/fit/docs/output/` for additional class examples

When building a documentation generator for a new language, start by diffing its output
against these references before considering it complete.
