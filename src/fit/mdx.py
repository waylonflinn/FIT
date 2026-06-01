"""
MDX/Mintlify preprocessing.

Detect and convert JSX components in markdown source to standard CommonMark.

Used by three commands:

- ``fit preprocess`` — transforms the document in place
- ``fit generate``   — guard that refuses unprocessed MDX (unless ``--force``)
- ``fit measure``    — warns when MDX tags are detected

Tag taxonomy (from spec 002):

- **structural** — hard blockers; affect split boundaries; ``generate`` aborts
- **content**    — wrappers with minor split impact; ``generate`` only warns

Architecture: a single :class:`MdxDocument` class. Cheap regex-based detection
runs in the constructor; the expensive token-walk transformation is deferred
to :meth:`MdxDocument.preprocess`. This keeps the guard/warning code paths
cheap while sharing a single surface with the preprocess command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Pattern


# ---------------------------------------------------------------------------
# Tag registry
# ---------------------------------------------------------------------------

TagCategory = Literal["structural", "content"]


@dataclass(frozen=True)
class TagSpec:
    """Static description of one MDX tag the preprocessor recognizes.

    The :data:`TAGS` registry below is the single source of truth.
    :class:`MdxDocument` consumes this spec both for scanning (``open_re`` /
    ``close_re`` / ``category``) and for transformation (``handler``).

    Attributes:
        name: Unprefixed tag name (e.g. ``"section"``, ``"CodeGroup"``,
            ``"ParamField"``). Matches the JSX element name.
        category: ``"structural"`` (hard blocker) or ``"content"``
            (warn-only wrapper).
        open_re: Regex matching the opening tag line. Capture groups expose
            attributes the handler uses (title, type, name, required, ...).
        close_re: Regex matching the closing tag line. ``None`` for tags
            with no distinct close form.
        handler: Function invoked by the preprocessor for each occurrence
            of this tag at the top level of the token stream. Receives the
            ``re.Match`` for the opening tag and a :class:`PreprocessContext`
            carrying running state. Returns the replacement markdown text.
            ``None`` if no transformation is defined (the tag is detected
            but passed through unchanged).
    """
    name: str
    category: TagCategory
    open_re: Pattern
    close_re: Pattern | None
    handler: Callable | None = None


TAGS: dict[str, TagSpec] = {}
"""The tag taxonomy from spec 002. Populated by the implementation.

Keys are tag names. The dict is read by :class:`MdxDocument` for both the
constructor's regex scan and :meth:`MdxDocument.preprocess`'s handler dispatch.
"""


# ---------------------------------------------------------------------------
# Preprocessing context
# ---------------------------------------------------------------------------

@dataclass
class PreprocessContext:
    """Running state threaded through tag handlers during preprocessing.

    Handlers are otherwise pure functions; this context carries whatever
    information they need from prior tokens in the stream.

    Attributes:
        heading_depth: Depth (1–6) of the most recent ``heading_open`` token
            in the token stream. Drives synthetic-heading depth for
            ``<section>``, ``<Accordion>``, ``<Card>``.
        step_number: 1-indexed counter for the current ``<Steps>`` block.
            Reset to 1 on each ``<Steps>`` open; incremented on each
            ``<Step>``. Zero when no ``<Steps>`` block is active.
        field_run_tag: Name of the tag (``"ParamField"`` or ``"ResponseField"``)
            for an active run of consecutive field tags being coalesced into
            a single bullet list. ``None`` when no run is active.
    """
    heading_depth: int = 1
    step_number: int = 0
    field_run_tag: str | None = None


# ---------------------------------------------------------------------------
# MdxDocument
# ---------------------------------------------------------------------------

class MdxDocument:
    """An MDX/Mintlify document. Wraps raw text and exposes MDX-specific operations.

    Construction runs a cheap regex scan that populates the tag-count attributes.
    The markdown-it-py parse and token walk are deferred until
    :meth:`preprocess` is called. Callers that only need detection (the guard
    in ``fit generate``, the warning in ``fit measure``) construct the object
    and read the scan attributes without paying the parse cost.

    Attributes:
        text: The raw source text as passed to the constructor.
        structural_tags: Map of tag name → occurrence count for structural
            tags found in :attr:`text`. Empty dict if none. Populated by
            ``__init__``.
        content_wrapper_tags: Map of tag name → occurrence count for
            content-wrapper tags found in :attr:`text`. Empty dict if none.
            Populated by ``__init__``.
        summary: Per-tag transformation count populated by :meth:`preprocess`.
            Empty until :meth:`preprocess` has been called.
    """

    def __init__(self, text: str):
        """Scan ``text`` for MDX tags via regex. Does not parse markdown.

        Populates :attr:`structural_tags` and :attr:`content_wrapper_tags`
        by running each tag's ``open_re`` against the source.

        Args:
            text: Raw markdown/MDX source.
        """
        ...

    @property
    def has_structural_tags(self) -> bool:
        """True if any structural (hard-blocker) tags were found in :attr:`text`."""
        ...

    @property
    def has_content_wrappers(self) -> bool:
        """True if any content-wrapper tags were found in :attr:`text`."""
        ...

    def format_findings(self) -> str:
        """Human-readable list of tags found, grouped by category.

        Used by the ``generate`` guard's abort message and the ``measure``
        warning. Output is stable so it can be asserted against in tests.

        Returns:
            Multi-line string listing each tag name and its count, grouped
            by category. Empty string if no tags of either category were
            found.
        """
        ...

    def preprocess(self) -> str:
        """Convert MDX/Mintlify source to standard CommonMark.

        Parses :attr:`text` with markdown-it-py, walks the top-level tokens
        tracking running state (heading depth, step counter, active
        field-list run), and dispatches each ``html_block`` through the
        :data:`TAGS` registry's handler. Blocks that don't match any
        registered tag pass through byte-identically via line-map slicing.

        Populates :attr:`summary` as a side effect.

        Returns:
            The transformed text. Contains only standard CommonMark — no
            JSX tags from the handled taxonomy. Tags outside the taxonomy
            (and indented tags that markdown-it-py sees as code blocks)
            are left unchanged.
        """
        ...
