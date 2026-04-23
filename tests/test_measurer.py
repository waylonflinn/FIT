"""
Tests for Measurer.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_doc, make_segment, make_block

from fit.measurer import Measurer


class TestMeasurer:

    def test_M01_plain_text(self, measurer):
        """M-01: Plain text token estimate — 400 chars -> 100 tokens."""
        text = "a" * 400
        assert measurer.measure(text) == 100

    def test_M02_code_block(self, measurer):
        """M-02: Code block token estimate — full string as code block -> chars / 3.5."""
        text = "```python\n" + "x" * 350 + "\n```"
        expected = int(len(text) / 3.5)
        assert measurer.measure(text) == expected

    def test_M03_mixed_content_uses_text_ratio(self, measurer):
        """M-03: Mixed content uses text ratio (not code ratio)."""
        text = "Some prose.\n\n```python\nx = 1\n```\n\nMore prose."
        expected = len(text) // 4
        assert measurer.measure(text) == expected

    def test_M04_empty_string(self, measurer):
        """M-04: Empty string returns 0."""
        assert measurer.measure("") == 0

    def test_M05_bare_fence_open_only(self, measurer):
        """M-05: String starting with fence but not ending with fence uses text ratio."""
        text = "```python\nsome code\n"
        expected = len(text) // 4
        assert measurer.measure(text) == expected


# ---------------------------------------------------------------------------
# Segment — Construction and Basic Properties
