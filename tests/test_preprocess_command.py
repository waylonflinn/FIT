"""CLI and filesystem contract tests for ``fit preprocess`` (Spec 002)."""

from __future__ import annotations

import pytest

from fit.cli import main


def combined_output(capsys) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


class TestSuccessfulPreprocess:
    def test_cli_writes_exact_backup_replaces_source_and_prints_concise_result(
        self, tmp_path, capsys
    ):
        source = tmp_path / "guide.md"
        original = "<Tip>Remember.</Tip>\n"
        source.write_text(original, encoding="utf-8")

        main(["preprocess", str(source)])

        assert source.read_text(encoding="utf-8") == (
            "> **Tip:**\n"
            ">\n"
            "> Remember.\n"
        )
        assert (tmp_path / "guide.orig.md").read_text(encoding="utf-8") == original
        output = combined_output(capsys)
        assert output == f"Preprocessed {source}\n"

    @pytest.mark.parametrize("verbose_flag", ["-v", "--verbose"])
    def test_verbose_result_includes_transformation_details(
        self, tmp_path, capsys, verbose_flag
    ):
        source = tmp_path / "verbose.md"
        source.write_text("<Tip>Remember.</Tip>\n", encoding="utf-8")

        main(["preprocess", verbose_flag, str(source)])

        assert combined_output(capsys) == (
            f"Preprocessed {source} "
            "(Transformations: Tip: 1; discarded presentation attributes: none; "
            "unknown JSX: none; diagnostics: none)\n"
        )

    def test_backup_name_inserts_orig_before_final_suffix(self, tmp_path):
        source = tmp_path / "api.reference.md"
        original = '<section title="Reference">body</section>\n'
        source.write_text(original, encoding="utf-8")

        main(["preprocess", str(source)])

        assert (tmp_path / "api.reference.orig.md").read_text(encoding="utf-8") == original

    def test_clean_source_reports_no_changes_and_creates_no_backup(
        self, tmp_path, capsys
    ):
        source = tmp_path / "clean.md"
        original = "# Clean\n\nNothing to transform.\n"
        source.write_text(original, encoding="utf-8")

        main(["preprocess", str(source)])

        assert source.read_text(encoding="utf-8") == original
        assert not (tmp_path / "clean.orig.md").exists()
        assert "no changes" in combined_output(capsys).lower()

    def test_second_run_is_noop_even_though_first_backup_exists(self, tmp_path, capsys):
        source = tmp_path / "repeat.md"
        original = "<Note>Once.</Note>\n"
        source.write_text(original, encoding="utf-8")

        main(["preprocess", str(source)])
        transformed = source.read_text(encoding="utf-8")
        backup = tmp_path / "repeat.orig.md"
        assert backup.read_text(encoding="utf-8") == original
        capsys.readouterr()

        main(["preprocess", str(source)])

        assert source.read_text(encoding="utf-8") == transformed
        assert backup.read_text(encoding="utf-8") == original
        assert "no changes" in combined_output(capsys).lower()


class TestDryRun:
    def test_dry_run_validates_and_reports_without_writing(self, tmp_path, capsys):
        source = tmp_path / "dry.md"
        original = '<section title="Dry">body</section>\n'
        source.write_text(original, encoding="utf-8")

        main(["preprocess", "--dry-run", str(source)])

        assert source.read_text(encoding="utf-8") == original
        assert not (tmp_path / "dry.orig.md").exists()
        assert combined_output(capsys) == f"Dry run: would preprocess {source}\n"

    def test_verbose_dry_run_includes_transformation_details(
        self, tmp_path, capsys
    ):
        source = tmp_path / "dry.md"
        original = '<section title="Dry">body</section>\n'
        source.write_text(original, encoding="utf-8")

        main(["preprocess", "--dry-run", "--verbose", str(source)])

        assert source.read_text(encoding="utf-8") == original
        assert not (tmp_path / "dry.orig.md").exists()
        assert combined_output(capsys) == (
            f"Dry run: would preprocess {source} "
            "(Transformations: section: 1; "
            "discarded presentation attributes: none; "
            "unknown JSX: none; diagnostics: none)\n"
        )

    def test_dry_run_still_rejects_invalid_input_without_writing(
        self, tmp_path, capsys
    ):
        source = tmp_path / "invalid.md"
        original = "<UnknownWidget>body</UnknownWidget>\n"
        source.write_text(original, encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["preprocess", "--dry-run", str(source)])

        assert exc_info.value.code != 0
        assert source.read_text(encoding="utf-8") == original
        assert not (tmp_path / "invalid.orig.md").exists()
        assert list(tmp_path.iterdir()) == [source]
        output = combined_output(capsys)
        assert "UnknownWidget" in output
        assert "invalid choice" not in output


class TestFailureSafety:
    def test_existing_backup_is_never_overwritten(self, tmp_path, capsys):
        source = tmp_path / "guide.md"
        original = "<Tip>new source</Tip>\n"
        source.write_text(original, encoding="utf-8")
        backup = tmp_path / "guide.orig.md"
        backup.write_text("existing backup\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["preprocess", str(source)])

        assert exc_info.value.code != 0
        assert source.read_text(encoding="utf-8") == original
        assert backup.read_text(encoding="utf-8") == "existing backup\n"
        assert "backup" in combined_output(capsys).lower()
        assert set(tmp_path.iterdir()) == {source, backup}

    @pytest.mark.parametrize(
        ("original", "finding"),
        [
            ("<UnknownWidget>body</UnknownWidget>\n", "UnknownWidget"),
            ('<section title="Open">body\n', "unclosed"),
            ("<Tabs><Tab title='A'>body</Tabs>\n", "mismatch"),
            ("prose <Tip>body</Tip>\n", "mid-line"),
        ],
    )
    def test_validation_failure_leaves_source_and_directory_unchanged(
        self, tmp_path, capsys, original, finding
    ):
        source = tmp_path / "unsafe.md"
        source.write_text(original, encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main(["preprocess", str(source)])

        assert exc_info.value.code != 0
        assert source.read_text(encoding="utf-8") == original
        assert list(tmp_path.iterdir()) == [source]
        output = combined_output(capsys)
        assert finding.lower() in output.lower()
        assert "invalid choice" not in output

    def test_invalid_utf8_exits_nonzero_without_creating_files(self, tmp_path, capsys):
        source = tmp_path / "binary.md"
        original = b"\xff\xfe<Tip>bad</Tip>"
        source.write_bytes(original)

        with pytest.raises(SystemExit) as exc_info:
            main(["preprocess", str(source)])

        assert exc_info.value.code != 0
        assert source.read_bytes() == original
        assert list(tmp_path.iterdir()) == [source]
        output = combined_output(capsys).lower()
        assert "utf-8" in output or "decode" in output
        assert "invalid choice" not in output

    def test_directory_path_exits_nonzero_without_writing(self, tmp_path, capsys):
        source = tmp_path / "directory.md"
        source.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            main(["preprocess", str(source)])

        assert exc_info.value.code != 0
        assert source.is_dir()
        assert list(tmp_path.iterdir()) == [source]
        output = combined_output(capsys).lower()
        assert "regular file" in output or "not a file" in output
        assert "invalid choice" not in output
