"""
Prototype: MDX/Mintlify preprocessor.

Converts Mintlify/MDX component syntax to standard markdown before ingestion
into the FIT generator. Handles two constructs:

  <section title="...">   → synthetic heading at depth+1
  </section>              → discarded
  <CodeGroup>             → discarded
  </CodeGroup>            → discarded

Approach:
  1. Parse source with markdown-it-py to get top-level token stream.
  2. Walk tokens tracking current heading depth.
  3. For each html_block token:
     - If it matches <section title="...">, emit a synthetic heading at depth+1.
     - If it matches </section>, <CodeGroup>, or </CodeGroup>, discard.
     - Otherwise, emit as-is (using next_start reconstruction to preserve whitespace).
  4. Reconstruct output as standard markdown.

Key invariant from line_map prototype: use lines[start:next_start] to emit
each block's text — this absorbs inter-block blank lines into the preceding
block's slice and gives byte-identical reconstruction for unmodified blocks.

This prototype becomes the production 'fit preprocess' subcommand — not throwaway.

Test case: doc/anthropic/build-with-claude/prompt-caching.md
"""

import re
import sys
from pathlib import Path
from markdown_it import MarkdownIt


# Patterns for MDX constructs we handle
RE_SECTION_OPEN = re.compile(r'^\s*<section\s+title="([^"]+)"\s*/?>\s*$', re.IGNORECASE)
RE_SECTION_CLOSE = re.compile(r'^\s*</section\s*>\s*$', re.IGNORECASE)
RE_CODEGROUP_OPEN = re.compile(r'^\s*<CodeGroup\s*/?>\s*$', re.IGNORECASE)
RE_CODEGROUP_CLOSE = re.compile(r'^\s*</CodeGroup\s*>\s*$', re.IGNORECASE)

# Structural tags that must be absent from output — used in the regex fallback pass.
# These are the same tags the token-walker handles, but the fallback catches any that
# were invisible to markdown-it-py (e.g. indented 4 spaces → parsed as code_block).
STRUCTURAL_DISCARD_PATTERNS = [
    RE_SECTION_CLOSE,
    RE_CODEGROUP_OPEN,
    RE_CODEGROUP_CLOSE,
]
# section_open is NOT in the discard list — it needs title extraction, not just removal.
# If an indented <section title="..."> survives the token pass, we handle it separately.
RE_SECTION_OPEN_FALLBACK = re.compile(r'^\s*<section\s+title="([^"]+)"\s*/?>\s*$', re.IGNORECASE)

# Heading characters in order
HEADING_CHARS = '#'


def heading_prefix(depth: int) -> str:
    """Return the markdown heading prefix for a given depth (1-indexed)."""
    return '#' * max(1, depth)


def top_level_tokens(tokens):
    """Yield top-level block tokens (level==0, nesting >= 0, not inline)."""
    for token in tokens:
        if token.level == 0 and token.type != "inline" and token.nesting >= 0:
            yield token


def current_heading_depth(token, tokens_before) -> int:
    """
    Determine the heading depth in effect just before this token.
    Scans backward through all tokens (not just top-level) for the last
    heading token at level 0.
    """
    depth = 1  # default: treat as if we're at top level
    idx = tokens_before.index(token) if token in tokens_before else -1
    if idx == -1:
        return depth
    for t in tokens_before[:idx]:
        if t.type == "heading_open" and t.level == 0:
            # tag is 'h1', 'h2', etc.
            try:
                depth = int(t.tag[1])
            except (ValueError, IndexError):
                pass
    return depth


def classify_html_block(text: str):
    """
    Classify an html_block token's text.
    Returns one of:
      ('section_open', title_str)
      ('section_close', None)
      ('codegroup_open', None)
      ('codegroup_close', None)
      ('other', None)
    Only the first non-empty line of the block is examined.
    """
    first_line = text.strip().splitlines()[0] if text.strip() else ''
    m = RE_SECTION_OPEN.match(first_line)
    if m:
        return ('section_open', m.group(1))
    if RE_SECTION_CLOSE.match(first_line):
        return ('section_close', None)
    if RE_CODEGROUP_OPEN.match(first_line):
        return ('codegroup_open', None)
    if RE_CODEGROUP_CLOSE.match(first_line):
        return ('codegroup_close', None)
    return ('other', None)


def preprocess(source: str) -> str:
    """
    Convert MDX/Mintlify source to standard markdown.
    Returns the processed markdown string.
    """
    lines = source.splitlines(keepends=True)
    md = MarkdownIt()
    all_tokens = md.parse(source)
    top_tokens = list(top_level_tokens(all_tokens))

    output_parts = []
    heading_depth = 1  # tracks the most recent heading depth seen

    for i, token in enumerate(top_tokens):
        # Determine slice extent: from token.map[0] to start of next token (or EOF)
        if token.map is None:
            # Shouldn't happen for well-formed markdown, but skip safely
            continue
        start = token.map[0]
        if i + 1 < len(top_tokens) and top_tokens[i + 1].map is not None:
            next_start = top_tokens[i + 1].map[0]
        else:
            next_start = len(lines)
        block_text = ''.join(lines[start:next_start])

        if token.type == 'heading_open':
            # Track current heading depth
            try:
                heading_depth = int(token.tag[1])
            except (ValueError, IndexError):
                pass
            output_parts.append(block_text)

        elif token.type == 'html_block':
            kind, title = classify_html_block(token.content)

            if kind == 'section_open':
                # Emit synthetic heading at depth+1
                # Trailing whitespace from block_text becomes the separator
                synthetic_depth = heading_depth + 1
                prefix = heading_prefix(synthetic_depth)
                # Preserve the inter-block blank lines that follow (from next_start slicing)
                # by appending them after the synthetic heading line.
                trailing = ''.join(lines[token.map[1]:next_start])
                output_parts.append(f'{prefix} {title}\n{trailing}')

            elif kind in ('section_close', 'codegroup_open', 'codegroup_close'):
                # Discard the tag itself, but preserve trailing blank lines
                # so surrounding blocks aren't collapsed together.
                trailing = ''.join(lines[token.map[1]:next_start])
                output_parts.append(trailing)

            else:
                # Unrecognized html_block — emit as-is
                output_parts.append(block_text)

        else:
            # All other block types — emit as-is
            output_parts.append(block_text)

    result = ''.join(output_parts)

    # Fallback regex pass — catches structural tags that were invisible to markdown-it-py
    # (e.g. indented 4 spaces, which the parser treats as code_block content).
    # Process line by line so we can handle section_open (needs title extraction) vs
    # plain discard tags.
    result_lines = result.splitlines(keepends=True)
    cleaned = []
    for line in result_lines:
        stripped = line.rstrip('\n')
        discarded = False
        for pat in STRUCTURAL_DISCARD_PATTERNS:
            if pat.match(stripped):
                discarded = True
                break
        if discarded:
            continue
        m = RE_SECTION_OPEN_FALLBACK.match(stripped)
        if m:
            # Indented section_open — emit synthetic heading. Depth unknown without
            # token context; use H2 as safe default for deeply nested occurrences.
            title = m.group(1)
            cleaned.append(f'## {title}\n')
            continue
        cleaned.append(line)
    return ''.join(cleaned)


def main():
    if len(sys.argv) < 2:
        print("Usage: mdx_preprocessor.py <input.md> [output.md]")
        print()
        print("If output.md is omitted, writes to <input_stem>.preprocessed.md")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.with_suffix('').with_suffix('') \
            .parent / (input_path.stem + '.preprocessed.md')

    source = input_path.read_text()
    result = preprocess(source)
    output_path.write_text(result)

    # Report what changed
    input_lines = source.splitlines()
    output_lines = result.splitlines()
    print(f"Input:  {input_path} ({len(input_lines)} lines)")
    print(f"Output: {output_path} ({len(output_lines)} lines)")
    print(f"Delta:  {len(output_lines) - len(input_lines):+d} lines")

    # Count transformations
    section_opens = source.count('<section ')
    section_closes = source.count('</section>')
    codegroup_opens = source.count('<CodeGroup')
    codegroup_closes = source.count('</CodeGroup>')
    print(f"\nTransformed:")
    print(f"  <section ...>  → heading : {section_opens}")
    print(f"  </section>     → removed : {section_closes}")
    print(f"  <CodeGroup>    → removed : {codegroup_opens}")
    print(f"  </CodeGroup>   → removed : {codegroup_closes}")


if __name__ == '__main__':
    main()
