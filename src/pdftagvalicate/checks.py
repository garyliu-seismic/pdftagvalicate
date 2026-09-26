"""Orchestrates running the selected set of PDF/UA validation checks.

All checks are read-only: no PDF is modified.  Each check returns a
:class:`~pdftagvalicate.types.CheckResult` with a Matterhorn clause ID,
a human-readable name, a :class:`~pdftagvalicate.types.Severity`, and a
detail string.

Mirrors the structure of ``repairs.py`` so the two can evolve in parallel.
"""

from __future__ import annotations

import pikepdf

from . import pdf_checks
from .types import CheckResult, ValidateOptions


def run_checks(pdf: pikepdf.Pdf, options: ValidateOptions) -> list[CheckResult]:
    results: list[CheckResult] = []

    # Step 2 — trivial catalog/trailer checks
    _run_one(results, lambda: pdf_checks.check_01_005(pdf))
    _run_one(results, lambda: pdf_checks.check_11_001(pdf))
    _run_one(results, lambda: pdf_checks.check_06_003(pdf))
    _run_one(results, lambda: pdf_checks.check_07_001(pdf))
    _run_one(results, lambda: pdf_checks.check_13_004(pdf))
    _run_one(results, lambda: pdf_checks.check_14_002(pdf))
    _run_one(results, lambda: pdf_checks.check_14_003(pdf))

    # Step 3 — moderate struct-tree / font / annotation checks
    _run_one(results, lambda: pdf_checks.check_09_001(pdf))
    _run_one(results, lambda: pdf_checks.check_14_001(pdf))
    _run_one(results, lambda: pdf_checks.check_09_007(pdf))
    _run_one(results, lambda: pdf_checks.check_14_004(pdf))
    _run_one(results, lambda: pdf_checks.check_28_001(pdf))
    _run_one(results, lambda: pdf_checks.check_31_001(pdf))
    _run_one(results, lambda: pdf_checks.check_09_004(pdf))

    # Step 4 — hard checks (XMP namespace parse + content-stream tokenizer)
    _run_one(results, lambda: pdf_checks.check_06_001(pdf))
    _run_one(results, lambda: pdf_checks.check_09_006(pdf))

    # P4 — extended PAC checks
    _run_one(results, lambda: pdf_checks.check_08_001(pdf))
    _run_one(results, lambda: pdf_checks.check_01_002(pdf))
    _run_one(results, lambda: pdf_checks.check_06_004(pdf))
    _run_one(results, lambda: pdf_checks.check_11_002(pdf))
    _run_one(results, lambda: pdf_checks.check_09_008(pdf))
    _run_one(results, lambda: pdf_checks.check_15_001(pdf))
    _run_one(results, lambda: pdf_checks.check_15_002(pdf))
    _run_one(results, lambda: pdf_checks.check_17_001(pdf))
    _run_one(results, lambda: pdf_checks.check_17_002(pdf))
    _run_one(results, lambda: pdf_checks.check_22_001(pdf))
    _run_one(results, lambda: pdf_checks.check_24_001(pdf))
    _run_one(results, lambda: pdf_checks.check_24_002(pdf))
    _run_one(results, lambda: pdf_checks.check_28_002(pdf))

    return results


def _run_one(results: list[CheckResult], check) -> None:
    """Run a single check, catching any unexpected exception so the others
    still run; surfaces the failure as an Error-severity result."""
    try:
        results.append(check())
    except Exception as ex:  # noqa: BLE001
        from .types import Severity
        results.append(CheckResult(
            id="??-???",
            name=type(ex).__name__,
            severity=Severity.Error,
            detail=f"Unexpected error: {ex}",
        ))
