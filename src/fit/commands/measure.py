"""Measure one or more Markdown files against resolved token thresholds."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from fit.config import ResolvedThresholds
from fit.mdx import MdxDocument
from fit.measurer import Measurer


logger = logging.getLogger(__name__)

_BACKUP_ENDINGS = (".md.unfit", ".unfit.md", ".orig.md", ".md.orig")


@dataclass(frozen=True)
class MeasureResult:
    """One measured path and its classified token count."""

    path: Path
    count: int
    status: str


def _is_backup(path: Path) -> bool:
    return path.name.lower().endswith(_BACKUP_ENDINGS)


def expand_paths(paths: list[str], *, recursive: bool) -> list[Path]:
    """Expand explicit files and directories into a stable unique file list."""
    expanded: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        identity = path.resolve()
        if identity not in seen:
            seen.add(identity)
            expanded.append(path)

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise SystemExit(f"Path not found: {path}")
        if path.is_dir():
            candidates = path.rglob("*.md") if recursive else path.glob("*.md")
            eligible = sorted(
                (
                    candidate
                    for candidate in candidates
                    if candidate.is_file() and not _is_backup(candidate)
                ),
                key=lambda candidate: str(candidate),
            )
            if not eligible:
                raise SystemExit(f"No eligible Markdown files found in: {path}")
            for candidate in eligible:
                add(candidate)
            continue
        if not path.is_file():
            raise SystemExit(f"Not a regular file: {path}")
        if path.suffix != ".md" and not _is_backup(path):
            raise SystemExit(f"Not a Markdown file: {path}")
        add(path)

    return sorted(expanded, key=lambda path: str(path))


def add_parser(subparsers) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "measure",
        help="Estimate token counts for Markdown files.",
    )
    p.add_argument(
        "paths",
        nargs="+",
        metavar="path",
        help="Markdown files and/or directories to measure.",
    )
    p.add_argument(
        "-s", "--soft-threshold",
        type=int,
        default=None,
        dest="soft_threshold",
        help="Soft token target; overrides .fit.toml and the 3000 default.",
    )
    p.add_argument(
        "-t", "--hard-threshold",
        type=int,
        default=None,
        dest="hard_threshold",
        help="Hard token ceiling; overrides .fit.toml and the 5000 default.",
    )
    p.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Include Markdown files in nested directories.",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show threshold origins and categorized MDX findings.",
    )
    p.set_defaults(func=run)
    return p


def _colorize(status: str) -> str:
    if not sys.stdout.isatty():
        return status
    if status == "fits":
        return f"\033[32m{status}\033[0m"  # green
    elif status == "soft":
        return f"\033[33m{status}\033[0m"  # yellow
    else:
        return f"\033[31m{status}\033[0m"  # red


def run(args) -> None:
    results = [
        _measure(path, thresholds, verbose=args.verbose)
        for path, thresholds in args.resolved_targets
    ]
    for result in results:
        print(
            f"{result.count:>6,} tokens — {_colorize(result.status)}  "
            f"({result.path})"
        )

    if len(results) > 1:
        fit_count = sum(result.status == "fits" for result in results)
        soft_count = sum(result.status == "soft" for result in results)
        hard_count = sum(result.status == "hard" for result in results)
        total = sum(result.count for result in results)
        print(
            f"Summary: {len(results)} files — {fit_count} fit, "
            f"{soft_count} over soft, {hard_count} over hard; "
            f"{total:,} tokens total"
        )

    if any(result.status == "hard" for result in results):
        raise SystemExit(1)


def _measure(
    path: Path, thresholds: ResolvedThresholds, *, verbose: bool
) -> MeasureResult:
    text = path.read_text(encoding="utf-8")
    mdx_document = MdxDocument(text)
    if (
        mdx_document.has_structural_tags
        or mdx_document.has_content_wrappers
        or mdx_document.has_unknown_components
    ):
        warning = "MDX components may affect measurement or later generation."
        if verbose:
            warning += "\n" + mdx_document.format_findings()
        logger.warning(warning)
    count = Measurer().measure(text)

    if count <= thresholds.soft:
        status = "fits"
    elif count <= thresholds.hard:
        status = "soft"
    else:
        status = "hard"
    return MeasureResult(path, count, status)
