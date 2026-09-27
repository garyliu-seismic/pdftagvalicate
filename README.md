# pdftagvalicate

PDF/UA tag-tree validator and auto-repair tool.

License note: pikepdf is MPL-2.0 and qpdf is Apache-2.0 — both permissive,
free for closed-source/commercial use, unlike iText's AGPL/commercial dual
license. This tool is not a replacement for the production merge pipeline;
that continues to run on iText inside the .NET service. This is a
lightweight side tool for ad-hoc validation/repair.

## What it repairs

| Flag              | Repair                                                                 |
|-------------------|-------------------------------------------------------------------------|
| `--metadata`      | `pdfuaid:part` XMP identifier, `/MarkInfo /Marked`, `/ViewerPreferences /DisplayDocTitle` |
| `--title`         | Back-fills XMP `dc:title` from `/Info /Title` when missing              |
| `--lang`          | Sets catalog `/Lang` from XMP `dc:language` (or `--lang-value`) when missing |
| `--fix-tbody`     | Dissolves fake `Table -> TBody -> TR -> TD` wrapper chains with no real tabular content |
| `--th-scope`      | Adds a `/Scope` (`/Column` or `/Row`) attribute to `<TH>` cells missing one |
| `--link-nesting`  | Wraps orphaned `Link` annotations in a `<Link>` struct element + `ParentTree` entry |
| `--all`           | All of the above (also the default when no repair flag is given)        |

## What it checks

`--check` runs a report-only PDF/UA audit (PAC-style) and writes nothing.
Each repair has a matching check, plus three extra report-only checks:

| Flag              | Check                                                                  |
|-------------------|-------------------------------------------------------------------------|
| `--metadata`      | Missing `pdfuaid:part`, `/MarkInfo /Marked`, `/ViewerPreferences /DisplayDocTitle` |
| `--title`         | Missing XMP `dc:title`                                                  |
| `--lang`          | Missing catalog `/Lang`                                                 |
| `--th-scope`      | `<TH>` cells missing `/Scope`                                           |
| `--link-nesting`  | Orphaned `Link` annotations                                             |
| `--fix-tbody`     | Fake `Table -> TBody -> TR -> TD` wrapper chains                        |
| `--alt-text`      | `<Figure>` elements missing `/Alt` (report-only)                        |
| `--fonts`         | Unembedded / Type3 / missing-`ToUnicode` fonts (report-only)            |
| `--suspects`      | `/MarkInfo /Suspects` flag (report-only)                                |
| `--all`           | All of the above (also the default when no check flag is given)         |

## Install

```bash
pip install -e ".[dev]"
```

## CLI usage

```bash
# Report what would change, without writing a file
python -m pdftagvalicate input.pdf --dry-run

# Apply all repairs and write the result
python -m pdftagvalicate input.pdf output.pdf

# Apply only specific repairs
python -m pdftagvalicate input.pdf output.pdf --th-scope --link-nesting

# Audit a document (report-only, writes nothing)
python -m pdftagvalicate input.pdf --check

# Audit only specific checks
python -m pdftagvalicate input.pdf --check --metadata --lang --alt-text

# Machine-readable output (for tool-calling agents)
python -m pdftagvalicate input.pdf output.pdf --json
python -m pdftagvalicate input.pdf --check --json
```

`--json` prints a single JSON object to stdout:

```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "dry_run": false,
  "total_fixed": 3,
  "reports": [
    {"name": "MarkInfo /Marked", "fixed": 1, "detail": "Set /MarkInfo /Marked = true."}
  ]
}
```

Exit codes: `0` = nothing to repair (or no issues in `--check`), `1` =
repairs made / needed for `--dry-run` (or issues found in `--check`), `2` =
error (details on stderr, or in the JSON `error` field with `--json`).

## Library usage

```python
import pikepdf
from pdftagvalicate import RepairOptions, run_repairs

with pikepdf.open("input.pdf") as pdf:
    reports = run_repairs(pdf, RepairOptions.all())
    pdf.save("output.pdf")
```

## Tests

```bash
pytest
```
