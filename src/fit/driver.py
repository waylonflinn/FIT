"""
driver — process_file and _reduction_loop.
"""

from __future__ import annotations

import logging
from pathlib import Path

from markdown_it import MarkdownIt

from fit.document import Document
from fit.measurer import Measurer
from fit.writer import WriterFactory

logger = logging.getLogger(__name__)


def process_file(
    path: Path,
    soft_threshold: int = 3000,
    hard_threshold: int = 5000,
    inline_threshold: int = 600,
    inline_threshold_reduction_increment: int = 100,
    trivial_extension_threshold: int = 25,
    min_segment_count: int = 3,
    inline_languages: list[str] | None = None,
    dry_run: bool = False,
    is_root: bool = False,
) -> list[Path]:
    """
    Process a single file. Returns list of new subdoc paths created.
    is_root is a placeholder parameter for future use.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    measurer = Measurer()

    # Coarse initial gate
    if measurer.measure(text) <= soft_threshold:
        logger.info(f"{path}: fits within soft threshold, skipping.")
        return []

    doc = Document(
        text,
        measurer,
        soft_threshold=soft_threshold,
        hard_threshold=hard_threshold,
        inline_threshold=inline_threshold,
        inline_threshold_reduction_increment=inline_threshold_reduction_increment,
        trivial_extension_threshold=trivial_extension_threshold,
        min_segment_count=min_segment_count,
        inline_languages=inline_languages,
    )

    if doc.is_unsplittable:
        logger.warning(
            f"{path}: too few segments to split (check for headings or decrease --min-segment-count)."
        )
        return []

    writer = WriterFactory.create(dry_run=dry_run)
    return _reduction_loop(
        doc,
        writer,
        path,
        soft_threshold=soft_threshold,
        hard_threshold=hard_threshold,
        inline_threshold=inline_threshold,
        inline_threshold_reduction_increment=inline_threshold_reduction_increment,
        inline_languages=inline_languages,
    )


def _reduction_loop(
    doc: Document,
    writer,
    source_path: Path,
    soft_threshold: int = 3000,
    hard_threshold: int = 5000,
    inline_threshold: int = 600,
    inline_threshold_reduction_increment: int = 100,
    inline_languages: list[str] | None = None,
) -> list[Path]:
    """
    Outer reduction loop. Decrements inline threshold each iteration.
    Runs scan + reduce passes. Switches to hard threshold on critical reduce detection.
    """
    current_threshold = soft_threshold
    current_inline_threshold = inline_threshold
    hard_threshold_adopted = False

    # Check if already satisfied after initial _parse (step 6 reduction)
    if doc.is_satisfied(current_threshold):
        return writer.write(doc, source_path)

    while True:
        # Decrement inline threshold for this iteration
        current_inline_threshold -= inline_threshold_reduction_increment

        # Inline -> subdoc demotion check
        for seg in doc:
            if seg.is_inline:
                if seg._measurer.measure(seg.body) > current_inline_threshold:
                    blocks = Document._parse_segment(seg.body)
                    seg.demote_to_subdoc(blocks)
                    seg.reduce(current_inline_threshold, inline_languages)

        # Pass 1: Scan (only while on soft threshold)
        if not hard_threshold_adopted:
            for seg in doc:
                if seg.is_critical_reduce(current_inline_threshold):
                    logger.warning(
                        f"Switching to hard threshold ({hard_threshold}) due to critical reduce."
                    )
                    hard_threshold_adopted = True
                    current_threshold = hard_threshold
                    break

            if hard_threshold_adopted:
                if doc.is_satisfied(current_threshold):
                    return writer.write(doc, source_path)

        # Pass 2: Reduce
        for seg in doc:
            if not seg.is_inline and not seg.is_empty:
                seg.reduce(current_inline_threshold, inline_languages)

        # Check satisfaction
        if doc.is_satisfied(current_threshold):
            return writer.write(doc, source_path)

        # Check if all segments are empty (link-only)
        all_empty = all(seg.is_inline or seg.is_empty for seg in doc)
        if all_empty:
            logger.warning(
                f"{source_path}: all segment blocks exhausted but document still exceeds threshold; "
                "writing link-only document."
            )
            return writer.write(doc, source_path)

        # Safety: if inline threshold has gone very low, avoid infinite loop
        if current_inline_threshold <= 0:
            logger.warning(
                f"{source_path}: inline threshold exhausted without satisfying target; writing anyway."
            )
            return writer.write(doc, source_path)
