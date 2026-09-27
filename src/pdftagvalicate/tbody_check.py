"""Report-only fake TBody wrapper check (no mutation)."""

from __future__ import annotations

import pikepdf

from . import tbody_repair
from .pdfutil import is_tagged
from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Fake TBody wrappers"
    if not is_tagged(pdf):
        return CheckReport(name, 0, "Document is not tagged - skipped.")

    tables = tbody_repair.collect_fake_tables(pdf)
    if not tables:
        return CheckReport(name, 0, "No fake-table wrappers found.")
    return CheckReport(name, len(tables), f"{len(tables)} fake Table->TBody->TR->TD chain(s).")
