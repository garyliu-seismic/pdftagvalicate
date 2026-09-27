"""Report-only /Lang check (no mutation).

PAC requires the document language to be declared in the catalog. This
reports a missing /Lang and notes whether XMP dc:language is available as a
back-fill source.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Name

from .pdfutil import DC_NS, get_xmp_property
from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Document language (/Lang)"
    lang = pdf.Root.get(Name.Lang)
    if lang is not None and str(lang).strip():
        return CheckReport(name, 0, "/Lang is set.")

    source = get_xmp_property(pdf, "language", DC_NS)
    if source:
        return CheckReport(
            name, 1, f"Missing /Lang (can back-fill from XMP dc:language = {source!r})."
        )
    return CheckReport(name, 1, "Missing /Lang (no dc:language in XMP to back-fill from).")
