"""
Segment — a single named section of a document.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fit.measurer import Measurer


class Segment:
    """Named section of a document, with inline/subdoc state and reduction behavior.
    """

    def __init__(
        self,
        name: str,
        heading: str,
        body: str,
        blocks: list[str],
        measurer: "Measurer",
        is_inline: bool,
    ):
        """
        Args:
            name: Slug key; used as filename stem for subdocs.
            heading: Raw heading or ruled line that opens this segment. Included verbatim in ``body``.
            body: Full content for disk write (heading included). Immutable after construction.
            blocks: Content blocks in document order. Empty for inline segments.
            measurer: The Measurer implementation to use for token measurement.
            is_inline: True if segment is rendered verbatim in the root document; False if replaced by a subdoc link.
        """

        self.name = name
        self.heading = heading
        self.body = body  # immutable after construction
        self.blocks = list(blocks)
        self._measurer = measurer
        self.is_inline = is_inline

        # Set from original block list at construction — never mutated
        self._had_paragraph: bool = any(
            not self._is_code_block(b) for b in self.blocks
        )
        self._had_code: bool = any(
            self._is_code_block(b) for b in self.blocks
        )

        # Cached token count — sum over current blocks (0 for inline)
        self._cached_tokens: int = sum(measurer.measure(b) for b in self.blocks)

        # Link overhead: precomputed once (used by Document.measure())
        # Will be set by Document after construction
        self._link_overhead: int = 0

    def __repr__(self) -> str:
        body_len = 20
        body_preview = self.body[:body_len].replace("\n", " ") + ("…" if len(self.body) > body_len else "")
        return f"Segment(name={self.name!r}, heading={self.heading!r}, is_inline={self.is_inline}, body={body_preview!r})"

    @staticmethod
    def _is_code_block(block: str) -> bool:
        """True if block is a fenced code block."""
        stripped = block.strip()
        return stripped.startswith("```") and stripped.endswith("```") and stripped != "```"

    @staticmethod
    def _code_language(block: str) -> Optional[str]:
        """Language identifier from a fenced code block info string. None if not a code block or no language."""
        stripped = block.strip()
        if not (stripped.startswith("```") and stripped.endswith("```") and stripped != "```"):
            return None
        first_line = stripped.split("\n", 1)[0]
        lang = first_line[3:].strip()
        if not lang:
            return None
        # Normalize via pygments if available
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_by_name(lang)
                return lexer.name.lower()
            except ClassNotFound:
                return lang.lower()
        except ImportError:
            return lang.lower()

    def measure(self, complete: bool = False) -> int:
        """Estimated token count for this segment when written.

        For inline segments (or when ``complete=True``), returns token count for entire original text in the segment.
        For subdoc segments, returns only the sum of token counts for remaining blocks (cached after each reduction).

        Args:
            complete: If True, always return token count for entire original text, regardless of inline/subdoc state.

        Returns:
            Estimated token count.
        """
        if self.is_inline or complete:
            return self._measurer.measure(self.body)
        return self._cached_tokens

    @property
    def is_empty(self) -> bool:
        """True if the block list is empty."""
        return len(self.blocks) == 0

    def is_critical_reduce(self, threshold: int) -> bool:
        """True if reducing at this threshold would eliminate the final non-code or final code blocks,
        or if such a reduction has already occured.

        Specifically: True if the segment originally had non-code blocks and reducing would
        leave none, or originally had code blocks and reducing would leave none. Does not
        mutate state.

        Args:
            threshold: Token threshold to test against.

        Returns:
            True if a critical reduction would occur at this threshold.
        """
        if not self._had_paragraph and not self._had_code:
            return False

        if len(self.blocks) == 0:
            # Already empty — past the critical point
            return self._had_paragraph or self._had_code

        non_code_blocks = [b for b in self.blocks if not self._is_code_block(b)]
        code_blocks = [b for b in self.blocks if self._is_code_block(b)]

        paragraph_critical = False
        code_critical = False

        if self._had_paragraph:
            tokens_if_code_removed = sum(
                self._measurer.measure(b) for b in non_code_blocks
            )
            if tokens_if_code_removed >= threshold:
                paragraph_critical = True
            elif len(non_code_blocks) == 1 and self._cached_tokens >= threshold:
                paragraph_critical = False

        if self._had_code:
            tokens_if_prose_removed = sum(
                self._measurer.measure(b) for b in code_blocks
            )
            if tokens_if_prose_removed >= threshold and len(code_blocks) > 0:
                code_critical = True

        return paragraph_critical or code_critical

    def reduce(self, threshold: int, priority_languages: list[str] = None) -> int:
        """Remove blocks until the remaining token count falls below ``threshold``.

        Applies a six-step priority algorithm. Removes blocks one by one, stopping as
        soon as the token count drops below the threshold.

        Block removal order:
            1. Non-priority code blocks, in reverse document order.
            2. Priority code blocks trimmed to one per language, processing languages
               in reverse priority order (lowest first). Keeps the first document-order
               occurrence of each language.
            3. Priority code blocks removed in reverse priority order until only the
               highest-priority language remains.
            4. Non-code blocks removed in reverse document order until one remains.
            5. The final code block.
            6. All remaining blocks cleared; returns 0.

        Args:
            threshold: Target token count (exclusive upper bound).
            priority_languages: Programming languages to preserve longest, ordered by priority
                (index 0 = highest priority). Defaults to no priority languages.

        Returns:
            Sum of token counts of all remaining blocks, or 0 if threshold could not be reached.
        """
        if threshold == 0:
            self.blocks = []
            self._cached_tokens = 0
            return 0

        if not self.blocks:
            return 0

        if self._cached_tokens < threshold:
            return self._cached_tokens

        langs = priority_languages or []

        def _remove_block(idx: int) -> None:
            """Remove block at idx and delta-update _cached_tokens."""
            removed = self.blocks.pop(idx)
            self._cached_tokens -= self._measurer.measure(removed)

        def _satisfied() -> bool:
            return self._cached_tokens < threshold

        # Build set of normalized priority language names for fast lookup
        normalized_priority = set(self._normalize_lang(pl) for pl in langs)

        def _is_priority_code(block: str) -> bool:
            if not self._is_code_block(block):
                return False
            lang = self._code_language(block)
            if lang is None:
                return False
            return lang in normalized_priority

        # Step 1: Remove non-priority code blocks in reverse document order
        i = len(self.blocks) - 1
        while i >= 0:
            b = self.blocks[i]
            if self._is_code_block(b) and not _is_priority_code(b):
                _remove_block(i)
                if _satisfied():
                    return self._cached_tokens
            i -= 1

        # Step 2: Trim priority code to one-per-language, processing lowest priority first.
        # BUG: Design specifies keeping the first document-order occurrence (i.e. removing
        # from the end, highest index first). This loop removes lang_indices[-1] (the
        # highest index / last occurrence) first, then pops it — leaving lang_indices[0]
        # (the first occurrence) as the survivor. That matches the spec. However, removal
        # of lang_indices[-1] shifts indices for all blocks after it; lang_indices is not
        # rebuilt after each removal, so subsequent idx_to_remove values may be stale if
        # blocks between them were removed in an earlier step. Low risk in practice (step 1
        # only removes non-priority blocks), but worth verifying.
        for lang in reversed(langs):
            lang_norm = self._normalize_lang(lang)
            lang_indices = [
                idx for idx, b in enumerate(self.blocks)
                if self._is_code_block(b) and self._code_language(b) == lang_norm
            ]
            while len(lang_indices) > 1:
                idx_to_remove = lang_indices[-1]
                _remove_block(idx_to_remove)
                if _satisfied():
                    return self._cached_tokens
                lang_indices.pop()

        # Step 3: Remove priority code blocks in reverse priority order until only highest remains.
        for lang in reversed(langs[1:]):
            lang_norm = self._normalize_lang(lang)
            lang_indices = [
                idx for idx, b in enumerate(self.blocks)
                if self._is_code_block(b) and self._code_language(b) == lang_norm
            ]
            for idx in sorted(lang_indices, reverse=True):
                _remove_block(idx)
                if _satisfied():
                    return self._cached_tokens

        # Step 4: Remove non-code blocks in reverse document order until one non-code block remains.
        while True:
            non_code_indices = [
                idx for idx, b in enumerate(self.blocks) if not self._is_code_block(b)
            ]
            if len(non_code_indices) <= 1:
                break
            idx = non_code_indices[-1]
            _remove_block(idx)
            if _satisfied():
                return self._cached_tokens

        # Step 5: Remove the final code block (if any).
        # NOTE: Design specifies a single code block remains at this point. The loop
        # handles 0 or 1 correctly but would silently over-remove if the invariant broke.
        code_indices = [idx for idx, b in enumerate(self.blocks) if self._is_code_block(b)]
        for idx in sorted(code_indices, reverse=True):
            _remove_block(idx)
            if _satisfied():
                return self._cached_tokens

        # Step 6: Nothing satisfied threshold — clear everything and return 0.
        self.blocks = []
        self._cached_tokens = 0
        return 0

    @staticmethod
    def _normalize_lang(lang: str) -> str:
        """Normalize a language name for comparison via pygments. Falls back to lowercasing."""
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_by_name(lang)
                return lexer.name.lower()
            except ClassNotFound:
                return lang.lower()
        except ImportError:
            return lang.lower()

    def demote_to_subdoc(self, blocks: list[str]) -> None:
        """Transition this segment from inline to subdoc status.

        Sets ``is_inline = False``, replaces ``blocks``, and recomputes ``_cached_tokens``
        from scratch. Caller is responsible for producing ``blocks`` from ``body``
        (typically via ``Document._parse_segment(segment.body)``).

        Args:
            blocks: Parsed content blocks for this segment's body.
        """
        self.is_inline = False
        self.blocks = list(blocks)
        self._cached_tokens = sum(self._measurer.measure(b) for b in self.blocks)

    def serialize_inline_component(self) -> str:
        """Inline portion of the root document entry for a subdoc segment.

        Returns the current blocks (the inline component after reduction) joined together,
        followed by a subdoc link with a token annotation. If all blocks have been removed,
        emits just the heading and link. The Token count annotation is derived from the
        segment's original contents.

        Returns:
            Heading + inline content + subdoc link, ready to splice into the root document.
        """
        token_count = self._measurer.measure(self.body)
        link = f"[{self.name}.md]({self.name}.md) (~{token_count} tokens)\n"
        if self.blocks:
            inline_content = "".join(self.blocks)
            if not inline_content.endswith("\n"):
                inline_content += "\n"
            return inline_content + link
        else:
            # Fully reduced: emit just the heading + link
            heading_line = self.heading
            if not heading_line.endswith("\n"):
                heading_line += "\n"
            return heading_line + link
