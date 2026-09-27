"""Check that content-bearing <Figure> elements carry non-empty ``/Alt`` text.

PAC flags figures that lack an alternative description. This is a report-only
check: a meaningful alt text cannot be synthesized automatically, so we count
the offenders instead of guessing a placeholder.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Dictionary, Name

from .pdfutil import get_kids, is_tagged, role_of, visit_key
from .types import CheckReport

_ALT_REQUIRED_ROLES = {"Figure"}


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Alternative text (/Alt)"

    if not is_tagged(pdf):
        return CheckReport(name, 0, "Document is not tagged - skipped.")

    root = pdf.Root.get(Name.StructTreeRoot)
    missing: list[Dictionary] = []
    if root is not None:
        _walk(root, missing, set())

    if not missing:
        return CheckReport(name, 0, "All <Figure> elements have non-empty /Alt.")
    return CheckReport(name, len(missing), f"{len(missing)} <Figure> element(s) missing /Alt.")


def _walk(node, missing: list, visited: set) -> None:
    if not isinstance(node, Dictionary):
        return

    key = visit_key(node)
    if key in visited:
        return
    visited.add(key)

    if role_of(node) in _ALT_REQUIRED_ROLES:
        alt = node.get(Name.Alt)
        if alt is None or str(alt).strip() in ("", "()"):
            missing.append(node)

    for kid in get_kids(node):
        _walk(kid, missing, visited)
