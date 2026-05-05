
### `pyproject.toml`

Standard PEP 517 format. Declare `markdown-it-py` and `pygments` as dependencies. Add a console script entry point:

```toml
[project.scripts]
fit = "fit.cli:main"
```

Install locally with `uv pip install -e .` or `pip install -e .`. Other projects can then `from fit import Document` after installing.

### `__init__.py` public surface

```python
from fit.measurer import Measurer
from fit.segment import Segment
from fit.document import Document
from fit.writer import Writer, DryRunWriter, WriterFactory
```

`process_file` and `_reduction_loop` are not exported — they are CLI/driver implementation details.

### `Document` API changes

Remove `args: argparse.Namespace` from `__init__` and `_parse` (to be renamed `parse`). Replace with explicit keyword arguments with defaults matching current CLI defaults:

```python
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
```

`Document.parse` (formerly `Document._parse`) gets the same signature. `is_unsplittable` currently reads `self._args.min_segment_count` — replace with `self._min_segment_count` stored at construction. Any other internal reference to `args.X` becomes a stored instance variable `self._X`.

`inline_languages=None` means no language preference — no internal fallback. The CLI sets its own default (`["python", "javascript", "typescript"]`) before calling into the library.

### Subcommand structure

`cli.py` is a thin dispatcher — it creates the top-level parser, registers subcommands, and calls `args.func(args)`:

```python
# cli.py
def main():
    parser = argparse.ArgumentParser(prog="fit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    from fit.commands.generate import add_parser as add_generate
    from fit.commands.measure import add_parser as add_measure
    add_generate(subparsers)
    add_measure(subparsers)
    args = parser.parse_args()
    args.func(args)
```

Each subcommand package/module exposes two functions: `add_parser(subparsers)` to register its args, and `run(args)` as its entry point (assigned to `args.func` by `add_parser`).

**`commands/generate/`** is a package rather than a flat module so that level implementations can live alongside the dispatcher without crowding the top-level namespace. The dispatch pattern:

```python
# commands/generate/__init__.py
def add_parser(subparsers):
    p = subparsers.add_parser("generate", help="Generate a FIT from a markdown file")
    p.add_argument("path")
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--soft-threshold", ...)
    # ... remaining args
    p.set_defaults(func=run)
    return p

def run(args):
    from fit.commands.generate import level1
    level_map = {1: level1}
    impl = level_map.get(args.level)
    if impl is None:
        raise SystemExit(f"Unknown level: {args.level}")
    impl.run(args)
```

`level1.py` contains the current `process_file` / `_reduction_loop` logic (moved from `driver.py` or delegating to it). Future levels add `level2.py`, `level3.py`, etc. — the dispatch table grows, nothing else changes. In a later version, `run()` may auto-select the best available level based on what's installed at runtime.

**`commands/measure.py`** is a flat module (no level dispatch needed). Interface:

```
fit measure <path> [--soft-threshold N] [--hard-threshold N]
```

Output: token count plus a status indicator derived from the thresholds:
- Below soft threshold → `2137 tokens — fits`
- Above soft, below hard → `3740 tokens — exceeds soft threshold`
- Above hard → `5200 tokens — exceeds hard threshold`

Only `--soft-threshold` and `--hard-threshold` are relevant args (no inline threshold, languages, or dry-run). Single-file input for now; multi-file support is a natural future extension.

`argparse.Namespace` never crosses into library code (core classes in `measurer.py`, `segment.py`, `document.py`, `writer.py`, `driver.py`).

### Tests

- Extract shared fixtures and helpers (`measurer`, `default_args`, `make_doc`, `make_segment`, `sys.path` insert) into `tests/conftest.py`
- Split `test_fit_generator.py` — one file per tested class (see layout above)
- `default_args` fixture becomes a plain dict or direct kwargs rather than `argparse.Namespace`, matching the new API

### Execution order

1. Create `pyproject.toml`
2. Create `src/fit/` directory and split `fit_generator.py` into per-class modules, preserving all imports
3. Refactor `Document.__init__` and `Document.parse` — remove `args`, add explicit kwargs
4. Update all internal call sites that read `args.X`
5. Create `commands/` package — `generate/` (with `__init__.py` + `level1.py`) and `measure.py`; write `cli.py` as thin dispatcher
6. Write `__init__.py`
7. Restructure `tests/` — create `conftest.py`, split test file per class
8. `uv pip install -e .` and run full test suite — all tests should pass

---
