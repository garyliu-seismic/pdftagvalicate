"""Report font problems that PAC flags.

Three independent, report-only checks:

* unembedded fonts (no ``/FontFile`` in the font descriptor),
* Type 3 fonts (problematic for text extraction/selection),
* missing ``/ToUnicode`` CMap (breaks text-to-Unicode mapping).

None of these can be fixed reliably with pikepdf (they require re-embedding
font data), so we only report them.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Dictionary, Name

from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Fonts (embedding / Type3 / ToUnicode)"

    not_embedded: list[str] = []
    type3: list[str] = []
    no_cmap: list[str] = []

    for page in pdf.pages:
        resources = page.get(Name.Resources)
        if not isinstance(resources, Dictionary):
            continue
        fonts = resources.get(Name.Font)
        if not isinstance(fonts, Dictionary):
            continue

        for font_name, font in fonts.items():
            if not isinstance(font, Dictionary):
                continue

            if font.get(Name.Subtype) == Name.Type3:
                type3.append(str(font_name))
                continue

            desc = font.get(Name.FontDescriptor)
            embedded = isinstance(desc, Dictionary) and any(
                k in desc for k in (Name.FontFile, Name.FontFile2, Name.FontFile3)
            )
            if not embedded:
                not_embedded.append(str(font_name))

            if font.get(Name.ToUnicode) is None:
                no_cmap.append(str(font_name))

    issues = len(not_embedded) + len(type3) + len(no_cmap)
    if issues == 0:
        return CheckReport(name, 0, "All fonts are embedded, non-Type3, and have ToUnicode CMaps.")

    parts: list[str] = []
    if not_embedded:
        parts.append(f"{len(not_embedded)} unembedded font(s): {', '.join(not_embedded)}")
    if type3:
        parts.append(f"{len(type3)} Type3 font(s): {', '.join(type3)}")
    if no_cmap:
        parts.append(f"{len(no_cmap)} font(s) missing ToUnicode: {', '.join(no_cmap)}")
    return CheckReport(name, issues, "; ".join(parts))
