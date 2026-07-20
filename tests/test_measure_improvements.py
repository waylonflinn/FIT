"""Contract tests for Spec 003 threshold and measure improvements."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fit.cli import main
from fit.measurer import Measurer


class TestThresholdConfiguration:
    def test_each_threshold_resolves_flag_then_nearest_config_then_default(
        self, tmp_path
    ):
        from fit.config import ThresholdResolver

        (tmp_path / ".fit.toml").write_text(
            "[thresholds]\nsoft = 4000\nhard = 7000\n",
            encoding="utf-8",
        )
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / ".fit.toml").write_text(
            "[thresholds]\nsoft = 2000\nhard = 3000\n",
            encoding="utf-8",
        )
        target = nested / "doc.md"
        target.write_text("content\n", encoding="utf-8")

        resolved = ThresholdResolver().resolve(target, soft_override=2500)

        assert resolved.soft == 2500
        assert resolved.soft_source == "flag"
        assert resolved.hard == 3000
        assert resolved.hard_source == str(nested / ".fit.toml")

    def test_invalid_config_is_a_hard_error_naming_the_file(self, tmp_path):
        config = tmp_path / ".fit.toml"
        config.write_text("[thresholds\nsoft = 10\n", encoding="utf-8")
        target = tmp_path / "doc.md"
        target.write_text("content\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["measure", str(target)])

        assert exc_info.value.code != 0
        assert str(config) in str(exc_info.value)

    @pytest.mark.parametrize(
        "config_text",
        [
            "[thresholds]\nsoft = 0\nhard = 10\n",
            "[thresholds]\nsoft = true\nhard = 10\n",
            "[thresholds]\nsoft = 20\nhard = 10\n",
        ],
    )
    def test_invalid_threshold_values_are_hard_errors(self, tmp_path, config_text):
        (tmp_path / ".fit.toml").write_text(config_text, encoding="utf-8")
        target = tmp_path / "doc.md"
        target.write_text("content\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["measure", str(target)])

        assert exc_info.value.code != 0

    def test_one_flag_does_not_conceal_invalid_config_value(self, tmp_path):
        (tmp_path / ".fit.toml").write_text(
            "[thresholds]\nsoft = \"invalid\"\nhard = 10\n",
            encoding="utf-8",
        )
        target = tmp_path / "doc.md"
        target.write_text("content\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["measure", "--soft-threshold", "5", str(target)])

        assert exc_info.value.code != 0

    @pytest.mark.parametrize(
        "config_text",
        [
            "[thresholds\nsoft = 10\n",
            "[thresholds]\nsoft = \"invalid\"\nhard = 10\n",
            "[thresholds]\nsoft = 20\nhard = 10\n",
        ],
    )
    def test_both_flags_warn_and_override_invalid_config(
        self, tmp_path, caplog, capsys, config_text
    ):
        config = tmp_path / ".fit.toml"
        config.write_text(config_text, encoding="utf-8")
        target = tmp_path / "doc.md"
        second_target = tmp_path / "other.md"
        target.write_text("content\n", encoding="utf-8")
        second_target.write_text("more content\n", encoding="utf-8")
        caplog.set_level(logging.WARNING)

        main([
            "measure",
            "--soft-threshold", "10",
            "--hard-threshold", "20",
            str(target),
            str(second_target),
        ])

        assert caplog.text.count("Ignoring invalid threshold configuration") == 1
        assert str(config) in caplog.text
        assert "fits" in capsys.readouterr().out

    def test_both_flags_still_require_a_valid_override_pair(self, tmp_path):
        (tmp_path / ".fit.toml").write_text(
            "[thresholds]\nsoft = \"invalid\"\n",
            encoding="utf-8",
        )
        target = tmp_path / "doc.md"
        target.write_text("content\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main([
                "measure",
                "--soft-threshold", "20",
                "--hard-threshold", "10",
                str(target),
            ])

        assert exc_info.value.code != 0

    def test_unknown_threshold_key_warns_once_per_config(
        self, tmp_path, caplog, capsys
    ):
        (tmp_path / ".fit.toml").write_text(
            "[thresholds]\nsoft = 3000\nfuture = 1\n",
            encoding="utf-8",
        )
        first = tmp_path / "a.md"
        second = tmp_path / "b.md"
        first.write_text("a\n", encoding="utf-8")
        second.write_text("b\n", encoding="utf-8")
        caplog.set_level(logging.WARNING)

        main(["measure", str(first), str(second)])

        assert caplog.text.count("future") == 1
        capsys.readouterr()

    def test_generate_resolves_root_once_and_descendants_inherit(
        self, tmp_path, monkeypatch
    ):
        from fit.commands.generate import level1

        (tmp_path / ".fit.toml").write_text(
            "[thresholds]\nsoft = 10\nhard = 20\n",
            encoding="utf-8",
        )
        root = tmp_path / "root.md"
        root.write_text("# Root\n", encoding="utf-8")
        child_dir = tmp_path / "root"
        child_dir.mkdir()
        (child_dir / ".fit.toml").write_text(
            "[thresholds]\nsoft = 1\nhard = 2\n",
            encoding="utf-8",
        )
        child = child_dir / "child.md"
        child.write_text("# Child\n", encoding="utf-8")
        calls = []

        def fake_process_file(path, **kwargs):
            calls.append((Path(path), kwargs["soft_threshold"], kwargs["hard_threshold"]))
            return [child] if Path(path) == root else []

        monkeypatch.setattr(level1, "process_file", fake_process_file)

        main(["generate", "--recurse", str(root)])

        assert calls == [(root, 10, 20), (child, 10, 20)]


class TestMeasureExpansion:
    def test_directory_is_flat_by_default_and_recursive_with_flag(self, tmp_path):
        from fit.commands.measure import expand_paths

        top = tmp_path / "top.md"
        top.write_text("top\n", encoding="utf-8")
        nested = tmp_path / "nested"
        nested.mkdir()
        child = nested / "child.md"
        child.write_text("child\n", encoding="utf-8")

        assert expand_paths([str(tmp_path)], recursive=False) == [top]
        assert expand_paths([str(tmp_path)], recursive=True) == [child, top]

    def test_implicit_expansion_excludes_mdx_and_all_backup_forms(self, tmp_path):
        from fit.commands.measure import expand_paths

        source = tmp_path / "source.md"
        source.write_text("source\n", encoding="utf-8")
        for name in (
            "component.mdx",
            "a.md.unfit",
            "b.unfit.md",
            "c.orig.md",
            "d.md.orig",
        ):
            (tmp_path / name).write_text("excluded\n", encoding="utf-8")

        assert expand_paths([str(tmp_path)], recursive=False) == [source]

    @pytest.mark.parametrize(
        "name", ["a.md.unfit", "b.unfit.md", "c.orig.md", "d.md.orig"]
    )
    def test_recognized_backup_is_measurable_when_explicit(self, tmp_path, name):
        from fit.commands.measure import expand_paths

        backup = tmp_path / name
        backup.write_text("backup\n", encoding="utf-8")

        assert expand_paths([str(backup)], recursive=False) == [backup]

    def test_overlapping_inputs_are_deduplicated_and_sorted(self, tmp_path):
        from fit.commands.measure import expand_paths

        a = tmp_path / "a.md"
        z = tmp_path / "z.md"
        a.write_text("a\n", encoding="utf-8")
        z.write_text("z\n", encoding="utf-8")

        assert expand_paths(
            [str(z), str(tmp_path), str(a)], recursive=False
        ) == [a, z]

    @pytest.mark.parametrize("kind", ["empty", "missing", "non_markdown"])
    def test_invalid_expansion_input_is_a_hard_error(self, tmp_path, kind):
        from fit.commands.measure import expand_paths

        if kind == "empty":
            path = tmp_path / "empty"
            path.mkdir()
        elif kind == "missing":
            path = tmp_path / "missing.md"
        else:
            path = tmp_path / "notes.txt"
            path.write_text("notes\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            expand_paths([str(path)], recursive=False)

        assert exc_info.value.code != 0


class TestMultiDocumentMeasure:
    def test_summary_totals_and_hard_violation_exit_code(self, tmp_path, capsys):
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        (first_dir / ".fit.toml").write_text(
            "[thresholds]\nsoft = 5\nhard = 20\n",
            encoding="utf-8",
        )
        (second_dir / ".fit.toml").write_text(
            "[thresholds]\nsoft = 5\nhard = 8\n",
            encoding="utf-8",
        )
        first = first_dir / "a.md"
        second = second_dir / "b.md"
        first.write_text("a" * 40, encoding="utf-8")
        second.write_text("b" * 40, encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["measure", str(first), str(second)])

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "2 files" in output
        assert "0 fit" in output
        assert "1 over soft" in output
        assert "1 over hard" in output
        assert "20 tokens total" in output

    def test_soft_violation_alone_returns_success(self, tmp_path, capsys):
        source = tmp_path / "doc.md"
        source.write_text("x" * 40, encoding="utf-8")

        main([
            "measure",
            "--soft-threshold", "5",
            "--hard-threshold", "20",
            str(source),
        ])

        assert "— soft" in capsys.readouterr().out

    def test_per_file_token_counts_are_padded_to_six_characters(
        self, tmp_path, capsys
    ):
        one = tmp_path / "one.md"
        ten = tmp_path / "ten.md"
        one.write_text("x" * 4, encoding="utf-8")
        ten.write_text("x" * 40, encoding="utf-8")

        main(["measure", str(one), str(ten)])

        lines = capsys.readouterr().out.splitlines()
        assert lines[0].startswith("     1 tokens — fits")
        assert lines[1].startswith("    10 tokens — fits")

    def test_verbose_output_reports_each_threshold_origin(self, tmp_path, capsys):
        config = tmp_path / ".fit.toml"
        config.write_text("[thresholds]\nhard = 20\n", encoding="utf-8")
        source = tmp_path / "doc.md"
        second_source = tmp_path / "other.md"
        source.write_text("content\n", encoding="utf-8")
        second_source.write_text("more content\n", encoding="utf-8")

        main([
            "measure",
            "--verbose",
            "--soft-threshold", "10",
            str(source),
            str(second_source),
        ])

        output = capsys.readouterr().out
        assert output.count("Thresholds (") == 1
        assert f"Thresholds ({tmp_path})" in output
        assert "soft 10 (flag)" in output
        assert f"hard 20 ({config})" in output

    def test_verbose_output_reports_each_directory_independently(
        self, tmp_path, capsys
    ):
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        first = first_dir / "a.md"
        second = second_dir / "b.md"
        first.write_text("a\n", encoding="utf-8")
        second.write_text("b\n", encoding="utf-8")

        main(["measure", "--verbose", str(first), str(second)])

        output = capsys.readouterr().out
        assert output.count("Thresholds (") == 2
        assert f"Thresholds ({first_dir})" in output
        assert f"Thresholds ({second_dir})" in output

    def test_measure_recursive_short_flag(self, tmp_path, capsys):
        nested = tmp_path / "nested"
        nested.mkdir()
        source = nested / "doc.md"
        source.write_text("content\n", encoding="utf-8")

        main(["measure", "-r", str(tmp_path)])

        assert str(source) in capsys.readouterr().out
