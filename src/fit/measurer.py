"""
Measurer — token count estimation.
"""

from __future__ import annotations


class Measurer:
    """Estimate token count from a string. Injected into Document and Segment."""

    TEXT_RATIO: float = 4.0
    CODE_RATIO: float = 3.5

    def measure(self, text: str) -> int:
        """Estimate token count. Uses code ratio if text is a fenced code block.

        Detection: stripped text starts AND ends with three backticks (```) and is not
        exactly "```" (a bare unopened fence). This matches strings that open and close
        with a fence marker.
        """
        if not text:
            return 0
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```") and stripped != "```":
            return int(len(text) / self.CODE_RATIO)
        return int(len(text) / self.TEXT_RATIO)
