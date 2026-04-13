#!/usr/bin/env python3
"""
fit_split.py - Mechanical FIT (Fitted Information Tree) splitter

Splits a markdown file at H2 boundaries into:
  - Root doc (same path): H2 heading + first paragraph + link to sub-doc
  - Sub-docs: full section content, in a folder named after the source file

Usage:
    python3 fit_split.py <source.md>

Example:
    python3 fit_split.py /home/henry/doc/anthropic/build-with-claude/prompt-caching.md
    -> rewrites prompt-caching.md as root doc
    -> writes prompt-caching/how-prompt-caching-works.md, etc.
"""

import sys
import re
import os
import shutil

TRIVIAL_ADDITION_THRESHOLD = 100  # chars; allow for a trailing note or short line on first paragraph
MINIMUM_SUBDOC_THRESHOLD = 2000 # chars; do not create subdocuments for small sections

def slugify(text):
    """Convert heading text to a filename slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def parse_sections(content):
    """
    Split markdown into (preamble, sections).

    preamble: everything before the first H2 (list of lines)
    sections: list of (heading_text, body_text) tuples

    Skips H2 lines inside fenced code blocks.
    """
    lines = content.split("\n")
    preamble = []
    sections = []
    current_heading = None
    current_body = []
    in_fence = False

    for line in lines:
        # Track fenced code blocks (``` or ~~~)
        if re.match(r"^(```|~~~)", line):
            in_fence = not in_fence

        if not in_fence and line.startswith("## "):
            if current_heading is None:
                # Transition: preamble → first section
                preamble = current_body
                current_body = []
            else:
                # Transition: section → next section
                sections.append((current_heading, "\n".join(current_body)))
                current_body = []
            current_heading = line[3:].strip()
        else:
            current_body.append(line)

    # Last section
    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_body)))
    elif current_body:
        preamble = current_body

    return preamble, sections


def first_paragraph(body_text):
    """
    Extract the first non-empty prose paragraph from section body.
    Skips code blocks, tables, and blank-line-only content.
    Includes initial headings and rules.
    """
    paragraphs = re.split(r"\n\s*\n", body_text.strip())

    first_paragraph = []
    for p in paragraphs:
        p = p.strip()
        # include any preceding headings or rules
        if p and (p.startswith("#") or p.startswith("---")):
            first_paragraph.append(p)
        elif p and not p.startswith("```") and not p.startswith("|") and not p.startswith("~~~"):
            first_paragraph.append(p)
            return "\n".join(first_paragraph)
    return ""


def main():
    if len(sys.argv) < 2:
        print("Usage: fit_split.py <source.md>")
        sys.exit(1)

    source_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(source_path):
        print(f"Error: file not found: {source_path}")
        sys.exit(1)

    with open(source_path, "r") as f:
        content = f.read()

    source_dir = os.path.dirname(source_path)
    source_name = os.path.splitext(os.path.basename(source_path))[0]

    backup_path = os.path.join(source_dir, source_name + ".orig.md")
    shutil.copy2(source_path, backup_path)
    print(f"Backup: {backup_path} (~{len(content)//4} tokens)")

    sub_dir = os.path.join(source_dir, source_name)

    preamble, sections = parse_sections(content)

    os.makedirs(sub_dir, exist_ok=True)

    root_parts = []

    # Preserve preamble (title, intro text) in root doc
    preamble_text = "\n".join(preamble).strip()
    

    if preamble_text:

        #preamble_body = re.sub(r"^#[^#].*\n?", "", preamble_text, flags=re.MULTILINE).strip()
        preamble_first_para = first_paragraph(preamble_text)
        preamble_is_trivial = (
            len(preamble_text) <= len(preamble_first_para) + TRIVIAL_ADDITION_THRESHOLD
            or len(preamble_text) < MINIMUM_SUBDOC_THRESHOLD
        )

        #print(f"preamble : {preamble_first_para}")
        if preamble_is_trivial:
            root_parts.append(preamble_text)
            root_parts.append("")
            print(f"  inline: (preamble) (~{len(preamble_text)//4} tokens)")
        else:
            sub_filename = "introduction.md"
            sub_path = os.path.join(sub_dir, sub_filename)
            rel_link = f"{source_name}/{sub_filename}"

            if preamble_first_para:
                root_parts.append(preamble_first_para)
                root_parts.append("")

            token_estimate = len(preamble_text) // 4
            root_parts.append(f"→ [{rel_link}]({rel_link}) (~{token_estimate} tokens)")
            root_parts.append("")

            with open(sub_path, "w") as f:
                f.write(preamble_text + "\n")
            print(f"  sub:  {sub_path} (~{token_estimate} tokens)")

    if not sections:
        print("No H2 sections found — nothing left to split.")
        sys.exit(0)

    for heading, body in sections:
        slug = slugify(heading)
        sub_filename = f"{slug}.md"
        sub_path = os.path.join(sub_dir, sub_filename)
        rel_link = f"{source_name}/{sub_filename}"

        first_para = first_paragraph(body)
        body_stripped = body.strip()
        is_trivial = len(body_stripped) <= len(first_para) + TRIVIAL_ADDITION_THRESHOLD or len(body_stripped) < MINIMUM_SUBDOC_THRESHOLD

        root_parts.append(f"## {heading}")
        root_parts.append("")
        if is_trivial:
            # Inline the full body — no sub-doc needed
            root_parts.append(body_stripped)
            root_parts.append("")
            print(f"  inline: {heading} (~{len(body_stripped)//4} tokens)")
        else:
            if first_para:
                root_parts.append(first_para)
                root_parts.append("")
            token_estimate = len(body_stripped) // 4
            root_parts.append(f"→ [{rel_link}]({rel_link}) (~{token_estimate} tokens)")
            root_parts.append("")

            sub_content = f"## {heading}\n\n{body_stripped}\n"
            with open(sub_path, "w") as f:
                f.write(sub_content)
            print(f"  sub:  {sub_path}  (~{token_estimate} tokens)")

    # Write root doc (overwrites source)
    root_content = "\n".join(root_parts).strip() + "\n"
    with open(source_path, "w") as f:
        f.write(root_content)
    token_estimate = len(root_content) // 4
    print(f"  root: {source_path} (~{token_estimate} tokens)")
    print(f"Done. {len(sections)} sections split.")


if __name__ == "__main__":
    main()
