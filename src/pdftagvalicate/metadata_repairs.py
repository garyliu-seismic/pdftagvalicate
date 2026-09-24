"""Tier 1 - metadata repairs (catalog-level, zero structural risk)."""

from __future__ import annotations

import pikepdf
from pikepdf import Dictionary, Name

from .types import RepairReport

_PDFUAID_NS = "http://www.aiim.org/pdfua/ns/id/"


def fix_pdf_ua_identifier(pdf: pikepdf.Pdf) -> RepairReport:
    """Adds pdfuaid:part = 1 to the XMP metadata stream (idempotent)."""
    name = "PDF/UA identifier (pdfuaid:part)"
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta.register_xml_namespace(_PDFUAID_NS, "pdfuaid")
            if meta.get("pdfuaid:part") == "1":
                return RepairReport(name, 0, "pdfuaid:part is already '1'.")
            meta["pdfuaid:part"] = "1"
        return RepairReport(name, 1, "Added pdfuaid:part = 1 to XMP metadata.")
    except Exception as ex:  # noqa: BLE001 - surfaced to the caller as a report
        return RepairReport(name, 0, f"Skipped - could not modify XMP metadata: {ex}")


def fix_mark_info(pdf: pikepdf.Pdf) -> RepairReport:
    """Ensures /MarkInfo /Marked is true — only when a struct tree exists."""
    name = "MarkInfo /Marked"
    catalog = pdf.Root
    mark_info = catalog.get(Name.MarkInfo)
    marked = mark_info.get(Name.Marked) if mark_info is not None else None

    if marked:
        return RepairReport(name, 0, "/MarkInfo /Marked is already true.")

    if catalog.get(Name.StructTreeRoot) is None:
        return RepairReport(
            name, 0,
            "Skipped - no /StructTreeRoot present; setting Marked=true would falsely claim this PDF is tagged."
        )

    if mark_info is None:
        mark_info = Dictionary()
        catalog[Name.MarkInfo] = mark_info
    mark_info[Name.Marked] = True
    return RepairReport(name, 1, "Set /MarkInfo /Marked = true.")


def fix_display_doc_title(pdf: pikepdf.Pdf) -> RepairReport:
    """Ensures /ViewerPreferences /DisplayDocTitle is true."""
    name = "ViewerPreferences /DisplayDocTitle"
    catalog = pdf.Root
    vp = catalog.get(Name.ViewerPreferences)
    display = vp.get(Name.DisplayDocTitle) if vp is not None else None

    if display:
        return RepairReport(name, 0, "/DisplayDocTitle is already true.")

    if vp is None:
        vp = Dictionary()
        catalog[Name.ViewerPreferences] = vp
    vp[Name.DisplayDocTitle] = True
    return RepairReport(name, 1, "Set /ViewerPreferences /DisplayDocTitle = true.")
