"""pdftagvalicate - PDF/UA tag-tree validator and auto-repair tool.

Python port of Seismic.CTS.PdfUaRepairer (originally iText-based), rebuilt on
pikepdf so it can run standalone without a .NET runtime - e.g. as a CLI tool
invoked by Claude Code.
"""

from .types import CheckOptions, CheckReport, RepairOptions, RepairReport
from .repairs import run_repairs
from .checks import run_checks

__all__ = [
    "CheckOptions",
    "CheckReport",
    "RepairOptions",
    "RepairReport",
    "run_repairs",
    "run_checks",
]

__version__ = "0.1.0"
