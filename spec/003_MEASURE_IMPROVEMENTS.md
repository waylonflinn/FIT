# FIT CLI — Measure Improvements

_Effort: Focused (2)_

_Capability: Compositional (2)_

_Elapsed: —_

_Daily logs: Requirements: 2026-07-11_

_Status: Requirements (1/10)_

_Requires: 001_

_Updated: 2026-07-20_

---

## Goal

Two improvements surfaced by the first real consumer deployment (the sloplight
design corpus, thresholds raised to 5k/8k per `CONTEXT_DEGRADATION.md`):

1. **Native `.fit.toml` threshold configuration**, resolved at the CLI level —
   above the `measure` subcommand — so that `generate` (and any future
   subcommand taking thresholds) shares it for free.
2. **Multi-document measure**: accept multiple files and/or directories in a
   single invocation; directories are a precheck that autopopulates the file
   list with the markdown files they contain.

Together these turn threshold checking from a per-file, flags-retyped chore
into a one-command corpus sweep that respects per-subtree calibration.

---

## Requirements

### 1. `.fit.toml` configuration (CLI-level, not measure-specific)

- **Placement (user note, 2026-07-11):** resolve in the top-level CLI layer
  (`cli.py`), before subcommand dispatch — not inside `measure`. `generate`
  gets it in the same change; future subcommands inherit it.
- **Resolution order** (highest wins):
  1. Explicit CLI flags (`--soft-threshold` / `--hard-threshold`).
  2. Nearest `.fit.toml` found walking up from the **target document's**
     directory to the filesystem root.
  3. Package defaults (3000 / 5000).
- **Independent resolution:** resolve soft and hard independently. For
  example, an explicit `--soft-threshold` may be combined with a hard
  threshold from `.fit.toml`; providing one flag does not suppress config
  resolution for the other.
- **Per-target resolution:** with multiple targets (feature 2), each file
  resolves against its *own* nearest config. This is deliberate — it's what
  makes nested overrides work (e.g. a work-unit folder pinned to 3000/5000
  for cross-model comparability inside a repo calibrated to 5000/8000).
- **Generate inheritance:** `generate` resolves thresholds from its
  user-supplied root target once. Any descendants produced and processed by
  recursive generation inherit those resolved values for that run; generation
  does not re-resolve configuration against newly created descendants.
- **Format:**

  ```toml
  [thresholds]
  soft = 5000
  hard = 8000
  ```

  Keys mirror the CLI flag names (without the `--…-threshold` decoration).
  Other sections/keys (e.g. `generate`'s inline thresholds) MAY be added
  later under the same mirroring rule.
- **Validation and compatibility:**
  - Malformed TOML is a hard error that identifies the config file.
  - Threshold values must be positive integers, and soft must not exceed hard.
    Violations are hard errors.
  - Unknown keys inside `[thresholds]` are ignored with a warning. Unknown
    top-level sections are ignored silently so future sections remain
    forward-compatible.
  - Preserve the package's Python 3.10 support: use `tomllib` where available
    and a compatible fallback on Python 3.10.
- **Transparency:** output reports where each threshold came from
  (flag / config file path / default) under verbose output.
- **Sync obligation:** the convention is already documented in
  `skills/fit-creation/SKILL.md` (which currently instructs agents to pass
  resolved values as flags). When this lands, update the skill to drop the
  manual-resolution instruction. Example consumer config:
  `~/Development/sloplight/.fit.toml`.

### 2. Multi-document measure

- **Invocation:** `fit measure [options] <path> [<path> ...]` — any mix of
  files and directories.
- **Directory precheck:** each directory argument is expanded to the markdown
  files it contains, then processing proceeds exactly as if those files had
  been listed on the command line. One feature, one code path; the directory
  case is only an argument-expansion step.
- **Expansion rules:**
  - Matches `.md` files only. `.mdx` files are not included implicitly.
  - Flat by default: a directory argument includes only files directly within
    that directory.
  - `-r` / `--recursive` includes matching files in the directory's complete
    subtree.
  - **Excludes generated backups:** paths ending in `.md.unfit`, `.unfit.md`,
    `.orig.md`, or `.md.orig` never enter the list implicitly. Both ordering
    conventions are recognized because existing backup extension behavior is
    inconsistent and may change after a separate review. Explicitly listing
    one still works.
  - Overlapping arguments are deduplicated, so naming both a directory and a
    file within it measures that file once.
  - Deterministic ordering (sorted paths) for stable output diffs.
  - A directory that contains no eligible files is an error.
  - Missing paths and explicitly listed non-Markdown files are errors rather
    than silently skipped, except that files matching a recognized backup
    form remain explicitly measurable.
- **Output:** retain the existing per-file line for each target. When more
  than one file is measured, append a trailing summary containing:
  - total files measured;
  - counts of fits / over-soft / over-hard;
  - total token count across all measured files.
  The summary does not list largest offenders.
- **Exit code:** return `1` when any file exceeds its own resolved hard
  threshold, making a corpus sweep usable in CI or a pre-commit hook. Soft
  threshold violations alone do not produce a nonzero exit.

---

## Motivating use

```bash
# whole-corpus sweep, thresholds from sloplight/.fit.toml (5000/8000),
# unit folders with their own .fit.toml resolving tighter automatically:
fit measure --recursive design/image_store/
```
