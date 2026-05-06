"""
Measurer — token count estimation.
"""

from __future__ import annotations


class Measurer:
    """Character-based token count estimator.

    A lightweight approximation; does not depend on a real tokenizer.
    This simple implementation is a functional placeholder for a more accurate estimator.

    Attributes:
        TEXT_RATIO: Characters per token for prose. Rule-of-thumb; not validated.
        CODE_RATIO: Characters per token for code. Lower than TEXT_RATIO; code is typically denser.
    """

    TEXT_RATIO: float = 4.0
    CODE_RATIO: float = 3.5

    def measure(self, text: str) -> int:
        """Estimate the token count of a string.

        Uses CODE_RATIO for fenced code blocks, TEXT_RATIO otherwise.
        Code blocks are detected by heuristic, so mixed-content strings are treated as prose.

        Args:
            text: The string to estimate.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```") and stripped != "```":
            return int(len(text) / self.CODE_RATIO)
        return int(len(text) / self.TEXT_RATIO)
