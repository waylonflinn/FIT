"""
measure subcommand — estimate token count for a markdown file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fit.measurer import Measurer


def add_parser(subparsers) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "measure",
        help="Estimate token count for a markdown file.",
    )
    p.add_argument("path", help="Markdown file to measure.")
    p.add_argument(
        "--soft-threshold",
        type=int,
        default=3000,
        dest="soft_threshold",
        help="Soft token target (default: 3000).",
    )
    p.add_argument(
        "--hard-threshold",
        type=int,
        default=5000,
        dest="hard_threshold",
        help="Hard token ceiling (default: 5000).",
    )
    p.set_defaults(func=run)
    return p


def run(args) -> None:
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    measurer = Measurer()
    count = measurer.measure(text)

    if count <= args.soft_threshold:
        status = "fits"
    elif count <= args.hard_threshold:
        status = "exceeds soft threshold"
    else:
        status = "exceeds hard threshold"

    print(f"{count} tokens — {status}  ({path})")
