"""
cli — top-level argument parsing and subcommand dispatch.
"""

from __future__ import annotations

import argparse
import logging


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        prog="fit",
        description="Generate and inspect Fitted Information Trees (FITs).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from fit.commands.generate import add_parser as add_generate
    from fit.commands.measure import add_parser as add_measure

    add_generate(subparsers)
    add_measure(subparsers)

    args = parser.parse_args(argv)
    args.func(args)
