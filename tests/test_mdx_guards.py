"""Guard-matrix contract tests for Spec 002's generate and measure commands."""

from __future__ import annotations

import logging

import pytest

from fit.cli import main
from fit.commands.generate import level1


def all_output(capsys, caplog) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err + caplog.text


@pytest.fixture
def process_spy(monkeypatch):
    calls = []

    def fake_process_file(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(level1, "process_file", fake_process_file)
    return calls


class TestGenerateGuard:
    def test_structural_tag_aborts_before_processing_or_writing(
        self, tmp_path, process_spy, capsys, caplog
    ):
        source = tmp_path / "structural.md"
        original = '<section title="Blocked">body</section>\n'
        source.write_text(original, encoding="utf-8")
        caplog.set_level(logging.WARNING)

        with pytest.raises(SystemExit) as exc_info:
            main(["generate", str(source)])

        assert exc_info.value.code != 0
        assert process_spy == []
        assert source.read_text(encoding="utf-8") == original
        assert list(tmp_path.iterdir()) == [source]
        output = all_output(capsys, caplog)
        assert "section" in output
        assert "preprocess" in output

    def test_unknown_jsx_aborts_before_processing_or_writing(
        self, tmp_path, process_spy, capsys, caplog
    ):
        source = tmp_path / "unknown.md"
        original = "<CustomWidget>body</CustomWidget>\n"
        source.write_text(original, encoding="utf-8")
        caplog.set_level(logging.WARNING)

        with pytest.raises(SystemExit) as exc_info:
            main(["generate", str(source)])

        assert exc_info.value.code != 0
        assert process_spy == []
        assert source.read_text(encoding="utf-8") == original
        output = all_output(capsys, caplog)
        assert "CustomWidget" in output
        assert "preprocess" in output

    def test_content_wrapper_warns_and_continues(
        self, tmp_path, process_spy, capsys, caplog
    ):
        source = tmp_path / "content.md"
        source.write_text("<Tip>warning only</Tip>\n", encoding="utf-8")
        caplog.set_level(logging.WARNING)

        main(["generate", str(source)])

        assert len(process_spy) == 1
        output = all_output(capsys, caplog).lower()
        assert "warning" in output
        assert "tip" in output

    def test_force_bypasses_all_mdx_guard_messages(
        self, tmp_path, process_spy, capsys, caplog
    ):
        source = tmp_path / "forced.md"
        source.write_text(
            '<section title="Forced"><Tip>x</Tip><CustomWidget /></section>\n',
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING)

        main(["generate", "--force", str(source)])

        assert len(process_spy) == 1
        output = all_output(capsys, caplog)
        assert "section" not in output
        assert "Tip" not in output
        assert "CustomWidget" not in output

    def test_literal_jsx_in_fenced_code_does_not_warn_or_abort(
        self, tmp_path, process_spy, capsys, caplog
    ):
        source = tmp_path / "example.md"
        source.write_text(
            "```md\n<section title='Example'>\n<CustomWidget />\n</section>\n```\n",
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING)

        main(["generate", str(source)])

        assert len(process_spy) == 1
        output = all_output(capsys, caplog)
        assert "preprocess" not in output.lower()
        assert "CustomWidget" not in output


class TestMeasureWarning:
    @pytest.mark.parametrize(
        ("source_text", "finding"),
        [
            ('<section title="A">body</section>\n', "section"),
            ("<Warning>body</Warning>\n", "Warning"),
            ("<CustomWidget>body</CustomWidget>\n", "CustomWidget"),
        ],
    )
    def test_any_mdx_finding_warns_concisely_then_prints_measurement(
        self, tmp_path, capsys, caplog, source_text, finding
    ):
        source = tmp_path / "measure.md"
        source.write_text(source_text, encoding="utf-8")
        caplog.set_level(logging.WARNING)

        main(["measure", str(source)])

        output = all_output(capsys, caplog)
        assert "MDX components may affect measurement or later generation." in output
        assert finding not in output
        assert "tokens" in output
        assert str(source) in output

    @pytest.mark.parametrize("verbose_flag", ["-v", "--verbose"])
    def test_verbose_mdx_warning_includes_categorized_findings(
        self, tmp_path, capsys, caplog, verbose_flag
    ):
        source = tmp_path / "measure.md"
        source.write_text(
            "<CustomWidget>body</CustomWidget>\n",
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING)

        main(["measure", verbose_flag, str(source)])

        output = all_output(capsys, caplog)
        assert "MDX components may affect measurement or later generation." in output
        assert "Unknown JSX:" in output
        assert "CustomWidget: 1" in output
        assert "tokens" in output

    def test_fenced_jsx_example_is_measured_without_warning(
        self, tmp_path, capsys, caplog
    ):
        source = tmp_path / "measure-example.md"
        source.write_text("```md\n<Tip>literal</Tip>\n```\n", encoding="utf-8")
        caplog.set_level(logging.WARNING)

        main(["measure", str(source)])

        output = all_output(capsys, caplog)
        assert "tokens" in output
        assert "warning" not in output.lower()

    def test_angle_bracket_placeholders_are_measured_without_warning(
        self, tmp_path, capsys, caplog
    ):
        source = tmp_path / "roadmap.md"
        source.write_text(
            "Write `decisions/<NNN>_<unit>.md` for each unit.\n",
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING)

        main(["measure", str(source)])

        output = all_output(capsys, caplog)
        assert "tokens" in output
        assert "warning" not in output.lower()
        assert "Unknown JSX" not in output
