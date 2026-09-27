"""Ensure the document has a non-empty ``dc:title`` in its XMP metadata.

PAC requires a document title. We back-fill the XMP ``dc:title`` from the
classic ``/Info /Title`` entry when it is missing or empty. If neither is
present we report that the title cannot be auto-generated (fixed=0) rather
than inventing one.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Dictionary, Name

from .types import RepairReport


def fix(pdf: pikepdf.Pdf) -> RepairReport:
    name = "Document title (dc:title)"

    # Read the legacy /Info /Title BEFORE opening XMP metadata: pikepdf's
    # open_metadata() migrates and clears the /Info dictionary when no XMP
    # stream exists yet, so reading it afterwards would lose the value.
    legacy_title = None
    info = pdf.trailer.get(Name.Info)
    if isinstance(info, Dictionary):
        t = info.get(Name.Title)
        if t is not None:
            legacy_title = str(t).strip()

    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            existing = str(meta.get("dc:title", "")).strip()
    except Exception as ex:  # noqa: BLE001
        return RepairReport(name, 0, f"Skipped - could not read XMP metadata: {ex}")

    if existing:
        return RepairReport(name, 0, "dc:title is already present.")

    if not legacy_title:
        return RepairReport(
            name,
            0,
            "No document title found (neither dc:title nor /Info /Title); cannot auto-generate.",
        )

    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["dc:title"] = legacy_title
        return RepairReport(name, 1, f"Set dc:title = {legacy_title!r} from /Info /Title.")
    except Exception as ex:  # noqa: BLE001
        return RepairReport(name, 0, f"Skipped - could not modify XMP metadata: {ex}")
