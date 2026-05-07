"""
Document — structured container for an ordered collection of Segments.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from markdown_it import MarkdownIt

from fit.measurer import Measurer
from fit.segment import Segment

logger = logging.getLogger(__name__)


class Document:
    """Parses a Markdown document into an ordered collection of Segments.
    """

    def __init__(
        self,
        text: str,
        measurer: Measurer,
        soft_threshold: int = 3000,
        hard_threshold: int = 5000,
        inline_threshold: int = 600,
        inline_threshold_reduction_increment: int = 100,
        trivial_extension_threshold: int = 25,
        min_segment_count: int = 3,
        inline_languages: list[str] | None = None,
    ):
        """Parse a Markdown document into Segments. 
        
        Includes:

        - segmentation target detection
        - partitioning
        - name generation
        - inline/subdoc classification
        - block splitting
        - initial subdoc reduction

        Args:
            text: Raw Markdown document text.
            measurer: Token count estimator, injected into each Segment.
            soft_threshold: Token count below which a document is considered to fit without splitting.
            hard_threshold: Upper token bound adopted when further reduction would eliminate
                all prose or all code from any segment.
            inline_threshold: Maximum token count for a segment's inline component.
                Segments above this threshold are classified as subdocs.
            inline_threshold_reduction_increment: Amount by which the inline threshold is
                decremented each iteration of the reduction loop.
            trivial_extension_threshold: Token allowance above a single paragraph that still
                qualifies a segment as inline. Prevents splitting near-single-paragraph segments.
            min_segment_count: Minimum number of segments required to attempt a split.
                Documents that cannot produce this many segments are left unsplit.
            inline_languages: Code block languages to preserve longest during subdoc reduction,
                in priority order (index 0 = highest priority). None means no preference.
        """
        self._soft_threshold = soft_threshold
        self._hard_threshold = hard_threshold
        self._inline_threshold = inline_threshold
        self._inline_threshold_reduction_increment = inline_threshold_reduction_increment
        self._trivial_extension_threshold = trivial_extension_threshold
        self._min_segment_count = min_segment_count
        self._inline_languages = inline_languages  # None means no preference

        self._segments = Document._parse(
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

    def __iter__(self):
        return iter(self._segments)

    @property
    def names(self) -> list[str]:
        return [s.name for s in self._segments]

    def measure(self) -> int:
        """Estimated token count of the document as currently reduced.

        Sums the token count of each segment's inline content, plus the cost of
        the subdoc link line for each segment that has been classified as a subdoc.

        Returns:
            Total estimated token count.
        """
        total = 0
        for seg in self._segments:
            total += seg.measure()
            if not seg.is_inline:
                total += seg._link_overhead
        return total

    def is_satisfied(self, threshold: int) -> bool:
        """True if the current token count is at or below ``threshold``.

        Args:
            threshold: cutoff for token count

        Returns: 
            Whether or not the document token count is below the ``threshold``.
        """
        return self.measure() <= threshold

    @property
    def is_unsplittable(self) -> bool:
        """True if the document produced fewer segments than the minimum required to split."""
        return len(self._segments) < self._min_segment_count

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(
        text: str,
        measurer: Measurer,
        soft_threshold: int = 3000,
        hard_threshold: int = 5000,
        inline_threshold: int = 600,
        inline_threshold_reduction_increment: int = 100,
        trivial_extension_threshold: int = 25,
        min_segment_count: int = 3,
        inline_languages: list[str] | None = None,
    ) -> list[Segment]:
        """Parse a Markdown document into an ordered list of Segments.

        Runs the full pipeline: 

        - segmentation target detection
        - partitioning
        - name generation
        - inline/subdoc classification
        - block splitting
        - initial subdoc reduction
        
        Called by ``__init__``; also callable directly
        for testing.

        If no headings or ruled lines are found, returns a single inline Segment
        containing the full document text.

        Args:
            text: Raw Markdown document text.
            measurer: Token count estimator, injected into each Segment.
            soft_threshold: See ``__init__``.
            hard_threshold: See ``__init__``.
            inline_threshold: See ``__init__``.
            inline_threshold_reduction_increment: See ``__init__``.
            trivial_extension_threshold: See ``__init__``.
            min_segment_count: See ``__init__``.
            inline_languages: See ``__init__``.

        Returns:
            Segments in document order, each with measurer injected and initial
            reduction applied.
        """
        # Skipped from docstring:
        # - Link overhead precomputation (seg._link_overhead): set on each segment after construction,
        #   used by Document.measure(). Not relevant to parse() callers.
        md = MarkdownIt().enable("table")
        tokens = md.parse(text)
        lines = text.split("\n")

        # Step 1: Segmentation target detection
        target_level, target_type = Document._find_segmentation_target(tokens, min_segment_count)

        # Step 2 & 3 & 4: Segment the document and generate names
        segments_data = Document._segment_document(text, lines, tokens, target_level, target_type)

        if not segments_data:
            logger.warning("No headings or rules found; returning single segment.")
            seg = Segment(
                name="document",
                heading="",
                body=text,
                blocks=[],
                measurer=measurer,
                is_inline=True,
            )
            return [seg]

        result_segments = []

        resolved_languages = inline_languages  # None means no preference

        names = Document._assign_names(segments_data)

        for idx, (heading, body, seg_type) in enumerate(segments_data):
            name = names[idx]

            # Step 4: Inline/subdoc classification
            body_tokens = measurer.measure(body)
            is_inline = False

            if body_tokens < inline_threshold:
                is_inline = True
            else:
                # Check trivial extension condition
                first_para = Document._find_first_paragraph(body, md)
                if first_para is not None:
                    first_para_tokens = measurer.measure(first_para)
                    if body_tokens <= first_para_tokens + trivial_extension_threshold:
                        is_inline = True

            # Step 5: Block splitting for subdoc segments
            if is_inline:
                blocks = []
            else:
                blocks = Document._parse_segment(body)

            seg = Segment(
                name=name,
                heading=heading,
                body=body,
                blocks=blocks,
                measurer=measurer,
                is_inline=is_inline,
            )

            # Precompute link overhead
            link_line = f"[{name}.md]({name}.md) (~{measurer.measure(body)} tokens)\n"
            seg._link_overhead = measurer.measure(link_line)

            # Step 6: Initial subdoc reduction
            if not is_inline:
                seg.reduce(inline_threshold, resolved_languages)

            result_segments.append(seg)

        return result_segments

    @staticmethod
    def _slugify(heading: str) -> str:
        """Filesystem-safe slug from heading text. Returns empty string if no slug-able characters remain."""
        text = heading.lstrip("#").strip()
        if not text:
            return ""
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text)
        slug = slug.strip("_")
        slug = re.sub(r"_+", "_", slug)
        if not slug:
            return ""
        encoded = slug.encode("utf-8")
        if len(encoded) > 200:
            encoded = encoded[:200]
            slug = encoded.decode("utf-8", errors="ignore")
        return slug

    @staticmethod
    def _assign_names(segments_data: list) -> list[str]:
        """Generate a name for each entry in segments_data.

        Ruled lines → ``rule_NN``. Empty slugs → ``heading_NN``. Unique slugs → bare slug.
        Duplicate slugs suffixed with a zero-padded counter starting at ``01``.
        """
        # Pre-scan: count slug frequency for heading segments
        slug_freq: dict[str, int] = {}
        for heading, body, seg_type in segments_data:
            if seg_type == "heading":
                slug = Document._slugify(heading)
                if slug:
                    slug_freq[slug] = slug_freq.get(slug, 0) + 1

        # Assign names
        counts: dict[str, int] = {}
        names = []
        for heading, body, seg_type in segments_data:
            if seg_type == "rule":
                counts["_rule"] = counts.get("_rule", 0) + 1
                names.append(f"rule_{counts['_rule']:02d}")
            else:  # heading
                counts["_heading"] = counts.get("_heading", 0) + 1
                slug = Document._slugify(heading)
                if not slug:
                    names.append(f"heading_{counts['_heading']:02d}")
                elif slug_freq[slug] == 1:
                    names.append(slug)
                else:
                    counts[slug] = counts.get(slug, 0) + 1
                    names.append(f"{slug}_{counts[slug]:02d}")
        return names

    @staticmethod
    def _find_segmentation_target(tokens, min_segment_count: int):
        """Determine the heading level or rule type to split on.

        Scans H1–H6 in order, counting headings at each level plus all levels above.
        Returns the first level where that cumulative count meets ``min_segment_count``.
        Falls back to ruled lines, then to the deepest heading level found (with a warning).

        Returns:
            ``(level, type)`` where ``type`` is ``'heading'`` or ``'rule'``,
            and ``level`` is 1–6 for headings or 0 for rules.
            ``(None, None)`` if no headings or ruled lines exist.
        """
        heading_counts = {i: 0 for i in range(1, 7)}
        rule_count = 0

        for token in tokens:
            if token.type == "heading_open":
                level = int(token.tag[1])
                heading_counts[level] += 1
            elif token.type == "hr":
                rule_count += 1

        for level in range(1, 7):
            if heading_counts[level] == 0:
                continue
            count_at_or_above = sum(heading_counts[l] for l in range(1, level + 1))
            if count_at_or_above >= min_segment_count:
                return level, "heading"

        if rule_count >= min_segment_count:
            return 0, "rule"

        for level in range(6, 0, -1):
            if heading_counts[level] > 0:
                logger.warning(
                    f"No heading level meets min_segment_count={min_segment_count}; "
                    f"using H{level} (found {heading_counts[level]} heading(s))."
                )
                return level, "heading"

        if rule_count > 0:
            logger.warning(
                f"No heading level meets min_segment_count={min_segment_count}; "
                f"using ruled lines (found {rule_count})."
            )
            return 0, "rule"

        logger.warning("No headings or ruled lines found; document cannot be split.")
        return None, None

    @staticmethod
    def _segment_document(text: str, lines: list[str], tokens, target_level, target_type):
        """Partition the document at the target heading level or ruled lines.

        Returns:
            List of ``(heading, body, seg_type)`` tuples in document order,
            where ``seg_type`` is ``'heading'`` or ``'rule'``.
        """
        if target_level is None and target_type is None:
            return []

        split_points = []

        if target_type == "heading":
            i = 0
            while i < len(tokens):
                token = tokens[i]
                if token.type == "heading_open" and token.map:
                    level = int(token.tag[1])
                    if level <= target_level:
                        heading_text = ""
                        if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                            heading_text = tokens[i + 1].content
                        line_idx = token.map[0]
                        split_points.append((line_idx, heading_text, "heading"))
                i += 1
        else:  # rule
            for token in tokens:
                if token.type == "hr" and token.map:
                    line_idx = token.map[0]
                    split_points.append((line_idx, "", "rule"))

        if not split_points:
            return []

        segments = []
        for i, (line_idx, heading_text, seg_type) in enumerate(split_points):
            if i + 1 < len(split_points):
                end_line = split_points[i + 1][0]
            else:
                end_line = len(lines)

            heading_line = lines[line_idx]
            body_lines = lines[line_idx:end_line]
            body = "\n".join(body_lines)
            if body and not body.endswith("\n"):
                body += "\n"

            segments.append((heading_line, body, seg_type))

        return segments

    @staticmethod
    def _find_first_paragraph(body: str, md) -> Optional[str]:
        """First paragraph text in the segment body, or None if not found."""
        tokens = md.parse(body)
        lines = body.split("\n")

        for token in tokens:
            if token.type == "paragraph_open" and token.map:
                start = token.map[0]
                end = token.map[1]
                para_lines = lines[start:end]
                return "\n".join(para_lines)
        return None

    @staticmethod
    def _parse_segment(body: str) -> list[str]:
        """Split a segment body string into an ordered list of top-level blocks.

        A block is one top-level structural unit: a paragraph, fenced code block, list,
        blockquote, table, etc. Nested content is not surfaced as separate blocks.

        Blank lines between blocks are preserved by slicing each block up to the start
        of the next block rather than to its own end line. Block text is never stripped —
        trailing whitespace is load-bearing for faithful reconstruction of the segment body.

        Returns:
            Blocks in document order. Returns ``[body]`` if no block structure is detected.
        """
        md = MarkdownIt().enable("table")
        tokens = md.parse(body)
        lines = body.split("\n")

        top_level_ranges = []
        depth = 0
        open_token = None
        container_opens = {
            "bullet_list_open", "ordered_list_open",
            "blockquote_open", "table_open",
        }
        container_closes = {
            "bullet_list_close", "ordered_list_close",
            "blockquote_close", "table_close",
        }
        simple_blocks = {
            "paragraph_open", "fence", "hr", "html_block",
            "code_block",
        }

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type in container_opens:
                if depth == 0:
                    open_token = token
                depth += 1
                i += 1
                continue

            if token.type in container_closes:
                depth -= 1
                if depth == 0 and open_token is not None:
                    if open_token.map:
                        start = open_token.map[0]
                        end = open_token.map[1]
                        top_level_ranges.append((start, end))
                    open_token = None
                i += 1
                continue

            if depth == 0:
                if token.type in simple_blocks and token.map:
                    top_level_ranges.append((token.map[0], token.map[1]))
                elif token.type == "heading_open" and token.map:
                    j = i + 1
                    while j < len(tokens) and tokens[j].type != "heading_close":
                        j += 1
                    close_t = tokens[j] if j < len(tokens) else None
                    if close_t and close_t.map:
                        top_level_ranges.append((token.map[0], close_t.map[1]))
                    elif token.map:
                        top_level_ranges.append((token.map[0], token.map[1]))
                    i = j + 1
                    continue

            i += 1

        if not top_level_ranges:
            return [body] if body else []

        blocks = []
        n_ranges = len(top_level_ranges)
        for idx, (start, end) in enumerate(top_level_ranges):
            if idx + 1 < n_ranges:
                next_start = top_level_ranges[idx + 1][0]
            else:
                next_start = len(lines)
            block_text = "\n".join(lines[start:next_start])
            if idx + 1 < n_ranges:
                block_text += "\n"
            blocks.append(block_text)

        return blocks
