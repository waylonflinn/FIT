"""
preprocess subcommand — convert MDX/Mintlify source to standard CommonMark.

Operates in place. Backs up the original to ``<basename>.orig.md`` before
writing the converted text. Prints a summary of transformations applied
per tag.

Detection and conversion live in :mod:`fit.mdx`. This module is the
argparse + filesystem wrapper.
"""

from __future__ import annotations

import argparse


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``preprocess`` subcommand with the top-level parser.

    Args:
        subparsers: The ``argparse`` subparsers object from :mod:`fit.cli`.

    Returns:
        The configured subparser. The caller does not normally use the
        return value — it exists for symmetry with the other commands.
    """
    ...


def run(args) -> None:
    """Execute ``fit preprocess`` against ``args.path``.

    Steps:

    1. Read source from ``args.path``.
    2. Construct :class:`fit.mdx.MdxDocument` over the source.
    3. Call :meth:`fit.mdx.MdxDocument.preprocess` to produce transformed text.
    4. Write a backup to ``<basename>.orig.md`` (skipped under ``--dry-run``).
    5. Overwrite ``args.path`` with the transformed text
       (skipped under ``--dry-run``).
    6. Print the per-tag transformation summary to stdout.

    Args:
        args: Parsed argparse namespace from :func:`add_parser`.
    """
    ...
