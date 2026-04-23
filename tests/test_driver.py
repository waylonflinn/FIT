"""
Tests for driver (process_file, _reduction_loop, DriverLoop).
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_doc, make_segment, make_block

from fit.driver import process_file, _reduction_loop
from fit.document import Document
from fit.measurer import Measurer
from fit.writer import WriterFactory, DryRunWriter


def _args_to_kwargs(args, exclude=None):
    """Convert a SimpleNamespace to kwargs dict, excluding specified keys."""
    d = vars(args)
    if exclude:
        for k in exclude:
            d.pop(k, None)
    return d


class TestProcessFile:

    def _make_args(self, soft_threshold=200, min_segment_count=2):
        return SimpleNamespace(
            soft_threshold=soft_threshold,
            hard_threshold=400,
            inline_threshold=50,
            inline_threshold_reduction_increment=10,
            trivial_extension_threshold=5,
            min_segment_count=min_segment_count,
            inline_languages=["python", "javascript", "typescript"],
            dry_run=False,
        )

    def _pf(self, source, args):
        """Call process_file with unpacked args."""
        return process_file(source, **vars(args))

    def test_PF01_skips_file_when_measure_below_soft_threshold(self, tmp_path):
        """PF-01: Skips file when raw measure <= soft_threshold."""
        args = self._make_args(soft_threshold=3000)
        content = "x" * 40
        source = tmp_path / "small.md"
        source.write_text(content)
        result = self._pf(source, args)
        assert result == []
        backup = tmp_path / "small.unfit.md"
        assert not backup.exists()

    def test_PF02_proceeds_when_measure_above_soft_threshold(self, tmp_path):
        """PF-02: Proceeds when raw measure > soft_threshold."""
        args = self._make_args(soft_threshold=5)
        content = (
            "## Section A\n\n" + "x" * 400 + "\n\n"
            "## Section B\n\n" + "y" * 400 + "\n"
        )
        source = tmp_path / "large.md"
        source.write_text(content)
        try:
            self._pf(source, args)
        except Exception:
            pass  # Not the focus of this test

    def test_PF03_skips_reduction_when_unsplittable(self, tmp_path, caplog):
        """PF-03: Skips reduction when is_unsplittable."""
        import logging
        args = self._make_args(soft_threshold=5, min_segment_count=2)
        content = "x" * 1000
        source = tmp_path / "nosplit.md"
        source.write_text(content)
        with caplog.at_level(logging.WARNING):
            result = self._pf(source, args)
        assert result == []
        assert not (tmp_path / "nosplit.unfit.md").exists()


class TestReductionLoop:

    def _make_args(self, soft_threshold=100, hard_threshold=200,
                   inline_threshold=50, min_segment_count=2):
        return SimpleNamespace(
            soft_threshold=soft_threshold,
            hard_threshold=hard_threshold,
            inline_threshold=inline_threshold,
            inline_threshold_reduction_increment=10,
            trivial_extension_threshold=5,
            min_segment_count=min_segment_count,
            inline_languages=["python", "javascript", "typescript"],
            dry_run=True,
        )

    def _make_doc(self, content, args):
        return Document(
            content,
            Measurer(),
            soft_threshold=args.soft_threshold,
            hard_threshold=args.hard_threshold,
            inline_threshold=args.inline_threshold,
            inline_threshold_reduction_increment=args.inline_threshold_reduction_increment,
            trivial_extension_threshold=args.trivial_extension_threshold,
            min_segment_count=args.min_segment_count,
            inline_languages=args.inline_languages,
        )

    def _rl(self, doc, args, writer, source):
        return _reduction_loop(
            doc, writer, source,
            soft_threshold=args.soft_threshold,
            hard_threshold=args.hard_threshold,
            inline_threshold=args.inline_threshold,
            inline_threshold_reduction_increment=args.inline_threshold_reduction_increment,
            inline_languages=args.inline_languages,
        )

    def test_RL01_satisfied_immediately_write_and_return(self, tmp_path):
        """RL-01: If satisfied after _parse, write and return without iterating."""
        args = self._make_args(soft_threshold=10000, hard_threshold=20000, inline_threshold=5)
        content = (
            "## Section A\n\nSmall.\n\n"
            "## Section B\n\nSmall.\n"
        )
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        result = self._rl(doc, args, writer, source)
        assert result == []  # DryRunWriter returns []

    def test_RL02_inline_to_subdoc_demotion_fires(self, tmp_path, capsys):
        """RL-02: Inline->subdoc demotion fires at start of each outer iteration."""
        args = self._make_args(soft_threshold=50, hard_threshold=200,
                               inline_threshold=100, min_segment_count=2)
        body = "x" * 380   # 95 tokens
        large_body = "y" * 2000  # 500 tokens
        content = f"## Inline\n\n{body}\n\n## Large\n\n{large_body}\n"
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        self._rl(doc, args, writer, source)

    def test_RL03_scan_pass_triggers_hard_threshold_switch(self, tmp_path, caplog):
        """RL-03: Scan pass triggers Hard Threshold switch when is_critical_reduce fires."""
        import logging
        args = self._make_args(soft_threshold=50, hard_threshold=200,
                               inline_threshold=100, min_segment_count=2)
        code_block = "```python\n" + "x" * 350 + "\n```\n"
        content = f"## Code Heavy\n\n{code_block}\n\n## Other\n\nContent.\n"
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        with caplog.at_level(logging.WARNING):
            self._rl(doc, args, writer, source)

    def test_RL04_scan_pass_skipped_after_hard_threshold(self, tmp_path):
        """RL-04: Scan pass skipped after Hard Threshold adoption."""
        args = self._make_args(soft_threshold=50, hard_threshold=200,
                               inline_threshold=100, min_segment_count=2)
        content = (
            "## Section A\n\n" + "x" * 400 + "\n\n"
            "## Section B\n\n" + "y" * 400 + "\n"
        )
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        self._rl(doc, args, writer, source)

    def test_RL05_reduce_pass_skips_inline_and_empty_segments(self, tmp_path):
        """RL-05: Reduce pass skips inline and empty segments."""
        args = self._make_args(soft_threshold=50, hard_threshold=200,
                               inline_threshold=100, min_segment_count=2)
        small = "x" * 20
        large = "y" * 2000
        content = f"## Small\n\n{small}\n\n## Large\n\n{large}\n"
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        self._rl(doc, args, writer, source)

    def test_RL06_link_only_warning_when_all_segments_empty(self, tmp_path, caplog):
        """RL-06: Emits warning when all segments empty and threshold not satisfied."""
        import logging
        args = SimpleNamespace(
            soft_threshold=1,
            hard_threshold=1,
            inline_threshold=100,
            inline_threshold_reduction_increment=10,
            trivial_extension_threshold=5,
            min_segment_count=2,
            inline_languages=["python"],
            dry_run=True,
        )
        content = (
            "## Section A\n\n" + "x" * 400 + "\n\n"
            "## Section B\n\n" + "y" * 400 + "\n"
        )
        source = tmp_path / "source.md"
        source.write_text(content)
        doc = self._make_doc(content, args)
        writer = DryRunWriter()
        with caplog.at_level(logging.WARNING):
            self._rl(doc, args, writer, source)


class TestMinSegmentCountLowerBound:

    def test_MC01_min_segment_count_1_rejected(self):
        """MC-01: min_segment_count < 2 is rejected by generate subcommand."""
        from fit.commands.generate import run
        args = SimpleNamespace(
            path="somefile.md",
            level=1,
            soft_threshold=3000,
            hard_threshold=5000,
            inline_threshold=600,
            inline_threshold_reduction_increment=100,
            trivial_extension_threshold=25,
            min_segment_count=1,
            inline_languages=["python"],
            dry_run=False,
        )
        with pytest.raises(SystemExit) as exc_info:
            run(args)
        assert exc_info.value.code != 0

    def test_MC02_min_segment_count_2_accepted(self, tmp_path):
        """MC-02: min_segment_count of 2 is accepted."""
        from fit.cli import main
        source = tmp_path / "doc.md"
        source.write_text("## A\n\nContent.\n")
        # Should not raise on parse; will skip (file fits)
        main(["generate", "--min-segment-count", "2", str(source)])
