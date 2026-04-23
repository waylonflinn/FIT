"""
Writer — write document splits to the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from fit.document import Document


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

        for seg in document:
            if seg.is_inline:
                print(f"[DRY RUN]   INLINE: {seg.name} ({seg.measure()} tokens)")
            else:
                subdoc_path = subdoc_dir / f"{seg.name}.md"
                print(f"[DRY RUN]   SUBDOC: {seg.name} -> {subdoc_path} ({seg._measurer.measure(seg.body)} tokens)")

        # DryRunWriter returns [] — no files created, driver loop won't recurse
        return []


class WriterFactory:
    """Factory for Writer instances."""

    @staticmethod
    def create(dry_run: bool = False) -> "Writer | DryRunWriter":
        if dry_run:
            return DryRunWriter()
        return Writer()
