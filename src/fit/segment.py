"""
Segment — a single named section of a document.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fit.measurer import Measurer


class Segment:
    """Encapsulates a single named section of the document."""

    def __init__(
        self,
        name: str,
        heading: str,
        body: str,
        blocks: list[str],
        measurer: "Measurer",
        is_inline: bool,
    ):
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
        """Return True if this block is a fenced code block."""
        stripped = block.strip()
        return stripped.startswith("```") and stripped.endswith("```") and stripped != "```"

    @staticmethod
    def _code_language(block: str) -> Optional[str]:
        """Extract the language from a fenced code block info string. Returns None if not code."""
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
        """Return token estimate. Inline: measure body. Subdoc: return cached tokens."""
        if self.is_inline or complete:
            return self._measurer.measure(self.body)
        return self._cached_tokens

    @property
    def is_empty(self) -> bool:
        """True if block list is empty."""
        return len(self.blocks) == 0

    def is_critical_reduce(self, threshold: int) -> bool:
        """
        Returns True if reducing at this threshold would eliminate all non-code blocks
        (when _had_paragraph) or all code blocks (when _had_code). Does not mutate state.
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
        """
        Remove blocks per priority algorithm until _cached_tokens < threshold.
        Returns _cached_tokens. Returns 0 if threshold is zero or all blocks exhausted.
        No-op if already empty.
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
        """Normalize a language name for comparison."""
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
        """Transition inline segment to subdoc status. Recomputes _cached_tokens from scratch."""
        self.is_inline = False
        self.blocks = list(blocks)
        self._cached_tokens = sum(self._measurer.measure(b) for b in self.blocks)

    def serialize_inline_component(self) -> str:
        """
        Returns heading + inline component (current blocks joined) + subdoc link.
        Token annotation uses measurer.measure(body) — immutable, stable across reduction.
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
