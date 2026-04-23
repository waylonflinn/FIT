#!/usr/bin/env python3
"""
Language detection prototype for FIT generator.

For each fenced code block in the input document:
  - Records the actual info string (ground truth)
  - Runs pygments, whats-that-code, and codelang-detect against the content
  - Reports per-block results and threshold/tradeoff curves

Usage:
    python detect.py <markdown_file>
"""

import sys
from pathlib import Path

from markdown_it import MarkdownIt
from pygments.lexers import guess_lexer, get_lexer_by_name
from pygments.util import ClassNotFound
from whats_that_code.election import guess_language_all_methods
from codelang_detect import detect as _codelang_detect_raw


# Map codelang-detect short codes to normalized names
CODELANG_MAP = {
    "py": "python", "ts": "typescript", "js": "javascript",
    "cs": "c#", "cpp": "c++", "c": "c", "go": "go", "java": "java",
    "rb": "ruby", "sh": "shell", "php": "php", "json": "json",
    "rs": "rust", "kt": "kotlin", "html": "html", "css": "css",
    "sql": "sql", "xml": "xml", "yaml": "yaml", "dart": "dart",
    "scala": "scala", "swift": "swift", "r": "r", "groovy": "groovy",
    "cbl": "cobol", "sol": "solidity",
}


def normalize_lang(info_string: str) -> str:
    """Normalize a fenced code block info string to a canonical language name."""
    tag = info_string.strip().split()[0].lower() if info_string.strip() else ""
    if not tag:
        return ""
    try:
        lexer = get_lexer_by_name(tag)
        return lexer.name.lower()
    except ClassNotFound:
        return tag


def pygments_detect(content: str) -> tuple[str, float]:
    """Return (language_name, confidence) from pygments.guess_lexer."""
    try:
        lexer = guess_lexer(content)
        score = lexer.analyse_text(content)
        return lexer.name.lower(), score
    except ClassNotFound:
        return "", 0.0


def wtc_detect(content: str) -> str:
    """Return language name from whats-that-code, or '' if no result."""
    try:
        result = guess_language_all_methods(content)
        if not result:
            return ""
        # API returns either a string or a list depending on version
        if isinstance(result, list):
            return result[0].lower() if result else ""
        return result.lower()
    except Exception:
        return ""


def codelang_detect(content: str) -> str:
    """Return normalized language name from codelang-detect, or '' if no result."""
    try:
        result = _codelang_detect_raw(content)
        if result:
            return CODELANG_MAP.get(result.lower(), result.lower())
        return ""
    except Exception:
        return ""


def extract_blocks(path: Path) -> list[dict]:
    """Extract fenced code blocks from a markdown file."""
    md = MarkdownIt()
    source = path.read_text(encoding="utf-8")
    tokens = md.parse(source)

    blocks = []
    for tok in tokens:
        if tok.type == "fence":
            info = tok.info.strip()
            content = tok.content
            blocks.append({
                "info": info,
                "ground_truth": normalize_lang(info),
                "content": content,
            })
    return blocks


def correct_mark(predicted: str, ground_truth: str) -> str:
    if predicted and predicted != "(none)" and predicted == ground_truth:
        return "✓"
    return ""


def run(path: Path) -> None:
    print(f"Document: {path}")
    print("Loading blocks...\n")

    blocks = extract_blocks(path)
    print(f"Found {len(blocks)} fenced code blocks.\n")

    if not blocks:
        print("Nothing to analyze.")
        return

    # --- Per-block detection ---
    results = []
    for i, b in enumerate(blocks):
        py_lang, py_score = pygments_detect(b["content"])
        wtc_lang = wtc_detect(b["content"])
        cd_lang = codelang_detect(b["content"])
        results.append({
            "index": i + 1,
            "info": b["info"] or "(none)",
            "ground_truth": b["ground_truth"] or "(none)",
            "py_lang": py_lang or "(none)",
            "py_score": py_score,
            "wtc_lang": wtc_lang or "(none)",
            "cd_lang": cd_lang or "(none)",
            "content_len": len(b["content"]),
        })

    # --- Per-block table ---
    col_w = [4, 14, 14, 18, 6, 14, 14, 6]
    headers = ["#", "info string", "ground truth", "pygments", "score", "whats-that-code", "codelang-detect", "chars"]
    sep = "  ".join("-" * w for w in col_w)
    row_fmt = "  ".join(f"{{:<{w}}}" for w in col_w)

    print(row_fmt.format(*headers))
    print(sep)
    for r in results:
        gt = r["ground_truth"]
        py_cell = f"{r['py_lang']} {correct_mark(r['py_lang'], gt)}".strip()
        wtc_cell = f"{r['wtc_lang']} {correct_mark(r['wtc_lang'], gt)}".strip()
        cd_cell = f"{r['cd_lang']} {correct_mark(r['cd_lang'], gt)}".strip()
        print(row_fmt.format(
            str(r["index"]),
            r["info"][:col_w[1]],
            gt[:col_w[2]],
            py_cell[:col_w[3]],
            f"{r['py_score']:.2f}",
            wtc_cell[:col_w[5]],
            cd_cell[:col_w[6]],
            str(r["content_len"]),
        ))

    annotated = [r for r in results if r["ground_truth"] != "(none)"]

    # --- Pygments threshold tradeoff ---
    print(f"\n--- Pygments threshold tradeoff (annotated blocks: {len(annotated)} of {len(results)}) ---\n")
    hdr = f"{'threshold':>10}  {'correct':>8}  {'→Code':>6}  {'covered':>8}  {'accuracy':>9}"
    print(hdr)
    print("-" * len(hdr))
    for thresh in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
        correct = sum(1 for r in annotated if r["py_score"] >= thresh and r["py_lang"] == r["ground_truth"])
        to_code = sum(1 for r in annotated if r["py_score"] < thresh)
        covered = len(annotated) - to_code
        accuracy = correct / covered if covered > 0 else 0.0
        print(f"{thresh:>10.1f}  {correct:>8}  {to_code:>6}  {covered:>8}  {accuracy:>8.0%}")

    # --- whats-that-code summary ---
    print(f"\n--- whats-that-code summary (annotated blocks: {len(annotated)} of {len(results)}) ---\n")
    wtc_results = [r for r in annotated if r["wtc_lang"] != "(none)"]
    wtc_correct = sum(1 for r in wtc_results if r["wtc_lang"] == r["ground_truth"])
    coverage = len(wtc_results)
    accuracy = wtc_correct / coverage if coverage > 0 else 0.0
    print(f"  Result returned:  {coverage} of {len(annotated)} ({coverage/len(annotated):.0%})")
    print(f"  No result:        {len(annotated) - coverage} blocks (→ 'Code')")
    print(f"  Correct:          {wtc_correct} of {coverage} ({accuracy:.0%} accuracy)")
    print("  (no confidence score — threshold tradeoff is result vs. no-result only)")

    # --- codelang-detect summary ---
    print(f"\n--- codelang-detect summary (annotated blocks: {len(annotated)} of {len(results)}) ---\n")
    cd_results = [r for r in annotated if r["cd_lang"] != "(none)"]
    cd_correct = sum(1 for r in cd_results if r["cd_lang"] == r["ground_truth"])
    cd_coverage = len(cd_results)
    cd_accuracy = cd_correct / cd_coverage if cd_coverage > 0 else 0.0
    print(f"  Result returned:  {cd_coverage} of {len(annotated)} ({cd_coverage/len(annotated):.0%})")
    print(f"  No result:        {len(annotated) - cd_coverage} blocks (→ 'Code')")
    print(f"  Correct:          {cd_correct} of {cd_coverage} ({cd_accuracy:.0%} accuracy)")
    print("  (no confidence score — threshold tradeoff is result vs. no-result only)")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <markdown_file>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}")
        sys.exit(1)
    run(path)


if __name__ == "__main__":
    main()
