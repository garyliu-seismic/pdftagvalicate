"""Command-line interface for pdftagvalicate.

Designed to be invoked both by humans and by an LLM tool-calling loop (e.g.
Claude Code shelling out to it): pass --json to get a single machine-parsable
JSON object on stdout instead of the human-readable log, and rely on the
process exit code to know whether anything changed.

Exit codes: 0 = nothing to repair, 1 = repairs made (or needed, for
--dry-run), 2 = error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pikepdf

from .checks import run_checks
from .repairs import run_repairs
from .types import CheckResult, RepairOptions, RepairReport, Severity, ValidateOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdftagvalicate",
        description="PDF/UA tag-tree validator and auto-repair tool (pikepdf-based).",
    )
    parser.add_argument("input", type=Path, help="Path to the input PDF.")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Path to write the repaired PDF (required unless --dry-run).",
    )
    parser.add_argument("--all", action="store_true", help="Apply all safe repairs (default when no repair flag given).")
    parser.add_argument("--metadata", action="store_true", help="Fix pdfuaid:part, /ViewerPreferences, /MarkInfo.")
    parser.add_argument("--th-scope", action="store_true", help="Add /Scope attribute to <TH> cells missing it.")
    parser.add_argument(
        "--link-nesting", action="store_true", help="Wrap orphaned Link annotations inside <Link> struct elements."
    )
    parser.add_argument("--fix-tbody", action="store_true", help="Dissolve fake Table->TBody->TR->TD wrapper chains.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing an output file."
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run read-only PDF/UA checks and report Severity per clause (no output file written).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="With --validate: treat Warning-severity findings as failures (exit 1).",
    )
    parser.add_argument("--json", action="store_true", help="Print a single JSON report to stdout instead of logs.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.validate:
        # --validate is read-only: no output path needed or allowed.
        return _run_validate(args)

    if not args.dry_run and args.output is None:
        parser.error("output path is required unless --dry-run is given")

    if not args.input.exists():
        return _fail(f"File not found: {args.input}", as_json=args.json)

    options = RepairOptions(
        metadata=args.metadata,
        th_scope=args.th_scope,
        link_nesting=args.link_nesting,
        fix_tbody=args.fix_tbody,
        dry_run=args.dry_run,
    )
    if args.all or not options.any_selected:
        options = RepairOptions.all(dry_run=args.dry_run)

    if not args.json:
        print(f"pdftagvalicate: {args.input.name}")
        if options.dry_run:
            print("(dry-run - no file will be written)")
        print("=" * 72)

    try:
        reports = _run(args.input, args.output, options)
    except Exception as ex:  # noqa: BLE001
        return _fail(f"Error: {ex}", as_json=args.json)

    total_fixed = sum(r.fixed for r in reports)

    if args.json:
        print(
            json.dumps(
                {
                    "input": str(args.input),
                    "output": str(args.output) if args.output else None,
                    "dry_run": options.dry_run,
                    "total_fixed": total_fixed,
                    "reports": [r.to_dict() for r in reports],
                },
                indent=2,
            )
        )
    else:
        for r in reports:
            status = "FIXED" if r.fixed > 0 else "OK   "
            print(f"[{status}] {r.name}")
            if r.detail:
                print(f"         {r.detail}")
        print()
        if options.dry_run:
            print(f"Dry-run summary: {total_fixed} item(s) would be repaired.")
        elif total_fixed > 0:
            print(f"Repaired {total_fixed} item(s). Written to: {args.output}")
        else:
            print(f"Nothing to repair. Written to: {args.output}")

    return 1 if total_fixed > 0 else 0


def _run_validate(args) -> int:
    """Entry point for ``--validate`` mode."""
    if not args.input.exists():
        return _fail(f"File not found: {args.input}", as_json=args.json)

    options = ValidateOptions(strict=args.strict)

    if not args.json:
        print(f"pdftagvalicate --validate: {args.input.name}")
        if options.strict:
            print("(--strict: Warning counts as failure)")
        print("=" * 72)

    try:
        with pikepdf.open(args.input) as pdf:
            results = run_checks(pdf, options)
    except Exception as ex:  # noqa: BLE001
        return _fail(f"Error: {ex}", as_json=args.json)

    threshold = options.fail_threshold
    any_fail = any(r.severity >= threshold for r in results)

    if args.json:
        print(
            json.dumps(
                {
                    "input": str(args.input),
                    "strict": options.strict,
                    "checks": [r.to_dict() for r in results],
                },
                indent=2,
            )
        )
    else:
        for r in results:
            tag = r.severity.value.upper()[:4].ljust(4)
            print(f"[{tag}] {r.id}  {r.name}")
            if r.detail and r.severity != Severity.Pass:
                print(f"         {r.detail}")
        print()
        if any_fail:
            fails = [r for r in results if r.severity >= threshold]
            print(f"{len(fails)} check(s) failed.")
        else:
            print("All checks passed.")

    return 1 if any_fail else 0


def _run(input_path: Path, output_path: Path | None, options: RepairOptions) -> list[RepairReport]:
    if options.dry_run:
        with pikepdf.open(input_path) as pdf:
            return run_repairs(pdf, options)

    # Resolve both paths so that "input.pdf output/../input.pdf" is also detected.
    in_resolved = input_path.resolve()
    out_resolved = output_path.resolve() if output_path is not None else None
    in_place = in_resolved == out_resolved

    # pikepdf.open() supports allow_overwriting_input=True for in-place saves;
    # the flag must be set at open time, not save time.
    with pikepdf.open(input_path, allow_overwriting_input=in_place) as pdf:
        reports = run_repairs(pdf, options)
        pdf.save(output_path)
        return reports


def _fail(message: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"error": message}))
    else:
        print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
