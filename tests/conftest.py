"""
Shared fixtures and helpers for all fit test modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/fit is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fit.measurer import Measurer
from fit.segment import Segment
from fit.document import Document


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def measurer():
    return Measurer()


@pytest.fixture
def default_args():
    """SimpleNamespace with all defaults from the requirements table."""
    from types import SimpleNamespace
    return SimpleNamespace(
        soft_threshold=3000,
        hard_threshold=5000,
        inline_threshold=600,
        inline_threshold_reduction_increment=100,
        trivial_extension_threshold=25,
        min_segment_count=3,
        inline_languages=["python", "javascript", "typescript"],
        dry_run=False,
    )


@pytest.fixture
def small_args(default_args):
    """Tight thresholds useful for reduction loop and Writer tests."""
    default_args.inline_threshold = 100
    default_args.soft_threshold = 200
    default_args.hard_threshold = 400
    return default_args


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_doc(text: str, args, measurer: Measurer) -> list[Segment]:
    """Call Document.parse and return the result as a list."""
    return Document._parse(
        text,
        measurer,
        soft_threshold=args.soft_threshold,
        hard_threshold=args.hard_threshold,
        inline_threshold=args.inline_threshold,
        inline_threshold_reduction_increment=args.inline_threshold_reduction_increment,
        trivial_extension_threshold=args.trivial_extension_threshold,
        min_segment_count=args.min_segment_count,
        inline_languages=args.inline_languages,
    )


def make_segment(
    blocks: list[str],
    measurer: Measurer,
    is_inline: bool = False,
    heading: str = "## Test",
    body: str = None,
) -> Segment:
    """Construct a Segment directly from a list of raw block strings."""
    if body is None:
        body = heading + "\n" + "".join(blocks)
    return Segment(
        name="test",
        heading=heading,
        body=body,
        blocks=blocks,
        measurer=measurer,
        is_inline=is_inline,
    )


def make_block(chars: int, lang: str = None) -> str:
    """
    Return a block string of approximately `chars` total characters.
    If lang is given, wraps in a fenced code block; `chars` is the TOTAL length including fences.
    For prose (no lang), `chars` is the content length directly.
    """
    if lang is not None:
        fence_open = f"```{lang}\n"
        fence_close = "\n```"
        overhead = len(fence_open) + len(fence_close)
        content_chars = max(0, chars - overhead)
        return f"{fence_open}{'x' * content_chars}{fence_close}"
    else:
        return "x" * chars
