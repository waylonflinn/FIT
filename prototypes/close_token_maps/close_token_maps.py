"""
Prototype: markdown-it-py close token map availability.

The question: for container block types (bullet_list, ordered_list,
blockquote, table), do the closing tokens carry a .map attribute?

This matters for _parse_segment in fit_generator.py, which builds
top_level_ranges as (open.map[0], close.map[1]) pairs. If close.map
is None, the range is silently dropped and the block goes missing.

Test cases cover:
  - bullet list
  - ordered list
  - blockquote
  - table
  - nested list (list inside blockquote)
  - empty list item
  - list followed immediately by another block (no trailing blank line)

For each container found, prints the open and close token with their maps.
"""

from markdown_it import MarkdownIt

CONTAINER_OPENS = {
    "bullet_list_open",
    "ordered_list_open",
    "blockquote_open",
    "table_open",
}
CONTAINER_CLOSES = {
    "bullet_list_close",
    "ordered_list_close",
    "blockquote_close",
    "table_close",
}

TEST_CASES = {
    "bullet list": (
        "Before.\n\n"
        "- item 1\n"
        "- item 2\n"
        "\nAfter.\n"
    ),
    "bullet list longer": (
        "Before.\n\n"
        "- item 1\n"
        "- item 2\n"
        "- item 3\n"
        "\nAfter.\n"
    ),
    "ordered list": (
        "Before.\n\n"
        "1. first\n"
        "2. second\n"
        "\nAfter.\n"
    ),
    "blockquote": (
        "Before.\n\n"
        "> quoted line one\n"
        "> quoted line two\n"
        "\nAfter.\n"
    ),
    "table": (
        "Before.\n\n"
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
        "\nAfter.\n"
    ),
    "table": (
        "Before.\n\n"
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
        "|---|---|\n"
        "| C | D |\n"
        "\nAfter.\n"
    ),
    "nested list in blockquote": (
        "Before.\n\n"
        "> - nested item 1\n"
        "> - nested item 2\n"
        "\nAfter.\n"
    ),
    "list followed immediately by paragraph (no blank line)": (
        "- item 1\n"
        "- item 2\n"
        "After (no blank line).\n"
    ),
    "paragraph + code fence + bullet list (PS01 repro)": (
        "First paragraph.\n"
        "\n"
        "```python\nx = 1\n```\n"
        "\n"
        "- item 1\n"
        "- item 2\n"
    ),
}


def report_case(name: str, text: str):
    md = MarkdownIt().enable("table")
    tokens = md.parse(text)
    lines = text.split("\n")

    print(f"=== {name} ===")

    open_stack = []
    for token in tokens:
        if token.type in CONTAINER_OPENS:
            open_stack.append(token)
            indent = "  " * (len(open_stack) - 1)
            print(f"  {indent}OPEN  {token.type:<25} map={token.map}")

            if token.map and len(open_stack) == 1:  # depth-0 only
                sliced = lines[token.map[0]:token.map[1]]
                print(f"    slice [{token.map[0]}:{token.map[1]}]: {sliced}")

        elif token.type in CONTAINER_CLOSES:
            indent = "  " * (len(open_stack) - 1)
            map_note = "← None!" if token.map is None else ""
            print(f"  {indent}CLOSE {token.type:<25} map={token.map} {map_note}")
            if open_stack:
                open_stack.pop()

    print()


def main():
    for name, text in TEST_CASES.items():
        report_case(name, text)


if __name__ == "__main__":
    main()
