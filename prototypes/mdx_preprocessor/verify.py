"""
Verification script for MDX preprocessor output.

Checks that all tags which should have been removed or converted are absent
from the preprocessed file. Tags are organized by category matching the
Extension: Mintlify/MDX Preprocessing spec in 001_BASIC_MECHANICAL.md.

Each tag entry specifies:
  - pattern: regex to search for in the output
  - description: human-readable label
  - implemented: whether the preprocessor currently handles this tag

Unimplemented tags are reported as SKIP (not failures) — this lets us track
the full surface area before each one is added to the preprocessor.

Usage:
    python verify.py <preprocessed.md>
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class TagSpec:
    pattern: str          # regex to search for in output (should NOT appear)
    description: str      # human-readable name
    implemented: bool     # True = preprocessor handles it; False = not yet


# ---------------------------------------------------------------------------
# Tag registry — extend here as tags are added to the preprocessor.
# Categories match spec: Structural (hard blockers) and Content wrappers.
# ---------------------------------------------------------------------------

STRUCTURAL_TAGS: list[TagSpec] = [
    # section
    TagSpec(r'<section\b[^>]*>', '<section title="..."> open', implemented=True),
    TagSpec(r'</section\s*>', '</section> close', implemented=True),
    # CodeGroup
    TagSpec(r'<CodeGroup\b[^>]*>', '<CodeGroup> open', implemented=True),
    TagSpec(r'</CodeGroup\s*>', '</CodeGroup> close', implemented=True),
    # Tabs / Tab
    TagSpec(r'<Tabs\b[^>]*>', '<Tabs> open', implemented=False),
    TagSpec(r'</Tabs\s*>', '</Tabs> close', implemented=False),
    TagSpec(r'<Tab\b[^>]*>', '<Tab> open', implemented=False),
    TagSpec(r'</Tab\s*>', '</Tab> close', implemented=False),
    # Accordion / AccordionGroup
    TagSpec(r'<AccordionGroup\b[^>]*>', '<AccordionGroup> open', implemented=False),
    TagSpec(r'</AccordionGroup\s*>', '</AccordionGroup> close', implemented=False),
    TagSpec(r'<Accordion\b[^>]*>', '<Accordion title="..."> open', implemented=False),
    TagSpec(r'</Accordion\s*>', '</Accordion> close', implemented=False),
    # Steps / Step
    TagSpec(r'<Steps\b[^>]*>', '<Steps> open', implemented=False),
    TagSpec(r'</Steps\s*>', '</Steps> close', implemented=False),
    TagSpec(r'<Step\b[^>]*>', '<Step> open', implemented=False),
    TagSpec(r'</Step\s*>', '</Step> close', implemented=False),
    # Card / CardGroup
    TagSpec(r'<CardGroup\b[^>]*>', '<CardGroup> open', implemented=False),
    TagSpec(r'</CardGroup\s*>', '</CardGroup> close', implemented=False),
    TagSpec(r'<Card\b[^>]*>', '<Card title="..."> open', implemented=False),
    TagSpec(r'</Card\s*>', '</Card> close', implemented=False),
]

CONTENT_WRAPPER_TAGS: list[TagSpec] = [
    # Admonitions
    TagSpec(r'<Tip\b[^>]*>', '<Tip> open', implemented=False),
    TagSpec(r'</Tip\s*>', '</Tip> close', implemented=False),
    TagSpec(r'<Note\b[^>]*>', '<Note> open', implemented=False),
    TagSpec(r'</Note\s*>', '</Note> close', implemented=False),
    TagSpec(r'<Warning\b[^>]*>', '<Warning> open', implemented=False),
    TagSpec(r'</Warning\s*>', '</Warning> close', implemented=False),
    TagSpec(r'<Info\b[^>]*>', '<Info> open', implemented=False),
    TagSpec(r'</Info\s*>', '</Info> close', implemented=False),
    TagSpec(r'<Danger\b[^>]*>', '<Danger> open', implemented=False),
    TagSpec(r'</Danger\s*>', '</Danger> close', implemented=False),
    # Frame
    TagSpec(r'<Frame\b[^>]*>', '<Frame> open', implemented=False),
    TagSpec(r'</Frame\s*>', '</Frame> close', implemented=False),
    # API doc fields
    TagSpec(r'<ResponseField\b[^>]*>', '<ResponseField> open', implemented=False),
    TagSpec(r'</ResponseField\s*>', '</ResponseField> close', implemented=False),
    TagSpec(r'<ParamField\b[^>]*>', '<ParamField> open', implemented=False),
    TagSpec(r'</ParamField\s*>', '</ParamField> close', implemented=False),
]

ALL_TAGS = [
    ('Structural (hard blockers)', STRUCTURAL_TAGS),
    ('Content wrappers', CONTENT_WRAPPER_TAGS),
]


def find_matches(text: str, pattern: str) -> list[tuple[int, str]]:
    """Return list of (line_number, line_text) for each match."""
    results = []
    for i, line in enumerate(text.splitlines(), start=1):
        if re.search(pattern, line, re.IGNORECASE):
            results.append((i, line.rstrip()))
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: verify.py <preprocessed.md>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    text = path.read_text()
    print(f"Verifying: {path}")
    print(f"Lines: {len(text.splitlines())}")
    print()

    failures = 0
    skipped = 0
    occurences = 0

    for category, tags in ALL_TAGS:
        print(f"── {category} ──")
        for spec in tags:
            if not spec.implemented:
                print(f"  SKIP  {spec.description}")
                skipped += 1
                continue

            matches = find_matches(text, spec.pattern)
            if matches:
                print(f"  FAIL  {spec.description} — {len(matches)} occurrence(s):")
                for lineno, line in matches[:5]:  # show up to 5
                    print(f"          line {lineno}: {line[:120]}")
                if len(matches) > 5:
                    print(f"          ... and {len(matches) - 5} more")
                failures += 1
                occurences += len(matches)
            else:
                print(f"  OK    {spec.description}")
        print()

    print("─" * 50)
    implemented = sum(len(tags) for _, tags in ALL_TAGS) - skipped
    print(f"Result: {implemented - failures}/{implemented} implemented checks passed"
          f"  ({skipped} skipped — not yet implemented)")
    print()

    if failures:
        print(f"FAIL — {failures} tag(s) still present in output with {occurences} total occurences.")
        sys.exit(1)
    else:
        print("OK — all implemented tags removed from output.")


if __name__ == '__main__':
    main()
