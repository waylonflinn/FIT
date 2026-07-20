"""
cli — top-level argument parsing and subcommand dispatch.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fit.config import ResolvedThresholds, ThresholdConfigError, ThresholdResolver


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        prog="fit",
        description="Generate and inspect Fitted Information Trees (FITs).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from fit.commands.generate import add_parser as add_generate
    from fit.commands.measure import add_parser as add_measure
    from fit.commands.preprocess import add_parser as add_preprocess

    add_generate(subparsers)
    add_measure(subparsers)
    add_preprocess(subparsers)

    args = parser.parse_args(argv)
    _resolve_thresholds(args)
    args.func(args)


def _resolve_thresholds(args: argparse.Namespace) -> None:
    """Resolve threshold-aware command arguments before command dispatch."""
    if args.command not in {"generate", "measure"}:
        return

    resolver = ThresholdResolver()
    try:
        if args.command == "generate":
            resolved = resolver.resolve(
                Path(args.path),
                soft_override=args.soft_threshold,
                hard_override=args.hard_threshold,
            )
            args.soft_threshold = resolved.soft
            args.hard_threshold = resolved.hard
            if args.verbose:
                _print_thresholds(Path(args.path), resolved)
            return

        from fit.commands.measure import expand_paths

        paths = expand_paths(args.paths, recursive=args.recursive)
        args.resolved_targets = []
        directory_thresholds: dict[Path, ResolvedThresholds] = {}
        for path in paths:
            directory = path.parent
            directory_identity = directory.resolve()
            resolved = directory_thresholds.get(directory_identity)
            if resolved is None:
                resolved = resolver.resolve(
                    directory,
                    soft_override=args.soft_threshold,
                    hard_override=args.hard_threshold,
                )
                directory_thresholds[directory_identity] = resolved
                if args.verbose:
                    _print_thresholds(directory, resolved)
            args.resolved_targets.append((path, resolved))
    except ThresholdConfigError as error:
        raise SystemExit(str(error)) from error


def _print_thresholds(path: Path, resolved: ResolvedThresholds) -> None:
    print(
        f"Thresholds ({path}): "
        f"soft {resolved.soft} ({resolved.soft_source}), "
        f"hard {resolved.hard} ({resolved.hard_source})"
    )
