"""Report the ``/MarkInfo /Suspects`` flag.

``/Suspects`` true means the PDF contains content that has not been fully
mapped to the tag tree, which PAC flags. We only report it; clearing it is
unsafe until the structure is known to be complete.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Name

from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Untagged content (/Suspects)"
    mark_info = pdf.Root.get(Name.MarkInfo)
    suspects = mark_info.get(Name.Suspects) if mark_info is not None else None

    if suspects:
        return CheckReport(name, 1, "/MarkInfo /Suspects is true - content is not fully mapped to the tag tree.")
    return CheckReport(name, 0, "/Suspects is not set - no untagged-content flag.")
