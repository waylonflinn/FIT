"""
R8 Prototype: markdown-it-py line map reconstruction fidelity.

Verifies that for each top-level block token, slicing the original source by
token.map = [start_line, end_line] and concatenating all slices exactly
reconstructs the original document.

Test document contains:
  - paragraphs
  - an HTML comment block (html_block)
  - a blockquote (blockquote_open/close pair)
  - a bullet list (bullet_list_open/close pair)
  - a fenced code block (fence)

The key question: does concatenating all top-level block slices reproduce the
original source exactly, including whitespace between blocks?

Note on token.map semantics: token.map = [start, end] where start is inclusive
and end is exclusive (0-indexed line numbers). So the slice is lines[start:end].
"""

from pathlib import Path
from markdown_it import MarkdownIt


def top_level_tokens(tokens):
    """
    Yield only top-level block tokens (nesting == 0 for open tokens,
    or non-paired tokens like paragraph_open, fence, html_block, hr).

    We want one entry per logical block. For paired structures, yield the
    open token (nesting == 1); for atomic tokens, yield them directly.
    For close tokens (nesting == -1) and inline tokens, skip.
    """
    for token in tokens:
        if token.level == 0 and token.type != "inline":
            if token.nesting >= 0:  # open or self-closing; skip close (-1)
                yield token


def main():
    test_doc = Path(__file__).parent / "test_doc.md"
    original = test_doc.read_text()
    lines = original.splitlines(keepends=True)

    md = MarkdownIt()
    tokens = md.parse(original)

    print("Top-level tokens and their line maps:")
    print("-" * 60)

    slices = []
    for token in top_level_tokens(tokens):
        if token.map is None:
            print(f"  {token.type:<30} map=None  ← WARNING: no line map")
            continue
        start, end = token.map
        slice_text = "".join(lines[start:end])
        slices.append((token.type, start, end, slice_text))
        preview = slice_text.splitlines()[0][:50] if slice_text.strip() else "(empty)"
        print(f"  {token.type:<30} map=[{start:2d},{end:2d}]  # {preview}")

    print()

    # Check 1: do slices cover the full document without gaps?
    print("Coverage check:")
    prev_end = 0
    gaps = []
    for token_type, start, end, _ in slices:
        if start > prev_end:
            gap_text = "".join(lines[prev_end:start])
            gaps.append((prev_end, start, gap_text))
            print(f"  GAP at lines [{prev_end},{start}): {repr(gap_text)}")
        prev_end = max(prev_end, end)

    if prev_end < len(lines):
        tail = "".join(lines[prev_end:])
        print(f"  TAIL at lines [{prev_end},{len(lines)}): {repr(tail)}")
        gaps.append((prev_end, len(lines), tail))

    if not gaps:
        print("  No gaps detected — slices are contiguous.")

    print()

    # Check 2: reconstruct and compare
    # Include gap text in reconstruction to get a fair comparison
    reconstructed_parts = []
    prev_end = 0
    for token_type, start, end, slice_text in slices:
        if start > prev_end:
            reconstructed_parts.append("".join(lines[prev_end:start]))
        reconstructed_parts.append(slice_text)
        prev_end = end
    if prev_end < len(lines):
        reconstructed_parts.append("".join(lines[prev_end:]))
    reconstructed = "".join(reconstructed_parts)

    print("Reconstruction check:")
    if reconstructed == original:
        print("  ✓ Reconstructed text matches original exactly.")
    else:
        print("  ✗ MISMATCH — reconstructed text differs from original.")
        # Show first difference
        for i, (a, b) in enumerate(zip(original, reconstructed)):
            if a != b:
                print(f"    First difference at char {i}:")
                print(f"    Original:      {repr(original[max(0,i-20):i+20])}")
                print(f"    Reconstructed: {repr(reconstructed[max(0,i-20):i+20])}")
                break

    print()

    # Check 3: slice-only reconstruction (no gap filling) — what naive slicing produces.
    slice_only = "".join(s for _, _, _, s in slices)
    print("Slice-only reconstruction (naive — what splitter produces without fix):")
    if slice_only == original:
        print("  ✓ Slice-only text matches original — no inter-block whitespace lost.")
    else:
        print("  ✗ Slice-only differs from original — inter-block whitespace is in gaps.")
        print(f"    Original length: {len(original)}, Slice-only length: {len(slice_only)}")
        if gaps:
            print(f"    Gap content: {[repr(g[2]) for g in gaps]}")

    print()

    # Check 4: next_start reconstruction — proposed fix.
    # For each block, extend its slice to where the next block starts (or EOF).
    # This absorbs the gap blank lines into the preceding block's slice.
    print("next_start reconstruction (proposed fix — lines[start:next_start]):")
    extended_slices = []
    for i, (token_type, start, end, _) in enumerate(slices):
        next_s = slices[i + 1][1] if i + 1 < len(slices) else len(lines)
        extended_text = "".join(lines[start:next_s])
        extended_slices.append((token_type, start, next_s, extended_text))
        preview = extended_text.splitlines()[0][:50] if extended_text.strip() else "(empty)"
        print(f"  {token_type:<30} lines[{start:2d}:{next_s:2d}]  # {preview}")

    print()
    next_start_result = "".join(s for _, _, _, s in extended_slices)
    if next_start_result == original:
        print("  ✓ next_start reconstruction matches original exactly — byte-identical.")
    else:
        print("  ✗ next_start reconstruction differs from original.")
        print(f"    Original length: {len(original)}, next_start length: {len(next_start_result)}")
        for i, (a, b) in enumerate(zip(original, next_start_result)):
            if a != b:
                print(f"    First difference at char {i}:")
                print(f"    Original:     {repr(original[max(0,i-20):i+20])}")
                print(f"    next_start:   {repr(next_start_result[max(0,i-20):i+20])}")
                break

    print()

    # Check 5: '\n'.join(block_text) — Waylon's proposed fix.
    # Each slice already ends with '\n' (keepends=True), so joining with '\n'
    # inserts exactly one blank line between blocks.
    # Hypothesis: works for single blank lines; fails for double blank lines.
    print("'\\n'.join reconstruction (Waylon's proposed fix):")
    join_result = "\n".join(s for _, _, _, s in slices)
    if join_result == original:
        print("  ✓ join reconstruction matches original exactly — byte-identical.")
    else:
        print("  ✗ join reconstruction differs from original.")
        print(f"    Original length: {len(original)}, join length: {len(join_result)}")
        # Find and display all differences
        orig_lines = original.splitlines(keepends=True)
        join_lines = join_result.splitlines(keepends=True)
        for i, (a, b) in enumerate(zip(orig_lines, join_lines)):
            if a != b:
                print(f"    First differing line {i}: orig={repr(a)} join={repr(b)}")
                break
        if len(orig_lines) != len(join_lines):
            print(f"    Line count: original={len(orig_lines)}, join={len(join_lines)}")

        with open('test_doc.reconstruct.md', 'w') as f:
            f.write(join_result)

        print("Wrote reconstruction doc to: " + 'test_doc.reconstruct.md')

if __name__ == "__main__":
    main()
