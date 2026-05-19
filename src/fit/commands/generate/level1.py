"""
Level 1/1.5 generate implementation — structural FIT with code block optimization.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path

from fit.driver import process_file
from fit.measurer import Measurer

logger = logging.getLogger(__name__)


def _update_link_token_count(parent_path: Path, child_path: Path) -> None:
    """Update the token count annotation in parent_path for the link to child_path.

    After a subdoc file has been recursively split and rewritten, its token count
    has decreased. This function reads the new child file size and patches the
    corresponding ``(~N tokens)`` annotation in the parent root document.

    Args:
        parent_path: The root document that contains a link to child_path.
        child_path: The subdoc file that was just rewritten (split).
    """
    try:
        child_text = child_path.read_text(encoding="utf-8")
        new_token_count = Measurer().measure(child_text)

        # The link href is relative to parent_path's directory.
        # e.g. parent = /a/doc.md, child = /a/doc/seg.md → href = doc/seg.md
        try:
            href = child_path.relative_to(parent_path.parent).as_posix()
        except ValueError:
            logger.warning(
                f"Cannot compute relative path from {parent_path.parent} to {child_path}; "
                "skipping token count update."
            )
            return

        parent_text = parent_path.read_text(encoding="utf-8")

        # Match: [<href>](<href>) (~<N> tokens)
        # Escaped href for regex safety.
        href_escaped = re.escape(href)
        pattern = re.compile(
            r"(\[" + href_escaped + r"\]\(" + href_escaped + r"\) \(~)\d+( tokens\))"
        )
        updated_text, count = pattern.subn(
            rf"\g<1>{new_token_count}\g<2>",
            parent_text,
        )

        if count == 0:
            logger.warning(
                f"No link matching '{href}' found in {parent_path}; token count not updated."
            )
            return

        parent_path.write_text(updated_text, encoding="utf-8")
        logger.info(
            f"Updated token count for {href} in {parent_path}: ~{new_token_count} tokens."
        )

    except Exception as e:
        logger.warning(f"Failed to update token count in {parent_path} for {child_path}: {e}")


def run(args) -> None:
    """Run Level 1/1.5 generation: structural FIT via BFS driver loop."""
    inline_languages = args.inline_languages  # already a list from argparse

    # Queue entries: (path, parent_path | None)
    # parent_path is the root document that contains a link to path; None for the root file.
    queue: deque[tuple[Path, Path | None]] = deque([(Path(args.path), None)])
    is_root = True

    while queue:
        path, parent_path = queue.popleft()
        try:
            new_paths = process_file(
                path,
                soft_threshold=args.soft_threshold,
                hard_threshold=args.hard_threshold,
                inline_threshold=args.inline_threshold,
                inline_threshold_reduction_increment=args.inline_threshold_reduction_increment,
                trivial_extension_threshold=args.trivial_extension_threshold,
                min_segment_count=args.min_segment_count,
                inline_languages=inline_languages,
                dry_run=args.dry_run,
                verbose=args.verbose,
                is_root=is_root,
            )
            if args.recurse:
                # If this file was split (new_paths non-empty), update the parent's
                # token count annotation for the link pointing to this file.
                if new_paths and parent_path is not None and not args.dry_run:
                    _update_link_token_count(parent_path, path)

                for child_path in new_paths:
                    queue.append((child_path, path))

        except Exception as e:
            logger.error(f"Error processing {path}: {e}")
            raise
        is_root = False
