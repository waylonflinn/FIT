"""
measure subcommand — estimate token count for a markdown file.
"""

from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

from fit.mdx import MdxDocument
from fit.measurer import Measurer


logger = logging.getLogger(__name__)


def add_parser(subparsers) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "measure",
        help="Estimate token count for a markdown file.",
    )
    p.add_argument("path", help="Markdown file to measure.")
    p.add_argument(
        "-s", "--soft-threshold",
        type=int,
        default=3000,
        dest="soft_threshold",
        help="Soft token target (default: 3000).",
    )
    p.add_argument(
        "-t", "--hard-threshold",
        type=int,
        default=5000,
        dest="hard_threshold",
        help="Hard token ceiling (default: 5000).",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Include categorized MDX findings in warnings.",
    )
    p.set_defaults(func=run)
    return p

def _colorize(status: str) -> str:
    if not sys.stdout.isatty():
        return status
    if status == "fits":
        return f"\033[32m{status}\033[0m"           # green
    elif status == "exceeds soft threshold":
        return f"\033[33m{status}\033[0m"           # yellow
    else:
        return f"\033[31m{status}\033[0m"           # red

def run(args) -> None:
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    mdx_document = MdxDocument(text)
    if (
        mdx_document.has_structural_tags
        or mdx_document.has_content_wrappers
        or mdx_document.has_unknown_components
    ):
        warning = "MDX components may affect measurement or later generation."
        if args.verbose:
            warning += "\n" + mdx_document.format_findings()
        logger.warning(warning)
    measurer = Measurer()
    count = measurer.measure(text)

    if count <= args.soft_threshold:
        status = "fits"
    elif count <= args.hard_threshold:
        status = "exceeds soft threshold"
    else:
        status = "exceeds hard threshold"

    print(f"{count:,} tokens — {_colorize(status)}  ({path})")
