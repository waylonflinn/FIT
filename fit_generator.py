#!/usr/bin/env python3
"""
FIT Generator — Basic Mechanical Split

Converts an arbitrarily large markdown document into a Fitted Information Tree (FIT):
a root document (≤3k tokens) linking to subdocuments (≤3k tokens each), recursively.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import deque
from pathlib import Path
from typing import Optional

from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Measurer
# ---------------------------------------------------------------------------

class Measurer:
    """Estimate token count from a string. Injected into Document and Segment."""

    TEXT_RATIO: float = 4.0
    CODE_RATIO: float = 3.5

    def measure(self, text: str) -> int:
        """Estimate token count. Uses code ratio if text is a fenced code block.

        Detection: stripped text starts AND ends with three backticks (```) and is not
        exactly "```" (a bare unopened fence). This matches strings that open and close
        with a fence marker.
        """
        if not text:
            return 0
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```") and stripped != "```":
            return int(len(text) / self.CODE_RATIO)
        return int(len(text) / self.TEXT_RATIO)


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

class Segment:
    """Encapsulates a single named section of the document."""

    def __init__(
        self,
        name: str,
        heading: str,
        body: str,
        blocks: list[str],
        measurer: Measurer,
        is_inline: bool,
    ):
        self.name = name
        self.heading = heading
        self.body = body  # immutable after construction
        self.blocks = list(blocks)
        self._measurer = measurer
        self.is_inline = is_inline

        # Set from original block list at construction — never mutated
        self._had_paragraph: bool = any(
            not self._is_code_block(b) for b in self.blocks
        )
        self._had_code: bool = any(
            self._is_code_block(b) for b in self.blocks
        )

        # Cached token count — sum over current blocks (0 for inline)
        self._cached_tokens: int = sum(measurer.measure(b) for b in self.blocks)

        # Link overhead: precomputed once (used by Document.measure())
        # Will be set by Document after construction
        self._link_overhead: int = 0

    def __repr__(self) -> str:
        body_len = 20
        body_preview = self.body[:body_len].replace("\n", " ") + ("…" if len(self.body) > body_len else "")
        return f"Segment(name={self.name!r}, heading={self.heading!r}, is_inline={self.is_inline}, body={body_preview!r})"

    @staticmethod
    def _is_code_block(block: str) -> bool:
        """Return True if this block is a fenced code block."""
        stripped = block.strip()
        return stripped.startswith("```") and stripped.endswith("```") and stripped != "```"

    @staticmethod
    def _code_language(block: str) -> Optional[str]:
        """Extract the language from a fenced code block info string. Returns None if not code."""
        stripped = block.strip()
        if not (stripped.startswith("```") and stripped.endswith("```") and stripped != "```"):
            return None
        first_line = stripped.split("\n", 1)[0]
        lang = first_line[3:].strip()
        if not lang:
            return None
        # Normalize via pygments if available
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_by_name(lang)
                return lexer.name.lower()
            except ClassNotFound:
                return lang.lower()
        except ImportError:
            return lang.lower()

    def measure(self) -> int:
        """Return token estimate. Inline: measure body. Subdoc: return cached tokens."""
        if self.is_inline:
            return self._measurer.measure(self.body)
        return self._cached_tokens

    @property
    def is_empty(self) -> bool:
        """True if block list is empty."""
        return len(self.blocks) == 0

    def is_critical_reduce(self, threshold: int) -> bool:
        """
        Returns True if reducing at this threshold would eliminate all non-code blocks
        (when _had_paragraph) or all code blocks (when _had_code). Does not mutate state.
        """
        if not self._had_paragraph and not self._had_code:
            return False

        if len(self.blocks) == 0:
            # Already empty — past the critical point
            return self._had_paragraph or self._had_code

        non_code_blocks = [b for b in self.blocks if not self._is_code_block(b)]
        code_blocks = [b for b in self.blocks if self._is_code_block(b)]

        # Simulate: could we drop below threshold by removing only "safe" blocks?
        # Safe blocks for paragraph preservation: code blocks (remove them, keep prose)
        # Safe blocks for code preservation: non-code blocks (remove them, keep code)

        paragraph_critical = False
        code_critical = False

        if self._had_paragraph:
            # Would we lose the last non-code block?
            # We lose it if: even after removing all code blocks, we're still above threshold
            # OR if removing code blocks forces us to also remove prose blocks
            # More precisely: is_critical if the threshold forces removal of non-code blocks
            # Non-code blocks are removed in steps 4+.
            # Steps 1-3 remove only code blocks.
            # If removing ALL code blocks still leaves us >= threshold, then step 4+ fires -> critical
            tokens_if_code_removed = sum(
                self._measurer.measure(b) for b in non_code_blocks
            )
            if tokens_if_code_removed >= threshold:
                # Even with all code gone, still above threshold -> will hit step 4 -> critical
                paragraph_critical = True
            elif len(non_code_blocks) == 1 and self._cached_tokens >= threshold:
                # Only one non-code block; if we need to reduce at all, step 4 might fire
                # but only if code removal is insufficient
                # tokens_if_code_removed < threshold means code removal IS sufficient
                # so paragraph is safe
                paragraph_critical = False

        if self._had_code:
            # Would we lose the last code block?
            # Steps 1-4 remove non-priority code, duplicate priority code, then prose.
            # Step 5 removes the last code block.
            # Step 5 fires when we're still above threshold after removing all prose and
            # all but the last code block.
            # Simplification: critical if removing all non-code blocks still >= threshold
            # AND there's a code block to lose.
            tokens_if_prose_removed = sum(
                self._measurer.measure(b) for b in code_blocks
            )
            if tokens_if_prose_removed >= threshold and len(code_blocks) > 0:
                code_critical = True

        return paragraph_critical or code_critical

    def reduce(self, threshold: int, priority_languages: list[str] = None) -> int:
        """
        Remove blocks per priority algorithm until _cached_tokens < threshold.
        Returns _cached_tokens. Returns 0 if threshold is zero or all blocks exhausted.
        No-op if already empty.
        """
        if threshold == 0:
            self.blocks = []
            self._cached_tokens = 0
            return 0

        if not self.blocks:
            return 0

        if self._cached_tokens < threshold:
            return self._cached_tokens

        langs = priority_languages or []

        def _remove_block(idx: int) -> None:
            """Remove block at idx and delta-update _cached_tokens."""
            removed = self.blocks.pop(idx)
            self._cached_tokens -= self._measurer.measure(removed)

        def _satisfied() -> bool:
            return self._cached_tokens < threshold

        # Build set of normalized priority language names for fast lookup
        normalized_priority = set(self._normalize_lang(pl) for pl in langs)

        def _is_priority_code(block: str) -> bool:
            if not self._is_code_block(block):
                return False
            lang = self._code_language(block)
            if lang is None:
                return False
            return lang in normalized_priority

        # Step 1: Remove non-priority code blocks in reverse document order
        i = len(self.blocks) - 1
        while i >= 0:
            b = self.blocks[i]
            if self._is_code_block(b) and not _is_priority_code(b):
                _remove_block(i)
                if _satisfied():
                    return self._cached_tokens
            i -= 1

        # Step 2: Trim priority code to one-per-language, processing lowest priority first.
        # For each language: remove all but the FIRST instance, in reverse document order
        # (remove from the end backward, keeping the first/earliest instance).
        # "Remove all but the last" in the spec means "remove from the end backward until one
        # remains" — confirmed by R-05: json_A (first) survives, json_B and json_C are removed.
        # Early-stop after each individual block removal.
        for lang in reversed(langs):
            lang_norm = self._normalize_lang(lang)
            # Find all current indices of this language (document order = ascending)
            lang_indices = [
                idx for idx, b in enumerate(self.blocks)
                if self._is_code_block(b) and self._code_language(b) == lang_norm
            ]
            # Keep the first occurrence (lang_indices[0]); remove the rest from the end backward.
            # (Remove lang_indices[-1] first, then lang_indices[-2], etc.)
            while len(lang_indices) > 1:
                # Remove the last occurrence (highest index among this language's blocks)
                idx_to_remove = lang_indices[-1]
                _remove_block(idx_to_remove)
                if _satisfied():
                    return self._cached_tokens
                # Drop the removed index from our tracking list
                lang_indices.pop()
                # No need to adjust earlier indices — we only removed the highest index

        # Step 3: Remove priority code blocks in reverse priority order until only highest remains.
        # After step 2, each language has at most one block remaining.
        # Remove from lowest priority (last in langs) up to langs[1], keeping langs[0].
        for lang in reversed(langs[1:]):  # langs[0] is highest priority — skip it
            lang_norm = self._normalize_lang(lang)
            lang_indices = [
                idx for idx, b in enumerate(self.blocks)
                if self._is_code_block(b) and self._code_language(b) == lang_norm
            ]
            # There should be at most one, but loop for safety
            for idx in sorted(lang_indices, reverse=True):
                _remove_block(idx)
                if _satisfied():
                    return self._cached_tokens

        # Step 4: Remove non-code blocks in reverse document order until one non-code block remains.
        # "Reverse document order" = remove last non-code block first, stop when only one left.
        while True:
            non_code_indices = [
                idx for idx, b in enumerate(self.blocks) if not self._is_code_block(b)
            ]
            if len(non_code_indices) <= 1:
                break
            # Remove the last non-code block (highest index among non-code)
            idx = non_code_indices[-1]
            _remove_block(idx)
            if _satisfied():
                return self._cached_tokens

        # Step 5: Remove the final code block (if any).
        code_indices = [idx for idx, b in enumerate(self.blocks) if self._is_code_block(b)]
        for idx in sorted(code_indices, reverse=True):
            _remove_block(idx)
            if _satisfied():
                return self._cached_tokens

        # Step 6: Nothing satisfied threshold — clear everything and return 0.
        self.blocks = []
        self._cached_tokens = 0
        return 0

    @staticmethod
    def _normalize_lang(lang: str) -> str:
        """Normalize a language name for comparison."""
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_by_name(lang)
                return lexer.name.lower()
            except ClassNotFound:
                return lang.lower()
        except ImportError:
            return lang.lower()

    def demote_to_subdoc(self, blocks: list[str]) -> None:
        """Transition inline segment to subdoc status. Recomputes _cached_tokens from scratch."""
        self.is_inline = False
        self.blocks = list(blocks)
        self._cached_tokens = sum(self._measurer.measure(b) for b in self.blocks)

    def serialize_inline_component(self) -> str:
        """
        Returns heading + inline component (current blocks joined) + subdoc link.
        Token annotation uses measurer.measure(body) — immutable, stable across reduction.

        Since blocks are extracted from body (which includes the heading), blocks[0] is the
        heading. After reduction, blocks contains the heading + surviving prose/code.
        The output is: "".join(current_blocks) + link_line.

        If blocks is empty (fully reduced segment), just the heading + link is emitted.
        """
        token_count = self._measurer.measure(self.body)
        link = f"[{self.name}.md]({self.name}.md) (~{token_count} tokens)\n"
        if self.blocks:
            inline_content = "".join(self.blocks)
            if not inline_content.endswith("\n"):
                inline_content += "\n"
            return inline_content + link
        else:
            # Fully reduced: emit just the heading + link
            heading_line = self.heading
            if not heading_line.endswith("\n"):
                heading_line += "\n"
            return heading_line + link


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document:
    """Structured container for an ordered collection of Segments."""

    def __init__(self, text: str, measurer: Measurer, args):
        self._segments = Document._parse(text, measurer, args)
        self._args = args

    def __iter__(self):
        return iter(self._segments)

    @property
    def names(self) -> list[str]:
        return [s.name for s in self._segments]

    def measure(self) -> int:
        """Sum segment.measure() + subdoc link overhead for each subdoc segment."""
        total = 0
        for seg in self._segments:
            total += seg.measure()
            if not seg.is_inline:
                total += seg._link_overhead
        return total

    def is_satisfied(self, threshold: int) -> bool:
        return self.measure() <= threshold

    @property
    def is_unsplittable(self) -> bool:
        return len(self._segments) < self._args.min_segment_count

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(text: str, measurer: Measurer, args) -> list[Segment]:
        """Full parsing pipeline. Returns list of Segment objects."""
        md = MarkdownIt()
        tokens = md.parse(text)
        lines = text.split("\n")

        # Step 1: Segmentation target detection
        target_level, target_type = Document._find_segmentation_target(tokens, args.min_segment_count)

        # Step 2 & 3 & 4: Segment the document and generate names
        segments_data = Document._segment_document(text, lines, tokens, target_level, target_type)

        if not segments_data:
            # Warn and return single segment
            logger.warning("No headings or rules found; returning single segment.")
            single_name = "document"
            seg = Segment(
                name=single_name,
                heading="",
                body=text,
                blocks=[],
                measurer=measurer,
                is_inline=True,
            )
            return [seg]

        # Name generation with deduplication
        name_counts: dict[str, int] = {}
        result_segments = []

        inline_languages = getattr(args, "inline_languages", ["python", "javascript", "typescript"])
        if isinstance(inline_languages, str):
            inline_languages = [l.strip() for l in inline_languages.split(",")]

        for idx, (heading, body, seg_type) in enumerate(segments_data):
            # Generate slug name
            if seg_type == "rule":
                base_name = None  # will use rule_NN
                is_rule = True
            else:
                is_rule = False
                base_name = Document._slugify(heading)

            if is_rule or not base_name:
                if is_rule:
                    prefix = "rule"
                else:
                    prefix = "heading"
                # Count occurrences of this prefix
                count = name_counts.get(prefix, 0) + 1
                name_counts[prefix] = count
                name = f"{prefix}_{count:02d}"
            else:
                # Deduplicate
                if base_name not in name_counts:
                    name_counts[base_name] = 0
                    name = base_name
                else:
                    name_counts[base_name] += 1
                    suffix_num = name_counts[base_name]
                    name = f"{base_name}_{suffix_num:02d}"

            # Step 4: Inline/subdoc classification
            body_tokens = measurer.measure(body)
            is_inline = False

            if body_tokens < args.inline_threshold:
                is_inline = True
            else:
                # Check trivial extension condition
                first_para = Document._find_first_paragraph(body, md)
                if first_para is not None:
                    first_para_tokens = measurer.measure(first_para)
                    if body_tokens <= first_para_tokens + args.trivial_extension_threshold:
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
                seg.reduce(args.inline_threshold, inline_languages)

            result_segments.append(seg)

        return result_segments

    @staticmethod
    def _slugify(heading: str) -> str:
        """
        Convert heading text to a filesystem-safe slug.
        Algorithm (from design):
        1. Strip leading '#' characters and whitespace
        2. Replace runs of non-alphanumeric characters with '_'
        3. Strip leading/trailing '_'
        4. Collapse runs of '_' to single '_'
        5. Encode to UTF-8, truncate to 200 bytes, decode back safely
        6. Return empty string if result is empty (caller uses heading_NN fallback)
        """
        # Step 1: Strip leading '#' markers and whitespace
        text = heading.lstrip("#").strip()
        if not text:
            return ""
        # Step 2: Replace runs of non-alphanumeric (ASCII) characters with '_'
        # This turns spaces, punctuation, em-dashes, etc. into underscores
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text)
        # Step 3+4: Strip and collapse underscores
        slug = slug.strip("_")
        slug = re.sub(r"_+", "_", slug)
        if not slug:
            return ""
        # Step 5: Truncate to 200 bytes UTF-8 without splitting a multi-byte character
        encoded = slug.encode("utf-8")
        if len(encoded) > 200:
            encoded = encoded[:200]
            slug = encoded.decode("utf-8", errors="ignore")
        return slug

    @staticmethod
    def _find_segmentation_target(tokens, min_segment_count: int):
        """
        Find the segmentation target level.
        Returns (level, type) where type is 'heading' or 'rule'.
        level is 1-6 for headings, or 0 for rules.
        """
        # Count headings at each level
        heading_counts = {i: 0 for i in range(1, 7)}
        rule_count = 0

        for token in tokens:
            if token.type == "heading_open":
                level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
                heading_counts[level] += 1
            elif token.type == "hr":
                rule_count += 1

        # Search H1 through H6
        for level in range(1, 7):
            if heading_counts[level] == 0:
                continue
            # Count headings at this level plus all levels above
            count_at_or_above = sum(heading_counts[l] for l in range(1, level + 1))
            if count_at_or_above >= min_segment_count:
                return level, "heading"

        # Try ruled lines
        if rule_count >= min_segment_count:
            return 0, "rule"

        # Fallback: use lowest level found (highest number that has any headings)
        for level in range(6, 0, -1):
            if heading_counts[level] > 0:
                logger.warning(
                    f"No heading level meets min_segment_count={min_segment_count}; "
                    f"using H{level} (found {heading_counts[level]} heading(s))."
                )
                return level, "heading"

        # No headings at all, try rules
        if rule_count > 0:
            logger.warning(
                f"No heading level meets min_segment_count={min_segment_count}; "
                f"using ruled lines (found {rule_count})."
            )
            return 0, "rule"

        # Nothing usable
        logger.warning("No headings or ruled lines found; document cannot be split.")
        return None, None

    @staticmethod
    def _segment_document(text: str, lines: list[str], tokens, target_level, target_type):
        """
        Partition document into segments at target_level.
        Returns list of (heading, body, seg_type) tuples.
        seg_type is 'heading' or 'rule'.
        """
        if target_level is None and target_type is None:
            return []

        # Find all split points (line indices of target headings/rules)
        split_points = []  # list of (line_idx, heading_text, seg_type)

        if target_type == "heading":
            # Split at headings at level <= target_level (at or above target)
            i = 0
            while i < len(tokens):
                token = tokens[i]
                if token.type == "heading_open" and token.map:
                    level = int(token.tag[1])
                    if level <= target_level:
                        # Get the heading text from the inline token
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

        # Build segments from split points
        segments = []
        for i, (line_idx, heading_text, seg_type) in enumerate(split_points):
            if i + 1 < len(split_points):
                end_line = split_points[i + 1][0]
            else:
                end_line = len(lines)

            # The heading line
            heading_line = lines[line_idx]

            # Body = heading line + all content until next split
            body_lines = lines[line_idx:end_line]
            body = "\n".join(body_lines)
            # Ensure body ends with a newline if it had content
            if body and not body.endswith("\n"):
                body += "\n"

            segments.append((heading_line, body, seg_type))

        return segments

    @staticmethod
    def _find_first_paragraph(body: str, md) -> Optional[str]:
        """Find the first paragraph text in the segment body. Returns None if not found."""
        tokens = md.parse(body)
        lines = body.split("\n")

        for i, token in enumerate(tokens):
            if token.type == "paragraph_open" and token.map:
                start = token.map[0]
                end = token.map[1]
                para_lines = lines[start:end]
                return "\n".join(para_lines)
        return None

    @staticmethod
    def _parse_segment(body: str) -> list[str]:
        """
        Split a segment body into top-level blocks.
        Uses next_start slicing to preserve inter-block blank lines.
        Block text is NEVER stripped.
        """
        md = MarkdownIt()
        tokens = md.parse(body)
        lines = body.split("\n")

        # Find top-level block ranges using nesting depth tracking
        top_level_ranges = []
        depth = 0
        open_token = None  # tracks the opening token of the current top-level container
        # Container block open/close token pairs
        container_opens = {
            "bullet_list_open", "ordered_list_open",
            "blockquote_open", "table_open",
        }
        container_closes = {
            "bullet_list_close", "ordered_list_close",
            "blockquote_close", "table_close",
        }
        # Simple block types (appear as single tokens or open/inline/close triples at top level)
        simple_blocks = {
            "paragraph_open", "fence", "hr", "html_block",
            "code_block",  # indented code blocks
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
                    # Top-level container closed
                    close_token = token
                    if open_token.map and close_token.map:
                        start = open_token.map[0]
                        end = close_token.map[1]
                        top_level_ranges.append((start, end))
                    open_token = None
                i += 1
                continue

            if depth == 0:
                if token.type in simple_blocks and token.map:
                    top_level_ranges.append((token.map[0], token.map[1]))
                elif token.type == "heading_open" and token.map:
                    # Find matching heading_close
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
            # Fallback: return the whole body as one block
            return [body] if body else []

        # Build blocks using next_start scheme.
        # For each block, include lines from start up to (but not including) next_start.
        # The separator "\n" between adjacent sub-joins is appended explicitly to each non-last
        # block, ensuring that "".join(blocks) == body exactly.
        #
        # Proof: "\n".join(all_lines) == "\n".join(lines[a:b]) + "\n" + "\n".join(lines[b:c]) + ...
        # So block_text = "\n".join(lines[start:next_start]) + "\n"  for all but the last block.
        # The last block has no appended "\n" (or it's already included via the trailing empty
        # string in lines when body ends with "\n").
        blocks = []
        n_ranges = len(top_level_ranges)
        for idx, (start, end) in enumerate(top_level_ranges):
            if idx + 1 < n_ranges:
                next_start = top_level_ranges[idx + 1][0]
            else:
                next_start = len(lines)
            block_text = "\n".join(lines[start:next_start])
            if idx + 1 < n_ranges:
                # Append the separator "\n" that connects this sub-join to the next
                block_text += "\n"
            blocks.append(block_text)

        return blocks


# ---------------------------------------------------------------------------
# Writer and DryRunWriter
# ---------------------------------------------------------------------------

class Writer:
    """Writes document splits to the filesystem."""

    def write(self, document: Document, source_path: Path) -> list[Path]:
        """
        Write backup, root document, and subdoc files.
        Returns list of new subdoc paths created.
        """
        source_path = Path(source_path)

        # Step 1: Backup
        backup_path = source_path.parent / f"{source_path.stem}.unfit{source_path.suffix}"
        backup_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

        # Step 2: Assemble root document
        root_parts = []
        for seg in document:
            if seg.is_inline:
                root_parts.append(seg.body)
            else:
                root_parts.append(seg.serialize_inline_component())

        root_content = "".join(root_parts)
        source_path.write_text(root_content, encoding="utf-8")

        # Step 3: Write subdoc files
        subdoc_dir = source_path.parent / source_path.stem
        subdoc_paths = []

        for seg in document:
            if not seg.is_inline:
                subdoc_dir.mkdir(parents=True, exist_ok=True)
                subdoc_path = subdoc_dir / f"{seg.name}.md"
                subdoc_path.write_text(seg.body, encoding="utf-8")
                subdoc_paths.append(subdoc_path)

        return subdoc_paths


class DryRunWriter:
    """Prints planned actions without writing any files."""

    def write(self, document: Document, source_path: Path) -> list[Path]:
        """Print planned actions. Returns empty list (no files created)."""
        source_path = Path(source_path)
        backup_path = source_path.parent / f"{source_path.stem}.unfit{source_path.suffix}"
        subdoc_dir = source_path.parent / source_path.stem

        print(f"[DRY RUN] Would backup: {source_path} -> {backup_path}")
        print(f"[DRY RUN] Would rewrite root: {source_path}")

        subdoc_paths = []
        for seg in document:
            if seg.is_inline:
                print(f"[DRY RUN]   INLINE: {seg.name} ({seg.measure()} tokens)")
            else:
                subdoc_path = subdoc_dir / f"{seg.name}.md"
                print(f"[DRY RUN]   SUBDOC: {seg.name} -> {subdoc_path} ({seg._measurer.measure(seg.body)} tokens)")
                subdoc_paths.append(subdoc_path)

        # DryRunWriter returns [] — no files created, driver loop won't recurse
        return []


class WriterFactory:
    """Factory for Writer instances."""

    @staticmethod
    def create(args) -> "Writer | DryRunWriter":
        if getattr(args, "dry_run", False):
            return DryRunWriter()
        return Writer()


# ---------------------------------------------------------------------------
# process_file and _reduction_loop
# ---------------------------------------------------------------------------

def process_file(path: Path, args, is_root: bool = False) -> list[Path]:
    """
    Process a single file. Returns list of new subdoc paths created.
    is_root is a placeholder parameter for future use.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    measurer = Measurer()

    # Coarse initial gate
    if measurer.measure(text) <= args.soft_threshold:
        logger.info(f"{path}: fits within soft threshold, skipping.")
        return []

    doc = Document(text, measurer, args)

    if doc.is_unsplittable:
        logger.warning(
            f"{path}: too few segments to split (check for headings or decrease --min-segment-count)."
        )
        return []

    writer = WriterFactory.create(args)
    return _reduction_loop(doc, args, writer, path)


def _reduction_loop(doc: Document, args, writer, source_path: Path) -> list[Path]:
    """
    Outer reduction loop. Decrements inline threshold each iteration.
    Runs scan + reduce passes. Switches to hard threshold on critical reduce detection.
    """
    inline_languages = getattr(args, "inline_languages", ["python", "javascript", "typescript"])
    if isinstance(inline_languages, str):
        inline_languages = [l.strip() for l in inline_languages.split(",")]

    current_threshold = args.soft_threshold
    current_inline_threshold = args.inline_threshold
    hard_threshold_adopted = False

    # Check if already satisfied after initial _parse (step 6 reduction)
    if doc.is_satisfied(current_threshold):
        return writer.write(doc, source_path)

    while True:
        # Decrement inline threshold for this iteration
        current_inline_threshold -= args.inline_threshold_reduction_increment

        # Inline -> subdoc demotion check
        md = MarkdownIt()
        for seg in doc:
            if seg.is_inline:
                if seg._measurer.measure(seg.body) > current_inline_threshold:
                    blocks = Document._parse_segment(seg.body)
                    seg.demote_to_subdoc(blocks)
                    # After demotion, run initial reduce on this segment
                    seg.reduce(current_inline_threshold, inline_languages)

        # Pass 1: Scan (only while on soft threshold)
        if not hard_threshold_adopted:
            for seg in doc:
                if seg.is_critical_reduce(current_inline_threshold):
                    logger.warning(
                        f"Switching to hard threshold ({args.hard_threshold}) due to critical reduce."
                    )
                    hard_threshold_adopted = True
                    current_threshold = args.hard_threshold
                    break

            if hard_threshold_adopted:
                # Re-check satisfaction at hard threshold
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
        all_empty = all(
            seg.is_inline or seg.is_empty for seg in doc
        )
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


# ---------------------------------------------------------------------------
# DriverLoop and CLI
# ---------------------------------------------------------------------------

class DriverLoop:
    """BFS queue of file paths. Feeds each through process_file."""

    def __init__(self, args):
        self.args = args

    def run(self, paths: list[Path]) -> None:
        queue = deque(paths)
        is_root = True

        while queue:
            path = queue.popleft()
            try:
                new_paths = process_file(path, self.args, is_root=is_root)
                queue.extend(new_paths)
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")
                raise
            is_root = False


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fit_generator",
        description="Convert large markdown documents into Fitted Information Trees (FIT).",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files to process.")
    parser.add_argument(
        "--soft-threshold",
        type=int,
        default=3000,
        help="Soft token target; triggers splitting (default: 3000).",
    )
    parser.add_argument(
        "--hard-threshold",
        type=int,
        default=5000,
        help="Hard token ceiling (default: 5000).",
    )
    parser.add_argument(
        "--inline-threshold",
        type=int,
        default=600,
        help="Segments below this token count are inlined in full (default: 600).",
    )
    parser.add_argument(
        "--inline-threshold-reduction-increment",
        type=int,
        default=100,
        help="Amount inline threshold is reduced per iteration (default: 100).",
    )
    parser.add_argument(
        "--trivial-extension-threshold",
        type=int,
        default=25,
        help="Single-paragraph segments are inlined if within this many tokens of the paragraph (default: 25).",
    )
    parser.add_argument(
        "--min-segment-count",
        type=int,
        default=3,
        help="Minimum number of segments required to use a heading level (default: 3, minimum: 2).",
    )
    parser.add_argument(
        "--inline-languages",
        type=lambda s: [l.strip() for l in s.split(",")],
        default=["python", "javascript", "typescript"],
        help="Comma-separated preferred languages for code block priority (default: python,javascript,typescript).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would happen without writing files.",
    )

    args = parser.parse_args(argv)

    # Enforce min_segment_count >= 2
    if args.min_segment_count < 2:
        parser.error(
            f"--min-segment-count must be at least 2 (got {args.min_segment_count}); "
            "a value of 1 would allow infinite recursion."
        )

    return args


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args(argv)
    driver = DriverLoop(args)
    driver.run(args.paths)


if __name__ == "__main__":
    main()
