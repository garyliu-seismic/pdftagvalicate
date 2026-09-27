"""Report-only checks for catalog/XMP metadata (no mutation).

Mirrors the three repairs in :mod:`metadata_repairs` so ``--check`` can
report the same PDF/UA metadata problems the repair pass would fix.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Name

from .pdfutil import PDFUAID_NS, get_xmp_property
from .types import CheckReport


def check_pdf_ua_identifier(pdf: pikepdf.Pdf) -> CheckReport:
    name = "PDF/UA identifier (pdfuaid:part)"
    part = get_xmp_property(pdf, "part", PDFUAID_NS)
    if part == "1":
        return CheckReport(name, 0, "pdfuaid:part is set to 1.")
    return CheckReport(name, 1, "Missing PDF/UA identifier (pdfuaid:part = 1).")


def check_mark_info(pdf: pikepdf.Pdf) -> CheckReport:
    name = "MarkInfo /Marked"
    mark_info = pdf.Root.get(Name.MarkInfo)
    marked = mark_info.get(Name.Marked) if mark_info is not None else None
    if marked:
        return CheckReport(name, 0, "/MarkInfo /Marked is true.")
    return CheckReport(name, 1, "/MarkInfo /Marked is missing or false.")


def check_display_doc_title(pdf: pikepdf.Pdf) -> CheckReport:
    name = "ViewerPreferences /DisplayDocTitle"
    vp = pdf.Root.get(Name.ViewerPreferences)
    display = vp.get(Name.DisplayDocTitle) if vp is not None else None
    if display:
        return CheckReport(name, 0, "/DisplayDocTitle is true.")
    return CheckReport(name, 1, "/DisplayDocTitle is missing or false.")
