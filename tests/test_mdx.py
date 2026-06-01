"""
Tests for fit/mdx.py — MdxDocument scanning and preprocessing.

Scanning tests cover the regex-based pass that runs in MdxDocument.__init__.
Preprocessing tests cover the markdown-it-py token walk in
MdxDocument.preprocess(), one test per significant tag handling rule from
spec 002.
"""

from __future__ import annotations

import pytest

from fit.mdx import MdxDocument


# ---------------------------------------------------------------------------
# Scanning (cheap, runs in constructor)
# ---------------------------------------------------------------------------

class TestScan:
    def test_plain_markdown_has_no_tags(self):
        doc = MdxDocument("# Title\n\nJust some text.\n")
        assert doc.structural_tags == {}
        assert doc.content_wrapper_tags == {}
        assert doc.has_structural_tags is False
        assert doc.has_content_wrappers is False

    def test_structural_tag_counted(self):
        text = '<section title="A">x</section>\n<section title="B">y</section>\n'
        doc = MdxDocument(text)
        assert doc.structural_tags.get("section") == 2
        assert doc.has_structural_tags is True

    def test_content_wrapper_counted(self):
        doc = MdxDocument("<Tip>be careful</Tip>\n")
        assert doc.content_wrapper_tags.get("Tip") == 1
        assert doc.has_content_wrappers is True
        assert doc.has_structural_tags is False

    def test_structural_and_content_separated(self):
        text = (
            "<CodeGroup>\n"
            "```py\nx\n```\n"
            "</CodeGroup>\n"
            "<Tip>note</Tip>\n"
        )
        doc = MdxDocument(text)
        assert "CodeGroup" in doc.structural_tags
        assert "Tip" in doc.content_wrapper_tags
        assert "CodeGroup" not in doc.content_wrapper_tags
        assert "Tip" not in doc.structural_tags

    def test_format_findings_empty_when_no_tags(self):
        doc = MdxDocument("# Plain markdown\n\nNothing to find.\n")
        assert doc.format_findings() == ""

    def test_format_findings_lists_tags_and_counts(self):
        text = (
            '<section title="A">x</section>\n'
            '<section title="B">y</section>\n'
            '<Tip>z</Tip>\n'
        )
        out = MdxDocument(text).format_findings()
        assert "section" in out
        assert "2" in out
        assert "Tip" in out


# ---------------------------------------------------------------------------
# Preprocessing (token walk; deferred until preprocess() called)
# ---------------------------------------------------------------------------

class TestPreprocess:
    def test_no_tags_passes_through_unchanged(self):
        src = "# Title\n\nA paragraph.\n\n## Subhead\n\nMore prose.\n"
        assert MdxDocument(src).preprocess() == src

    def test_section_open_becomes_heading_at_depth_plus_one(self):
        src = (
            "# Top\n\n"
            '<section title="Inner">\n'
            "body\n"
            "</section>\n"
        )
        out = MdxDocument(src).preprocess()
        assert "## Inner" in out
        assert "<section" not in out
        assert "</section>" not in out
        assert "body" in out

    def test_codegroup_wrapper_discarded_content_kept(self):
        src = (
            "<CodeGroup>\n\n"
            "```python\nprint(1)\n```\n\n"
            "</CodeGroup>\n"
        )
        out = MdxDocument(src).preprocess()
        assert "<CodeGroup>" not in out
        assert "</CodeGroup>" not in out
        assert "print(1)" in out

    def test_card_caps_at_h6(self):
        # heading_depth = 6 → synthetic heading would be H7; per spec, drop it.
        src = (
            "###### Six\n\n"
            '<Card title="Inner">body</Card>\n'
        )
        out = MdxDocument(src).preprocess()
        assert "####### " not in out  # no H7 emitted
        assert "<Card" not in out
        assert "</Card>" not in out
        assert "body" in out

    def test_step_becomes_numbered_list_item(self):
        src = (
            "<Steps>\n"
            '<Step title="First">do x</Step>\n'
            '<Step title="Second">do y</Step>\n'
            "</Steps>\n"
        )
        out = MdxDocument(src).preprocess()
        assert "1." in out
        assert "2." in out
        assert "First" in out
        assert "Second" in out
        assert "<Step" not in out

    def test_steps_counter_resets_per_block(self):
        src = (
            "<Steps>\n"
            '<Step title="A">x</Step>\n'
            "</Steps>\n\n"
            "<Steps>\n"
            '<Step title="B">y</Step>\n'
            "</Steps>\n"
        )
        out = MdxDocument(src).preprocess()
        # Both blocks should start numbering at 1
        assert out.count("1.") == 2

    def test_tip_becomes_blockquote_with_label(self):
        src = "<Tip>Remember to commit.</Tip>\n"
        out = MdxDocument(src).preprocess()
        assert out.lstrip().startswith(">")
        assert "Remember to commit." in out
        assert "<Tip>" not in out
        assert "</Tip>" not in out

    def test_paramfield_run_coalesced_into_bullet_list(self):
        src = (
            '<ParamField body="model" type="string" required>The model name.</ParamField>\n'
            '<ParamField body="temperature" type="number">Sampling temperature.</ParamField>\n'
        )
        out = MdxDocument(src).preprocess()
        assert "- **model**" in out
        assert "- **temperature**" in out
        assert "<ParamField" not in out

    def test_responsefield_dotted_name_preserved(self):
        src = (
            '<ResponseField name="usage.input_tokens" type="integer">'
            "Tokens consumed.</ResponseField>\n"
        )
        out = MdxDocument(src).preprocess()
        assert "usage.input_tokens" in out
        assert "<ResponseField" not in out

    def test_summary_empty_before_preprocess(self):
        doc = MdxDocument('<section title="A">x</section>\n')
        assert doc.summary == {}

    def test_summary_populated_after_preprocess(self):
        src = (
            '<section title="A">x</section>\n'
            "<Tip>y</Tip>\n"
        )
        doc = MdxDocument(src)
        doc.preprocess()
        assert doc.summary.get("section", 0) >= 1
        assert doc.summary.get("Tip", 0) >= 1

    def test_unrecognized_html_block_passes_through(self):
        src = "<details>\n<summary>x</summary>\nbody\n</details>\n"
        out = MdxDocument(src).preprocess()
        assert "<details>" in out
        assert "<summary>" in out
