"""
Level 1/1.5 generate implementation — structural FIT with code block optimization.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from fit.driver import process_file

logger = logging.getLogger(__name__)


def run(args) -> None:
    """Run Level 1/1.5 generation: structural FIT via BFS driver loop."""
    inline_languages = args.inline_languages  # already a list from argparse

    queue = deque([Path(args.path)])
    is_root = True

    while queue:
        path = queue.popleft()
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
                is_root=is_root,
            )
            if args.recurse:
                queue.extend(new_paths)
        except Exception as e:
            logger.error(f"Error processing {path}: {e}")
            raise
        is_root = False
