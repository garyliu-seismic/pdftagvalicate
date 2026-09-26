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
| `--fix-tbody`     | Dissolves fake `Table -> TBody -> TR -> TD` wrapper chains with no real tabular content |
| `--th-scope`      | Adds a `/Scope` (`/Column` or `/Row`) attribute to `<TH>` cells missing one |
| `--link-nesting`  | Wraps orphaned `Link` annotations in a `<Link>` struct element + `ParentTree` entry |
| `--all`           | All of the above (also the default when no repair flag is given)        |

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

# Machine-readable output (for tool-calling agents)
python -m pdftagvalicate input.pdf output.pdf --json
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

Exit codes: `0` = nothing to repair, `1` = repairs made (or needed, for
`--dry-run`), `2` = error (details on stderr, or in the JSON `error` field
with `--json`).

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
