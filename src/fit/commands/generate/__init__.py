"""
generate subcommand — generate a FIT from a markdown file.
"""

from __future__ import annotations

import argparse


def add_parser(subparsers) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "generate",
        help="Generate a FIT from a markdown file.",
    )
    p.add_argument("path", help="Markdown file to process.")
    p.add_argument(
        "--level",
        type=int,
        default=1,
        help="FIT generation level (default: 1).",
    )
    p.add_argument(
        "--soft-threshold",
        type=int,
        default=3000,
        dest="soft_threshold",
        help="Soft token target; triggers splitting (default: 3000).",
    )
    p.add_argument(
        "--hard-threshold",
        type=int,
        default=5000,
        dest="hard_threshold",
        help="Hard token ceiling (default: 5000).",
    )
    p.add_argument(
        "--inline-threshold",
        type=int,
        default=600,
        dest="inline_threshold",
        help="Segments below this token count are inlined in full (default: 600).",
    )
    p.add_argument(
        "--inline-threshold-reduction-increment",
        type=int,
        default=100,
        dest="inline_threshold_reduction_increment",
        help="Amount inline threshold is reduced per iteration (default: 100).",
    )
    p.add_argument(
        "--trivial-extension-threshold",
        type=int,
        default=25,
        dest="trivial_extension_threshold",
        help="Single-paragraph segments are inlined if within this many tokens of the paragraph (default: 25).",
    )
    p.add_argument(
        "--min-segment-count",
        type=int,
        default=3,
        dest="min_segment_count",
        help="Minimum number of segments required to use a heading level (default: 3, minimum: 2).",
    )
    p.add_argument(
        "--inline-languages",
        type=lambda s: [lang.strip() for lang in s.split(",")],
        default=["python", "javascript", "typescript"],
        dest="inline_languages",
        help="Comma-separated preferred languages for code block priority (default: python,javascript,typescript).",
    )
    p.add_argument(
        "-r", "--recurse",
        action="store_true",
        default=False,
        dest="recurse",
        help="Recursively process subdocuments produced by splitting (default: off).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Print what would happen without writing files.",
    )
    p.set_defaults(func=run)
    return p


def run(args) -> None:
    """Dispatch to the appropriate level implementation."""
    # Validate min_segment_count before dispatch
    if args.min_segment_count < 2:
        raise SystemExit(
            f"--min-segment-count must be at least 2 (got {args.min_segment_count}); "
            "a value of 1 would allow infinite recursion."
        )

    from fit.commands.generate import level1
    level_map = {1: level1}

    impl = level_map.get(args.level)
    if impl is None:
        raise SystemExit(f"Unknown level: {args.level}. Available levels: {sorted(level_map)}")

    impl.run(args)
