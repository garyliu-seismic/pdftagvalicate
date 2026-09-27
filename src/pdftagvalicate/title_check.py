"""Report-only dc:title check (no mutation).

PAC requires a document title in the metadata. This reports the problem
without writing, and notes whether /Info /Title is available as a
back-fill source.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Dictionary, Name

from .pdfutil import DC_NS, get_xmp_property
from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Document title (dc:title)"
    title = get_xmp_property(pdf, "title", DC_NS)
    if title:
        return CheckReport(name, 0, "dc:title is present.")

    fallback = None
    info = pdf.trailer.get(Name.Info)
    if isinstance(info, Dictionary):
        t = info.get(Name.Title)
        if t is not None and str(t).strip():
            fallback = str(t).strip()

    if fallback:
        return CheckReport(
            name, 1, f"Missing dc:title (can back-fill from /Info /Title = {fallback!r})."
        )
    return CheckReport(name, 1, "Missing document title (no dc:title or /Info /Title).")
