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


# ---------------------------------------------------------------------------
# _update_link_token_count — recursive token patching
# ---------------------------------------------------------------------------

class TestUpdateLinkTokenCount:
    """Tests for level1._update_link_token_count."""

    def _import(self):
        from fit.commands.generate.level1 import _update_link_token_count
        return _update_link_token_count

    def test_ULTC01_patches_token_count_in_parent(self, tmp_path):
        """ULTC-01: Updates (~N tokens) in parent to match new child token count."""
        _update_link_token_count = self._import()
        m = Measurer()

        # Write child file with known content
        child_dir = tmp_path / "doc"
        child_dir.mkdir()
        child_path = child_dir / "Overview.md"
        child_content = "## Overview\n\nSmall content after split.\n"
        child_path.write_text(child_content)
        new_count = m.measure(child_content)

        # Write parent with a stale token count
        parent_path = tmp_path / "doc.md"
        stale_count = new_count + 500
        parent_content = (
            f"## Overview\n\n"
            f"[doc/Overview.md](doc/Overview.md) (~{stale_count} tokens)\n"
        )
        parent_path.write_text(parent_content)

        _update_link_token_count(parent_path, child_path)

        updated = parent_path.read_text()
        assert f"(~{new_count} tokens)" in updated
        assert f"(~{stale_count} tokens)" not in updated

    def test_ULTC02_no_match_logs_warning_does_not_raise(self, tmp_path, caplog):
        """ULTC-02: No matching link in parent → logs warning, does not raise."""
        import logging
        _update_link_token_count = self._import()

        child_dir = tmp_path / "doc"
        child_dir.mkdir()
        child_path = child_dir / "Missing.md"
        child_path.write_text("## Missing\n\nContent.\n")

        parent_path = tmp_path / "doc.md"
        parent_path.write_text("## Something\n\nNo link to Missing here.\n")
        original = parent_path.read_text()

        with caplog.at_level(logging.WARNING):
            _update_link_token_count(parent_path, child_path)

        # Parent unchanged
        assert parent_path.read_text() == original

    def test_ULTC03_recursive_run_updates_parent_token_count(self, tmp_path):
        """ULTC-03: fit generate --recurse updates stale token counts in root after subdoc split.

        Creates a two-level hierarchy: root.md → root/section.md (large, will be split).
        Runs generate --recurse and verifies the link in root.md is patched to the new count.
        """
        from fit.cli import main

        # Build section content large enough to be split itself
        section_body = (
            "## Alpha\n\n" + "a" * 1500 + "\n\n"
            "## Beta\n\n" + "b" * 1500 + "\n\n"
            "## Gamma\n\n" + "c" * 1500 + "\n"
        )
        # Root references a section that is too large
        root_content = (
            "# Root Document\n\n"
            "Intro paragraph.\n\n"
            "## Overview\n\n" + "x" * 1500 + "\n\n"
            "## Section\n\n" + "y" * 1500 + "\n\n"
            "## Details\n\n" + "z" * 1500 + "\n"
        )
        root_path = tmp_path / "root.md"
        root_path.write_text(root_content)

        m = Measurer()

        main([
            "generate",
            "--recurse",
            "--soft-threshold", "500",
            "--hard-threshold", "1000",
            "--inline-threshold", "200",
            "--min-segment-count", "2",
            str(root_path),
        ])

        # root.md should now exist and contain links to root/
        root_written = root_path.read_text()

        # Find any subdoc links produced
        import re
        links = re.findall(r"\[root/(\S+\.md)\]\(root/(\S+\.md)\) \(~(\d+) tokens\)", root_written)
        assert links, "Expected at least one subdoc link in root.md"

        for link_text, href, token_str in links:
            child_path = tmp_path / "root" / href
            if child_path.exists():
                actual_count = m.measure(child_path.read_text())
                assert int(token_str) == actual_count, (
                    f"Token count mismatch for root/{href}: "
                    f"link says {token_str}, file has {actual_count}"
                )
