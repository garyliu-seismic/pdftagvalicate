"""Ensure the document catalog carries a ``/Lang`` entry.

PAC requires a document language. We back-fill ``/Lang`` from the XMP
``dc:language`` property when present; otherwise we report that the language
cannot be determined (fixed=0) rather than guessing. An explicit value can be
supplied by the caller via ``lang_value``.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Name

from .types import RepairReport


def fix(pdf: pikepdf.Pdf, lang_value: str | None = None) -> RepairReport:
    name = "Document language (/Lang)"
    catalog = pdf.Root
    lang = catalog.get(Name.Lang)
    if lang is not None and str(lang).strip():
        return RepairReport(name, 0, "/Lang is already set.")

    value = (lang_value or "").strip()
    if not value:
        value = _language_from_xmp(pdf)

    if not value:
        return RepairReport(
            name,
            0,
            "Cannot determine document language; pass an explicit code (--lang-value).",
        )

    catalog[Name.Lang] = value
    return RepairReport(name, 1, f"Set /Lang = {value!r}.")


def _language_from_xmp(pdf: pikepdf.Pdf) -> str | None:
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            raw = meta.get("dc:language")
    except Exception:  # noqa: BLE001
        return None

    if isinstance(raw, (list, tuple, set)):
        raw = next(iter(raw), None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
