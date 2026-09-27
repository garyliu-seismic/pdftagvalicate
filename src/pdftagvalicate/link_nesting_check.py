"""Report-only Link annotation nesting check (no mutation)."""

from __future__ import annotations

import pikepdf

from . import link_nesting_repair
from .types import CheckReport


def check(pdf: pikepdf.Pdf) -> CheckReport:
    name = "Link annotation nesting"
    orphans = link_nesting_repair.collect_orphaned_links(pdf)
    if not orphans:
        return CheckReport(name, 0, "All Link annotations are properly nested.")
    return CheckReport(name, len(orphans), f"{len(orphans)} orphaned Link annotation(s).")
