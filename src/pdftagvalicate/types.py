"""Shared data types for pdftagvalicate repairs and validation checks."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum


@dataclass(frozen=True)
class RepairReport:
    """Result of running a single repair against a PDF."""

    name: str
    fixed: int
    detail: str

    @property
    def any_fixed(self) -> bool:
        return self.fixed > 0

    def to_dict(self) -> dict:
        return asdict(self)


class Severity(Enum):
    """Result severity for a single PDF/UA validation check.

    Mirrors the ``Severity`` enum in ``Seismic.CTS.PdfUaChecker``
    (CheckTypes.cs).  Ordering: Pass < Info < Warning < Fail < Error.
    """
    Pass = "Pass"
    Info = "Info"
    Warning = "Warning"
    Fail = "Fail"
    Error = "Error"

    def _rank(self) -> int:
        return ["Pass", "Info", "Warning", "Fail", "Error"].index(self.value)

    def __lt__(self, other: "Severity") -> bool:
        return self._rank() < other._rank()

    def __le__(self, other: "Severity") -> bool:
        return self._rank() <= other._rank()

    def __ge__(self, other: "Severity") -> bool:
        return self._rank() >= other._rank()

    def __gt__(self, other: "Severity") -> bool:
        return self._rank() > other._rank()


@dataclass(frozen=True)
class CheckResult:
    """Result of a single read-only PDF/UA validation check."""

    id: str          # Matterhorn clause ID, e.g. "01-005"
    name: str        # Human-readable name
    severity: Severity
    detail: str      # Free-text explanation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class ValidateOptions:
    """Which checks to run and output modifiers."""

    strict: bool = False   # treat Warning as Fail for exit-code purposes

    @property
    def fail_threshold(self) -> Severity:
        return Severity.Warning if self.strict else Severity.Fail


@dataclass
class RepairOptions:
    """Which repairs to run."""

    metadata: bool = False       # pdfuaid:part, DisplayDocTitle, MarkInfo
    title: bool = False          # ensure a non-empty dc:title
    lang: bool = False           # ensure catalog /Lang
    lang_value: str | None = None  # explicit language code for the lang repair
    th_scope: bool = False       # add /Scope to TH elements
    link_nesting: bool = False   # wrap orphaned Link annotations in <Link> struct elem
    fix_tbody: bool = False      # dissolve fake Table->TBody->TR->TD wrappers
    dry_run: bool = False

    @classmethod
    def all(cls, dry_run: bool = False) -> "RepairOptions":
        return cls(
            metadata=True,
            title=True,
            lang=True,
            th_scope=True,
            link_nesting=True,
            fix_tbody=True,
            dry_run=dry_run,
        )

    @property
    def any_selected(self) -> bool:
        return (
            self.metadata
            or self.title
            or self.lang
            or self.th_scope
            or self.link_nesting
            or self.fix_tbody
        )


@dataclass
class CheckOptions:
    """Which checks to run (report-only, no file written).

    Each repair flag has a matching report-only check, so ``--check`` can
    audit a document the same way the repair pass would fix it.
    """

    metadata: bool = False      # pdfuaid:part, MarkInfo, DisplayDocTitle
    title: bool = False         # dc:title
    lang: bool = False          # catalog /Lang
    th_scope: bool = False      # TH cells missing /Scope
    link_nesting: bool = False  # orphaned Link annotations
    fix_tbody: bool = False     # fake Table->TBody->TR->TD wrappers
    alt_text: bool = False      # Figure elements missing /Alt
    fonts: bool = False         # unembedded / Type3 / missing ToUnicode
    suspects: bool = False      # /MarkInfo /Suspects flag

    @classmethod
    def all(cls) -> "CheckOptions":
        return cls(
            metadata=True,
            title=True,
            lang=True,
            th_scope=True,
            link_nesting=True,
            fix_tbody=True,
            alt_text=True,
            fonts=True,
            suspects=True,
        )

    @property
    def any_selected(self) -> bool:
        return (
            self.metadata
            or self.title
            or self.lang
            or self.th_scope
            or self.link_nesting
            or self.fix_tbody
            or self.alt_text
            or self.fonts
            or self.suspects
        )
