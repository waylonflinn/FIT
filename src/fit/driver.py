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
    verbose: bool = False,
    is_root: bool = False,
) -> list[Path]:
    """Process a single Markdown file through the FIT pipeline.

    Applies a coarse token count gate before constructing a Document. Skips
    files that already fit within the soft threshold. Skips files that cannot
    be split into enough segments. Otherwise runs the reduction loop and writes
    output.

    Args:
        path: Path to the Markdown file to process.
        soft_threshold: Token count below which the file is skipped without processing.
        hard_threshold: Upper token bound adopted when further reduction would eliminate
            all prose or all code from any segment.
        inline_threshold: Maximum token count for a segment's inline component.
        inline_threshold_reduction_increment: Amount by which the inline threshold is
            decremented each iteration of the reduction loop.
        trivial_extension_threshold: Token allowance above a single paragraph that still
            qualifies a segment as inline.
        min_segment_count: Minimum number of segments required to attempt a split.
        inline_languages: Code block languages to preserve longest during subdoc reduction,
            in priority order (index 0 = highest priority). None means no preference.
        dry_run: If True, print planned write actions without touching the filesystem.
        verbose: If True, log additional detail during writing.
        is_root: Placeholder for future use. Has no current effect.

    Returns:
        List of subdoc paths created. Empty if the file was skipped or unsplittable.
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

    writer = WriterFactory.create(dry_run=dry_run, verbose=verbose)
    writer.log(f"Processing file: {path}")
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
    """Iteratively reduce the document until it satisfies the token threshold.

    Each iteration decrements the inline threshold and runs three sequential steps:

    - **Demotion:** Any inline segment whose body now exceeds the new inline threshold
      is converted to a subdoc and immediately reduced to the new threshold.
    - **Scan:** While still on the soft threshold, checks each segment for a critical
      reduction condition. If found, permanently switches to the hard threshold.
    - **Reduce:** Reduces each non-empty subdoc segment to the current inline threshold.

    Writes and returns when the document satisfies the active threshold. Also writes
    (with a warning) if all subdoc blocks have been exhausted without satisfying it.

    Args:
        doc: Parsed Document to reduce.
        writer: Writer or DryRunWriter instance used to write output.
        source_path: Path to the original source file; passed through to the writer.
        soft_threshold: Initial target token count.
        hard_threshold: Fallback target adopted on critical reduce detection.
        inline_threshold: Starting inline threshold, decremented each iteration.
        inline_threshold_reduction_increment: Amount to decrement per iteration.
        inline_languages: Priority language list passed to each segment's reduce call.

    Returns:
        List of subdoc paths written.
    """
    # NOTE: The demotion block below accesses seg._measurer directly and calls
    # Document._parse_segment() — both private. It also calls seg.demote_to_subdoc(),
    # which was flagged as a code smell during Segment documentation. This whole
    # demotion section is a known refactor candidate; the tight coupling between
    # driver, Document, and Segment here has been noted since the design phase.
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
