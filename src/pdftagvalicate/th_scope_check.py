"""Report-only TH /Scope check (no mutation)."""

from __future__ import annotations

import pikepdf

from . import th_scope_repair
from .pdfutil import is_tagged
from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "TH /Scope attribute"
    if not is_tagged(pdf):
        return CheckReport(name, 0, "Document is not tagged - skipped.")

    findings = th_scope_repair.collect_missing_scopes(pdf)
    if not findings:
        return CheckReport(name, 0, "All <TH> cells have /Scope.")
    return CheckReport(name, len(findings), f"{len(findings)} <TH> cell(s) missing /Scope.")
