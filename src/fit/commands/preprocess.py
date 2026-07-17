"""
preprocess subcommand — convert MDX/Mintlify source to standard CommonMark.

Operates in place. Backs up the original to ``<basename>.orig.md`` before
writing the converted text. Prints transformation details under ``--verbose``.

Detection and conversion live in :mod:`fit.mdx`. This module is the
argparse + filesystem wrapper.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from fit.mdx import MdxDocument, MdxPreprocessError


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``preprocess`` subcommand with the top-level parser.

    Args:
        subparsers: The ``argparse`` subparsers object from :mod:`fit.cli`.

    Returns:
        The configured subparser. The caller does not normally use the
        return value — it exists for symmetry with the other commands.
    """
    parser = subparsers.add_parser(
        "preprocess",
        help="Convert supported Mintlify MDX components to CommonMark.",
    )
    parser.add_argument("path", help="Markdown/MDX file to preprocess in place.")
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Validate and report without writing the source or backup.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Include transformation and diagnostic details.",
    )
    parser.set_defaults(func=run)
    return parser


def run(args) -> None:
    """Execute ``fit preprocess`` against ``args.path``.

    Steps:

    1. Read source from ``args.path``.
    2. Construct :class:`fit.mdx.MdxDocument` over the source.
    3. Call :meth:`fit.mdx.MdxDocument.preprocess` to produce transformed text.
    4. Write a backup to ``<basename>.orig.md`` (skipped under ``--dry-run``).
    5. Overwrite ``args.path`` with the transformed text
       (skipped under ``--dry-run``).
    6. Print a concise result, with transformation details under ``--verbose``.

    Args:
        args: Parsed argparse namespace from :func:`add_parser`.
    """
    path = Path(args.path)
    if not path.is_file():
        _fail(f"Not a regular file: {path}")

    try:
        original_bytes = path.read_bytes()
        original = original_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(f"Source is not valid UTF-8: {path}: {error}")
    except OSError as error:
        _fail(f"Could not read {path}: {error}")

    document = MdxDocument(original)
    try:
        transformed = document.preprocess()
    except MdxPreprocessError as error:
        _fail(f"MDX preprocessing failed: {error}")

    if transformed == original:
        print(f"No changes: {path}")
        return

    transformations = ", ".join(
        f"{name}: {count}" for name, count in document.summary.items()
    )
    discarded = ", ".join(
        f"{name}: {count}" for name, count in document.discarded_attributes.items()
    ) or "none"
    details = (
        f"Transformations: {transformations}; "
        f"discarded presentation attributes: {discarded}; "
        "unknown JSX: none; diagnostics: none"
    )
    verbose_suffix = f" ({details})" if args.verbose else ""
    backup = path.with_name(f"{path.stem}.orig{path.suffix}")
    if backup.exists():
        _fail(f"Refusing to overwrite existing backup: {backup}")

    if args.dry_run:
        print(f"Dry run: would preprocess {path}{verbose_suffix}")
        return

    staged: Path | None = None
    backup_created = False
    try:
        fd, staged_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        staged = Path(staged_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(transformed.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())

        backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        backup_created = True
        with os.fdopen(backup_fd, "wb") as handle:
            handle.write(original_bytes)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(staged, path)
        staged = None
    except FileExistsError as error:
        _fail(f"Refusing to overwrite existing backup: {backup}")
    except OSError as error:
        if backup_created:
            try:
                backup.unlink()
            except OSError:
                pass
        _fail(f"Could not commit preprocessing for {path}: {error}")
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except OSError:
                pass

    print(f"Preprocessed {path}{verbose_suffix}")
