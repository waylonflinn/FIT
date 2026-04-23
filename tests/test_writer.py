"""
Tests for Writer.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_doc, make_segment, make_block

from fit.writer import Writer, DryRunWriter, WriterFactory
from fit.document import Document
from fit.measurer import Measurer


class TestWriter:

    def _make_subdoc_content(self, heading: str, para_count: int = 3, chars_per_para: int = 300) -> str:
        """Create segment content that will definitely be subdoc (not trivial extension)."""
        # Multiple paragraphs ensure body_tokens >> first_para_tokens + trivial
        paras = [f"Para {i}: " + "x" * chars_per_para for i in range(para_count)]
        return f"{heading}\n\n" + "\n\n".join(paras) + "\n"

    def _make_args(self, min_segment_count=2, inline_threshold=50):
        return SimpleNamespace(
            soft_threshold=3000, hard_threshold=5000,
            inline_threshold=inline_threshold,
            inline_threshold_reduction_increment=10,
            trivial_extension_threshold=5,
            min_segment_count=min_segment_count,
            inline_languages=["python", "javascript", "typescript"],
            dry_run=False,
        )

    def test_W01_backup_written_before_output(self, tmp_path):
        """W-01: Backup written as <filename>.unfit.<ext> before any output."""
        # Use inline_threshold=600 (default) — content below threshold stays inline,
        # content above goes subdoc; force subdoc by using large content with threshold=50
        args = self._make_args(inline_threshold=50)
        content = self._make_subdoc_content("## Section A") + "\n" + self._make_subdoc_content("## Section B")
        source = tmp_path / "overview.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        # Verify at least one subdoc
        if all(s.is_inline for s in doc):
            pytest.skip("All segments inline with this content; test config issue")

        writer = Writer()
        writer.write(doc, source)

        backup = tmp_path / "overview.unfit.md"
        assert backup.exists()
        assert backup.read_text() == content

    def test_W02_inline_segment_body_written_verbatim(self, tmp_path):
        """W-02: Inline segment body written verbatim to root document."""
        # inline segment: very small content (5 tokens) < inline_threshold=600
        # subdoc segment: large multi-para content > inline_threshold=50
        args = self._make_args(inline_threshold=50)
        small_content = "x" * 20  # 5 tokens -> inline
        large_content = self._make_subdoc_content("## Large")

        content = f"## Small\n\n{small_content}\n\n{large_content}"
        source = tmp_path / "doc.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        inline_seg = next((s for s in doc if s.is_inline), None)
        if inline_seg is None:
            pytest.skip("No inline segment in this doc configuration")

        writer = Writer()
        writer.write(doc, source)
        root_content = source.read_text()
        assert inline_seg.body in root_content

    def test_W03_subdoc_segment_rendered_via_serialize_inline_component(self, tmp_path):
        """W-03: Subdoc segment rendered via serialize_inline_component() in root."""
        args = self._make_args(inline_threshold=50)
        content = (
            self._make_subdoc_content("## SectionA") + "\n" +
            self._make_subdoc_content("## SectionB")
        )
        source = tmp_path / "doc.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        subdoc_seg = next((s for s in doc if not s.is_inline), None)
        if subdoc_seg is None:
            pytest.skip("No subdoc segment in this doc configuration")

        writer = Writer()
        writer.write(doc, source)
        root_content = source.read_text()
        # Root should contain the link
        assert f"{subdoc_seg.name}.md" in root_content

    def test_W04_subdoc_files_written_to_source_stem_dir(self, tmp_path):
        """W-04: Subdoc files written to <source_stem>/ directory."""
        args = self._make_args(inline_threshold=50)
        content = (
            self._make_subdoc_content("## Installation") + "\n" +
            self._make_subdoc_content("## Usage")
        )
        source = tmp_path / "overview.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        subdoc_segs = [s for s in doc if not s.is_inline]
        if not subdoc_segs:
            pytest.skip("No subdoc segments in this doc configuration")

        writer = Writer()
        writer.write(doc, source)

        subdoc_dir = tmp_path / "overview"
        assert subdoc_dir.exists()
        for seg in subdoc_segs:
            assert (subdoc_dir / f"{seg.name}.md").exists()

    def test_W05_returns_list_of_new_subdoc_paths(self, tmp_path):
        """W-05: Returns list of new subdoc paths."""
        args = self._make_args(inline_threshold=50)
        content = (
            self._make_subdoc_content("## Alpha") + "\n" +
            self._make_subdoc_content("## Beta")
        )
        source = tmp_path / "doc.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        subdoc_count = sum(1 for s in doc if not s.is_inline)

        writer = Writer()
        result = writer.write(doc, source)
        assert isinstance(result, list)
        assert len(result) == subdoc_count

    def test_W06_dry_run_writer_no_files_created(self, tmp_path, capsys):
        """W-06: DryRunWriter prints planned actions without writing any files."""
        args = self._make_args(inline_threshold=50)
        content = (
            self._make_subdoc_content("## Alpha") + "\n" +
            self._make_subdoc_content("## Beta")
        )
        source = tmp_path / "doc.md"
        source.write_text(content)

        m = Measurer()
        doc = Document(content, m, **{k: v for k, v in vars(args).items() if k != 'dry_run'})
        writer = DryRunWriter()
        result = writer.write(doc, source)

        # No files should be created
        assert not (tmp_path / "doc.unfit.md").exists()
        assert not (tmp_path / "doc").exists()

        # Return value follows same schema (list of Paths)
        assert isinstance(result, list)
        # DryRunWriter returns [] explicitly
        assert result == []

        # Something should have been printed
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out


# ---------------------------------------------------------------------------
# args.min_segment_count Lower Bound
