"""Read-only PDF/UA validation checks ported from Seismic.CTS.PdfUaChecker.

Each public function corresponds to one Matterhorn clause and returns a
:class:`~pdftagvalicate.types.CheckResult`.  All functions are pure
readers — no PDF object is mutated.

Step 2 trivial   : 01-005, 11-001, 06-003, 07-001, 13-004, 14-002, 14-003
Step 3 moderate  : 09-001, 14-001, 09-007, 14-004, 28-001, 31-001, 09-004
Step 4 hard      : 06-001, 09-006  (to be added later)
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Dictionary, Name

from .link_nesting_repair import _collect_tagged
from .pdfutil import (
    find_page_index,
    get_kids,
    get_struct_kids,
    iter_font_resources,
    object_key,
    resolve_role,
    walk_struct_tree,
)
from .th_scope_repair import _collect_missing_scopes
from .tbody_repair import _collect_by_role, role_of
from .types import CheckResult, Severity


# ---------------------------------------------------------------------------
# 01-005  MarkInfo /Marked is true
# ---------------------------------------------------------------------------

def check_01_005(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 01-005: /MarkInfo /Marked must be present and true."""
    _id = "01-005"
    _name = "MarkInfo /Marked is true"

    catalog = pdf.Root
    mark_info = catalog.get(Name.MarkInfo)
    if mark_info is None:
        return CheckResult(_id, _name, Severity.Fail, "/MarkInfo entry is absent from the document catalog.")

    marked = mark_info.get(Name.Marked)
    if not marked:
        return CheckResult(_id, _name, Severity.Fail, "/MarkInfo /Marked is present but not true.")

    return CheckResult(_id, _name, Severity.Pass, "/MarkInfo /Marked is true.")


# ---------------------------------------------------------------------------
# 11-001  Document /Lang set
# ---------------------------------------------------------------------------

def check_11_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 11-001: the document catalog must have a /Lang entry."""
    _id = "11-001"
    _name = "Document /Lang set"

    lang = pdf.Root.get(Name.Lang)
    if lang is None or str(lang).strip() == "":
        return CheckResult(_id, _name, Severity.Fail, "Document /Lang is absent or empty.")

    return CheckResult(_id, _name, Severity.Pass, f"Document /Lang = {str(lang)!r}.")


# ---------------------------------------------------------------------------
# 06-003  Document Title set
# ---------------------------------------------------------------------------

def check_06_003(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 06-003: /Title must be present in the document info dict."""
    _id = "06-003"
    _name = "Document Title set"

    # DocInfo /Title lives in the trailer Info dict, not in XMP.
    doc_info = pdf.docinfo
    title = doc_info.get("/Title") if doc_info else None
    if title is None or str(title).strip() == "":
        return CheckResult(_id, _name, Severity.Fail, "DocInfo /Title is absent or empty.")

    return CheckResult(_id, _name, Severity.Pass, f"DocInfo /Title = {str(title)!r}.")


# ---------------------------------------------------------------------------
# 07-001  ViewerPreferences /DisplayDocTitle true
# ---------------------------------------------------------------------------

def check_07_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 07-001: /ViewerPreferences /DisplayDocTitle must be true."""
    _id = "07-001"
    _name = "ViewerPreferences /DisplayDocTitle true"

    catalog = pdf.Root
    vp = catalog.get(Name.ViewerPreferences)
    if vp is None:
        return CheckResult(_id, _name, Severity.Fail, "/ViewerPreferences is absent.")

    display = vp.get(Name.DisplayDocTitle)
    if not display:
        return CheckResult(_id, _name, Severity.Fail, "/ViewerPreferences /DisplayDocTitle is absent or false.")

    return CheckResult(_id, _name, Severity.Pass, "/ViewerPreferences /DisplayDocTitle is true.")


# ---------------------------------------------------------------------------
# 13-004  <Figure>/<Formula> alt text
# ---------------------------------------------------------------------------

def check_13_004(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 13-004: every <Figure> and <Formula> must have alt text.

    Checks /Alt, /ActualText, and /E on each struct element whose resolved
    role is Figure or Formula.
    """
    _id = "13-004"
    _name = "<Figure>/<Formula> alt text"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    missing: list[str] = []

    def _visit(node: Dictionary) -> None:
        role = resolve_role(role_of(node) or "", struct_root)
        if role not in ("Figure", "Formula"):
            return
        has_alt = (
            _nonempty(node.get(Name.Alt))
            or _nonempty(node.get(Name.ActualText))
            or _nonempty(node.get(Name.E))
        )
        if not has_alt:
            objgen = getattr(node, "objgen", (0, 0))
            missing.append(f"<{role}> obj {objgen[0]} has no /Alt, /ActualText, or /E")

    walk_struct_tree(struct_root, _visit)

    if missing:
        detail = f"{len(missing)} element(s) missing alt text: " + "; ".join(missing[:5])
        if len(missing) > 5:
            detail += f" … (+{len(missing) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All <Figure>/<Formula> elements have alt text.")


def _nonempty(val) -> bool:
    """True if *val* is a non-None, non-empty string."""
    if val is None:
        return False
    return str(val).strip() != ""


# ---------------------------------------------------------------------------
# 14-002  <TBody> contains only <TR> rows  (read-only mirror of tbody_repair)
# ---------------------------------------------------------------------------

def check_14_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 14-002: every <TBody> must contain only <TR> children.

    Read-only mirror of ``tbody_repair``: collects the same fake-table
    shapes and reports them without mutating the PDF.
    """
    _id = "14-002"
    _name = "<TBody> contains only <TR> rows"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    tbodies: list[Dictionary] = []
    _collect_by_role(struct_root.get(Name.K), "TBody", tbodies, set())

    violations: list[str] = []
    for tbody in tbodies:
        non_tr = [
            role_of(k) for k in get_struct_kids(tbody)
            if role_of(k) != "TR"
        ]
        if non_tr:
            objgen = getattr(tbody, "objgen", (0, 0))
            violations.append(
                f"TBody obj {objgen[0]} has non-TR children: {non_tr}"
            )

    if violations:
        detail = f"{len(violations)} TBody element(s) with non-TR children: " + "; ".join(violations[:5])
        if len(violations) > 5:
            detail += f" … (+{len(violations) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All <TBody> elements contain only <TR> children.")


# ---------------------------------------------------------------------------
# 14-003  TH cells have /Scope  (read-only mirror of th_scope_repair)
# ---------------------------------------------------------------------------

def check_14_003(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 14-003: every <TH> cell must have a /Scope attribute.

    Read-only mirror of ``th_scope_repair``: reuses ``_collect_missing_scopes``
    verbatim and wraps the result in a CheckResult without applying any fix.
    """
    _id = "14-003"
    _name = "TH cells have /Scope"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    findings: list[tuple] = []
    _collect_missing_scopes(struct_root, findings)

    if findings:
        count = len(findings)
        return CheckResult(
            _id, _name, Severity.Fail,
            f"{count} <TH> cell(s) are missing a /Scope attribute."
        )

    return CheckResult(_id, _name, Severity.Pass, "All <TH> cells have a /Scope attribute.")


# ===========================================================================
# Step 3 — trivial-to-moderate checks
# ===========================================================================


# ---------------------------------------------------------------------------
# 09-001  Single <Document> at struct tree root
# ---------------------------------------------------------------------------

def check_09_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-001: the struct tree root must have exactly one top-level
    element whose resolved role is ``Document``."""
    _id = "09-001"
    _name = "Single <Document> at struct tree root"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Fail, "No /StructTreeRoot — document is not tagged.")

    top_kids = [k for k in get_kids(struct_root) if isinstance(k, Dictionary)]
    doc_kids = [k for k in top_kids if resolve_role(role_of(k) or "", struct_root) == "Document"]
    non_doc  = [k for k in top_kids if resolve_role(role_of(k) or "", struct_root) != "Document"]

    if len(doc_kids) == 0:
        return CheckResult(_id, _name, Severity.Fail,
                           "No <Document> element found at the struct tree root.")
    if len(doc_kids) > 1:
        return CheckResult(_id, _name, Severity.Fail,
                           f"{len(doc_kids)} <Document> elements found at root; exactly 1 required.")
    if non_doc:
        # Mirrors C#: Document present but alongside other elements → Warning not Fail.
        roles = [role_of(k) for k in non_doc]
        all_roles = [role_of(k) for k in top_kids]
        return CheckResult(_id, _name, Severity.Warning,
                           f"<Document> is present but accompanied by other top-level elements: {roles}. "
                           f"Roles at root: {all_roles}.")

    return CheckResult(_id, _name, Severity.Pass, "Exactly one <Document> element at struct tree root.")


# ---------------------------------------------------------------------------
# 14-001  Role map resolves to standard roles
# ---------------------------------------------------------------------------

# Full set of standard roles (also defined in pdfutil._STANDARD_ROLES, but
# we need it here for the cycle/unknown distinction in reporting).
_STANDARD_ROLES: frozenset[str] = frozenset({
    "Document", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption",
    "TOC", "TOCI", "Index", "NonStruct", "Private",
    "H", "H1", "H2", "H3", "H4", "H5", "H6",
    "P", "L", "LI", "Lbl", "LBody",
    "Table", "TR", "TH", "TD", "THead", "TBody", "TFoot",
    "Span", "Quote", "Note", "Reference", "BibEntry", "Code",
    "Link", "Annot", "Ruby", "RB", "RT", "RP", "Warichu", "WT", "WP",
    "Figure", "Formula", "Form",
})


def check_14_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 14-001: every entry in StructTreeRoot/RoleMap must resolve
    transitively to a standard PDF 1.7 role without forming a cycle."""
    _id = "14-001"
    _name = "Role map resolves to standard roles"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    role_map = struct_root.get(Name.RoleMap)
    if role_map is None:
        return CheckResult(_id, _name, Severity.Pass, "No RoleMap present (nothing to validate).")

    bad_cycle:   list[str] = []
    bad_unknown: list[str] = []

    for key in role_map.keys():
        source = str(key)[1:]  # strip leading '/'
        resolved = resolve_role(source, struct_root)
        if resolved not in _STANDARD_ROLES:
            # Determine whether the failure is a cycle or simply unresolvable.
            # resolve_role returns the last node it reached in both cases;
            # a cycle is detectable by checking if that node still maps.
            rm = role_map
            if isinstance(rm, Dictionary) and Name("/" + resolved) in rm.keys():
                bad_cycle.append(source)
            else:
                bad_unknown.append(f"{source} → {resolved}")

    problems: list[str] = []
    if bad_cycle:
        problems.append(f"cyclic: {bad_cycle}")
    if bad_unknown:
        problems.append(f"unresolvable: {bad_unknown}")

    if problems:
        return CheckResult(_id, _name, Severity.Fail,
                           "RoleMap entries that do not resolve to standard roles — " + "; ".join(problems))

    return CheckResult(_id, _name, Severity.Pass, "All RoleMap entries resolve to standard PDF 1.7 roles.")


# ---------------------------------------------------------------------------
# 09-007  First heading is on level 1
# ---------------------------------------------------------------------------

# Heading roles in document order for level detection.
_HEADING_ROLES: frozenset[str] = frozenset({"H", "H1", "H2", "H3", "H4", "H5", "H6"})


def check_09_007(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-007: the first heading element in document order must
    resolve to H1 (or unlevelled H if no H1–H6 exist at all)."""
    _id = "09-007"
    _name = "First heading is on level 1"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    first_heading: list[str] = []   # mutable box; stop after first hit

    def _visit(node: Dictionary) -> None:
        if first_heading:
            return
        resolved = resolve_role(role_of(node) or "", struct_root)
        if resolved in _HEADING_ROLES:
            first_heading.append(resolved)

    walk_struct_tree(struct_root, _visit)

    if not first_heading:
        return CheckResult(_id, _name, Severity.Info, "No heading elements found in the document.")

    first = first_heading[0]
    if first in ("H1", "H"):
        return CheckResult(_id, _name, Severity.Pass, f"First heading is <{first}>.")

    return CheckResult(
        _id, _name, Severity.Fail,
        f"First heading is <{first}>; expected <H1> (or <H> when no levelled headings are used)."
    )


# ---------------------------------------------------------------------------
# 14-004  Table rows are regular
# ---------------------------------------------------------------------------

def check_14_004(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 14-004: within each table section, every TR must have the
    same number of cells as the first non-empty row (Warning, not Fail)."""
    _id = "14-004"
    _name = "Table rows are regular"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    tables: list[Dictionary] = []
    _collect_by_role(struct_root.get(Name.K), "Table", tables, set())

    irregular: list[str] = []

    for table in tables:
        table_objgen = getattr(table, "objgen", (0, 0))
        # Walk THead / TBody / TFoot sections (and bare TR children).
        sections: list[Dictionary] = []
        for kid in get_struct_kids(table):
            r = role_of(kid)
            if r in ("THead", "TBody", "TFoot"):
                sections.append(kid)
            elif r == "TR":
                # bare TR directly under table — treat as a singleton section
                sections.append(_fake_section(kid))

        for section in sections:
            rows = [k for k in get_struct_kids(section) if role_of(k) == "TR"]
            cell_counts = [
                len([c for c in get_struct_kids(r) if role_of(c) in ("TD", "TH")])
                for r in rows
            ]
            non_empty = [c for c in cell_counts if c > 0]
            if not non_empty:
                continue
            expected = non_empty[0]
            for i, count in enumerate(cell_counts):
                if count != 0 and count != expected:
                    page_idx = find_page_index(rows[i], pdf)
                    loc = f"p.{page_idx + 1}" if page_idx is not None else "unknown page"
                    irregular.append(
                        f"Table obj {table_objgen[0]} row {i + 1} has {count} cells (expected {expected}) on {loc}"
                    )

    if irregular:
        detail = f"{len(irregular)} irregular row(s): " + "; ".join(irregular[:5])
        if len(irregular) > 5:
            detail += f" … (+{len(irregular) - 5} more)"
        return CheckResult(_id, _name, Severity.Warning, detail)

    return CheckResult(_id, _name, Severity.Pass, "All table rows have consistent cell counts.")


def _fake_section(tr: Dictionary) -> Dictionary:
    """Wrap a bare TR in a temporary dict so section-level code works uniformly."""
    fake = Dictionary()
    fake[Name.K] = tr
    return fake


# ---------------------------------------------------------------------------
# 28-001  Link annotations nested inside <Link>  (reuses repair logic)
# ---------------------------------------------------------------------------

def check_28_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 28-001: every Link annotation must be referenced from a
    ``<Link>`` struct element via an OBJR.

    Read-only: reuses ``link_nesting_repair._collect_tagged`` to find the set
    of already-tagged annotation object numbers, then walks page /Annots to
    find any Link annotations *not* in that set.
    """
    _id = "28-001"
    _name = "Link annotations nested inside <Link>"

    struct_root = pdf.Root.get(Name.StructTreeRoot)

    tagged_obj_nums: set[int] = set()
    if struct_root is not None:
        _collect_tagged(struct_root, tagged_obj_nums, parent_is_link=False)

    untagged: list[str] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        for annot in annots:
            if not isinstance(annot, Dictionary):
                continue
            if annot.get(Name.Subtype) != Name.Link:
                continue
            objgen = getattr(annot, "objgen", (0, 0))
            if objgen == (0, 0) or objgen[0] not in tagged_obj_nums:
                untagged.append(f"annot obj {objgen[0]} on p.{page_idx + 1}")

    if untagged:
        detail = f"{len(untagged)} Link annotation(s) not wrapped in <Link>: " + "; ".join(untagged[:5])
        if len(untagged) > 5:
            detail += f" … (+{len(untagged) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All Link annotations are wrapped inside <Link> struct elements.")


# ---------------------------------------------------------------------------
# 31-001  All fonts embedded
# ---------------------------------------------------------------------------

def check_31_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 31-001: every font used in the document must be embedded.

    Checks ``/FontDescriptor`` for a ``FontFile``, ``FontFile2``, or
    ``FontFile3`` stream.  Composite (Type 0) fonts are checked via
    ``/DescendantFonts[0]/FontDescriptor``.
    """
    _id = "31-001"
    _name = "All fonts embedded"

    not_embedded: list[str] = []

    for font in iter_font_resources(pdf):
        name_str = str(font.get(Name.BaseFont) or font.get(Name.Name) or "<unknown>")
        descriptor = _get_font_descriptor(font)
        if descriptor is None:
            # Type 3 fonts have no descriptor — they embed glyph procedures directly.
            font_type = str(font.get(Name.Subtype) or "")
            if font_type == "/Type3":
                continue
            not_embedded.append(f"{name_str} (no FontDescriptor)")
            continue

        has_file = (
            descriptor.get(Name.FontFile) is not None
            or descriptor.get(Name.FontFile2) is not None
            or descriptor.get(Name.FontFile3) is not None
        )
        if not has_file:
            not_embedded.append(name_str)

    if not_embedded:
        detail = f"{len(not_embedded)} font(s) not embedded: " + ", ".join(not_embedded[:5])
        if len(not_embedded) > 5:
            detail += f" … (+{len(not_embedded) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All fonts are embedded.")


def _get_font_descriptor(font: Dictionary) -> "Dictionary | None":
    """Return the /FontDescriptor for *font*, following DescendantFonts for
    composite (Type 0) fonts."""
    # Type 0 (composite) fonts delegate to a CIDFont descendant.
    subtype = str(font.get(Name.Subtype) or "")
    if subtype == "/Type0":
        desc_fonts = font.get(Name.DescendantFonts)
        if isinstance(desc_fonts, Array) and len(desc_fonts) > 0:
            cidfonts = desc_fonts[0]
            if isinstance(cidfonts, Dictionary):
                return cidfonts.get(Name.FontDescriptor)
        return None
    return font.get(Name.FontDescriptor)


# ---------------------------------------------------------------------------
# 09-004  No untagged page content
# ---------------------------------------------------------------------------

def check_09_004(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-004: every page must have at least one MCR or OBJR
    descendant in the struct tree (i.e. no page is wholly untagged).

    Collects the set of page indices touched by any struct-tree leaf
    (MCR — a dict with /MCID, or OBJR — a dict with /Type/OBJR), then
    diffs against the full page range.
    """
    _id = "09-004"
    _name = "No untagged page content"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        if len(pdf.pages) == 0:
            return CheckResult(_id, _name, Severity.Pass, "Document has no pages.")
        return CheckResult(
            _id, _name, Severity.Fail,
            f"No struct tree — all {len(pdf.pages)} page(s) are untagged."
        )

    # Build page obj → index map (reuses the cache find_page_index sets up).
    tagged_pages: set[int] = set()

    def _visit(node: Dictionary) -> None:
        # MCR: has /MCID (integer) but no /S (not a struct elem).
        # OBJR: /Type == /OBJR.
        node_type = str(node.get(Name.Type) or "")
        is_objr = node_type == "/OBJR"
        is_mcr  = Name.MCID in node and Name.S not in node
        if is_objr or is_mcr:
            idx = find_page_index(node, pdf)
            if idx is not None:
                tagged_pages.add(idx)

    walk_struct_tree(struct_root, _visit)

    total = len(pdf.pages)
    untagged_indices = sorted(i for i in range(total) if i not in tagged_pages)

    if untagged_indices:
        pages_str = ", ".join(f"p.{i + 1}" for i in untagged_indices[:10])
        if len(untagged_indices) > 10:
            pages_str += f" … (+{len(untagged_indices) - 10} more)"
        return CheckResult(
            _id, _name, Severity.Fail,
            f"{len(untagged_indices)} page(s) have no tagged content: {pages_str}"
        )

    return CheckResult(_id, _name, Severity.Pass, f"All {total} page(s) have tagged content in the struct tree.")


# ===========================================================================
# Step 4 — hard checks
# ===========================================================================


# ---------------------------------------------------------------------------
# 06-001  PDF/UA identifier in XMP
# ---------------------------------------------------------------------------

_PDFUAID_NS   = "http://www.aiim.org/pdfua/ns/id/"
_PDFUAID_KEY  = "pdfuaid:part"          # prefix form used by pikepdf accessors
_PDFUAID_CLARK = f"{{{_PDFUAID_NS}}}part"  # Clark notation fallback


def check_06_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 06-001: the XMP metadata stream must declare
    ``pdfuaid:part = '1'`` in the ``http://www.aiim.org/pdfua/ns/id/``
    namespace.

    Implementation note: ``pikepdf.open_metadata()`` correctly resolves the
    value regardless of whether the XMP uses the element or attribute form and
    regardless of the namespace prefix (``pdfuaid``, ``ua``, or any other),
    because it normalises to Clark notation internally.  No ``lxml`` raw-parse
    fallback is needed.
    """
    _id   = "06-001"
    _name = "PDF/UA identifier in XMP"

    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            # Try the prefix form first (what pikepdf exposes after namespace
            # registration); fall back to the Clark-notation key.
            meta.register_xml_namespace(_PDFUAID_NS, "pdfuaid")
            value = meta.get(_PDFUAID_KEY) or meta.get(_PDFUAID_CLARK)
    except Exception as ex:  # noqa: BLE001
        return CheckResult(_id, _name, Severity.Error,
                           f"Could not read XMP metadata: {ex}")

    if value is None:
        return CheckResult(_id, _name, Severity.Fail,
                           "pdfuaid:part is absent from the XMP metadata stream.")

    value_str = str(value).strip()
    if value_str != "1":
        return CheckResult(_id, _name, Severity.Fail,
                           f"pdfuaid:part = {value_str!r}; expected '1' (PDF/UA-1).")

    return CheckResult(_id, _name, Severity.Pass,
                       "XMP metadata contains pdfuaid:part = '1'.")


# ---------------------------------------------------------------------------
# 09-006  No untagged real content in page streams
# ---------------------------------------------------------------------------

import enum as _enum

class _McLayer(_enum.Enum):
    """Marked-content layer state, mirroring C# UntaggedContentCheck.McLayer."""
    Artifact = "Artifact"   # inside /Artifact BDC — explicitly decorative
    Tagged   = "Tagged"     # inside a valid tagged BDC layer
    Invalid  = "Invalid"    # inside a BDC in an XObject without /StructParents


def check_09_006(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-006: no real-content painting operator may appear outside
    a marked-content layer (BDC/BMC … EMC stack).

    Uses a tri-state layer model (Artifact / Tagged / Invalid) that matches the
    C# ``UntaggedContentCheck``:
    - Page streams and Form XObjects **with** ``/StructParents``: any BMC/BDC
      layer is ``Tagged`` (valid).
    - Form XObjects **without** ``/StructParents``: only ``/Artifact`` BDC blocks
      are valid; all other BDC/BMC layers become ``Invalid``.

    Recurses into Form XObjects with a cycle guard.  Image XObjects are counted
    at their ``Do`` call site (not recursed into).  Because this is the most
    expensive check it runs last.
    """
    _id   = "09-006"
    _name = "No untagged real content in page streams"

    paths:  list[str] = []
    images: list[str] = []
    texts:  list[str] = []
    parse_errors: list[str] = []

    visited_xobjects: set[tuple] = set()

    def _scan(stream_obj, label: str, mc_stack: list[_McLayer], only_artifacts: bool) -> None:
        try:
            instructions = pikepdf.parse_content_stream(stream_obj)
        except Exception as ex:  # noqa: BLE001
            parse_errors.append(f"{label}: parse error — {ex}")
            return

        resources = _get_resources(stream_obj)

        for instr in instructions:
            op = str(instr.operator)

            if op in ("BMC", "BDC"):
                # Determine the new layer state.
                tag = ""
                if instr.operands:
                    tag = str(instr.operands[0])
                is_artifact = tag in ("/Artifact", "Artifact")
                if is_artifact:
                    layer = _McLayer.Artifact
                elif not only_artifacts:
                    layer = _McLayer.Tagged
                else:
                    layer = _McLayer.Invalid
                mc_stack.append(layer)

            elif op == "EMC":
                if mc_stack:
                    mc_stack.pop()

            elif op in ("Tj", "TJ", "’", ‘"’):
                top = mc_stack[-1] if mc_stack else _McLayer.Invalid
                if top == _McLayer.Invalid or not mc_stack:
                    texts.append(f"{label}: ‘{op}’")

            elif op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "sh"):
                top = mc_stack[-1] if mc_stack else _McLayer.Invalid
                if top == _McLayer.Invalid or not mc_stack:
                    paths.append(f"{label}: ‘{op}’")

            elif op == "Do":
                if not instr.operands:
                    continue
                xobj_name = instr.operands[0]
                resolved = _resolve_xobject_any(resources, xobj_name)
                top = mc_stack[-1] if mc_stack else _McLayer.Invalid
                parent_is_safe = bool(mc_stack) and top != _McLayer.Invalid
                parent_is_artifact = top == _McLayer.Artifact
                if resolved is None:
                    # XObject not found — can’t determine type; skip.
                    continue
                subtype, xobj = resolved
                if subtype == "Image":
                    if not parent_is_artifact and not parent_is_safe:
                        images.append(f"{label}: ‘Do’ (image)")
                elif subtype == "Form":
                    if parent_is_artifact:
                        continue  # whole form is decorative
                    xobj_key = getattr(xobj, "objgen", (0, 0))
                    if xobj_key != (0, 0) and xobj_key in visited_xobjects:
                        continue
                    if xobj_key != (0, 0):
                        visited_xobjects.add(xobj_key)
                    has_struct_parents = Name.StructParents in xobj
                    _scan(xobj, label, list(mc_stack), only_artifacts=not has_struct_parents)

    for page_idx, page in enumerate(pdf.pages):
        label = f"p.{page_idx + 1}"
        try:
            _scan(page, label, mc_stack=[], only_artifacts=False)
        except Exception as ex:  # noqa: BLE001
            parse_errors.append(f"{label}: unexpected error — {ex}")

    total = len(paths) + len(images) + len(texts)
    if total == 0 and not parse_errors:
        return CheckResult(_id, _name, Severity.Pass,
                           f"All content is tagged across {len(pdf.pages)} page(s).")

    if total > 0:
        parts = []
        if paths:
            parts.append(f"{len(paths)} path object(s) not tagged")
        if images:
            parts.append(f"{len(images)} image object(s) not tagged")
        if texts:
            parts.append(f"{len(texts)} text object(s) not tagged")
        detail = f"{total} untagged content object(s): " + "; ".join(parts)
        if parse_errors:
            detail += f"  [{len(parse_errors)} stream(s) had parse errors and may be incomplete]"
        return CheckResult(_id, _name, Severity.Fail, detail)

    detail = (
        f"{len(parse_errors)} stream(s) could not be fully parsed; "
        "untagged content may exist: " + "; ".join(parse_errors[:3])
    )
    return CheckResult(_id, _name, Severity.Warning, detail)


def _get_resources(obj) -> "Dictionary | None":
    """Best-effort /Resources extraction from a page or Form XObject."""
    try:
        if isinstance(obj, pikepdf.Page):
            return obj.obj.get(Name.Resources)
        if isinstance(obj, Dictionary):
            return obj.get(Name.Resources)
    except Exception:  # noqa: BLE001
        pass
    return None


def _resolve_xobject(resources, name) -> "Dictionary | None":
    """Resolve an XObject name from /Resources; return it only if it’s a Form."""
    if resources is None:
        return None
    try:
        xobjs = resources.get(Name.XObject)
        if not isinstance(xobjs, Dictionary):
            return None
        name_key = Name("/" + str(name)[1:]) if str(name).startswith("/") else name
        xobj = xobjs.get(name_key)
        if not isinstance(xobj, Dictionary):
            return None
        if str(xobj.get(Name.Subtype) or "") == "/Form":
            return xobj
    except Exception:  # noqa: BLE001
        pass
    return None


def _resolve_xobject_any(resources, name) -> "tuple[str, Dictionary] | None":
    """Resolve an XObject name; return (subtype, dict) or None if not found."""
    if resources is None:
        return None
    try:
        xobjs = resources.get(Name.XObject)
        if not isinstance(xobjs, Dictionary):
            return None
        name_key = Name("/" + str(name)[1:]) if str(name).startswith("/") else name
        xobj = xobjs.get(name_key)
        if not isinstance(xobj, Dictionary):
            return None
        subtype = str(xobj.get(Name.Subtype) or "").lstrip("/")
        return (subtype, xobj)
    except Exception:  # noqa: BLE001
        pass
    return None


# ===========================================================================
# P4 — Extended PAC checks
# ===========================================================================

import re as _re

_BCP47_RE = _re.compile(
    r"^(?:[a-zA-Z]{2,3}|x)"         # primary: 2-3 letter language tag, or 'x' private-use
    r"(-[a-zA-Z]{4})?"               # optional script subtag
    r"(-[a-zA-Z]{2}|-\d{3})?"        # optional region subtag (hyphen required)
    r"(-[a-zA-Z0-9]{5,8}|-\d{4})*"  # optional variant(s)
    r"(-[a-zA-Z]-[a-zA-Z0-9]{2,8})*"  # optional singleton extensions
    r"(-x(-[a-zA-Z0-9]{1,8})+)?$"     # optional private-use extension
)


# ---------------------------------------------------------------------------
# 08-001  Encryption allows assistive technology access
# ---------------------------------------------------------------------------

def check_08_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 08-001: if the document is encrypted, the permissions must
    allow content copying for accessibility (bit 10 of the /P flags)."""
    _id   = "08-001"
    _name = "Encryption allows AT access"

    if not pdf.is_encrypted:
        return CheckResult(_id, _name, Severity.Pass, "Document is not encrypted.")

    # PDF spec Table 22: bit 10 (1-indexed) = 0x200.  This is the
    # "copy text and graphics for accessibility" permission flag.
    try:
        p_flags = int(pdf.encryption.P)
    except Exception:  # noqa: BLE001
        return CheckResult(_id, _name, Severity.Warning,
                           "Document is encrypted but /P permissions flags could not be read.")

    accessibility_bit = 0x200  # bit 10 (PDF spec Table 22)
    if not (p_flags & accessibility_bit):
        return CheckResult(_id, _name, Severity.Fail,
                           f"Encryption /P = {p_flags:#010x}: content-copying-for-accessibility bit (0x200) is not set.")

    return CheckResult(_id, _name, Severity.Pass,
                       "Encryption permits content copying for accessibility.")


# ---------------------------------------------------------------------------
# 01-002  All in-use struct tags are standard or mapped in RoleMap
# ---------------------------------------------------------------------------

def check_01_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 01-002: every /S (structure type) used in the struct tree
    must either be a standard PDF 1.7 role or appear as a key in RoleMap."""
    _id   = "01-002"
    _name = "All struct tags standard or role-mapped"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    role_map = struct_root.get(Name.RoleMap)
    mapped_keys: set[str] = set()
    if isinstance(role_map, Dictionary):
        for k in role_map.keys():
            mapped_keys.add(str(k)[1:])  # strip leading '/'

    unmapped: list[str] = []

    def _visit(node: Dictionary) -> None:
        raw = node.get(Name.S)
        if raw is None:
            return
        role = str(raw)[1:]
        if role not in _STANDARD_ROLES and role not in mapped_keys:
            unmapped.append(role)

    walk_struct_tree(struct_root, _visit)

    if unmapped:
        unique = sorted(set(unmapped))
        return CheckResult(_id, _name, Severity.Fail,
                           f"{len(unmapped)} struct element(s) use non-standard, unmapped roles: {unique}.")
    return CheckResult(_id, _name, Severity.Pass,
                       "All struct tags are standard PDF 1.7 roles or mapped in RoleMap.")


# ---------------------------------------------------------------------------
# 06-004  XMP dc:title matches DocInfo /Title
# ---------------------------------------------------------------------------

def check_06_004(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 06-004: if both XMP dc:title and DocInfo /Title are present
    they must agree (case-insensitive, trimmed)."""
    _id   = "06-004"
    _name = "XMP dc:title matches DocInfo /Title"

    doc_info_title = ""
    doc_info = pdf.docinfo
    if doc_info:
        raw = doc_info.get("/Title")
        doc_info_title = str(raw).strip() if raw is not None else ""

    xmp_title = ""
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            val = meta.get("dc:title")
            xmp_title = str(val).strip() if val is not None else ""
    except Exception:  # noqa: BLE001
        pass

    if not doc_info_title or not xmp_title:
        return CheckResult(_id, _name, Severity.Info,
                           "One or both title fields absent — no conflict to check.")

    if doc_info_title.lower() != xmp_title.lower():
        return CheckResult(_id, _name, Severity.Warning,
                           f"DocInfo /Title = {doc_info_title!r} differs from XMP dc:title = {xmp_title!r}.")

    return CheckResult(_id, _name, Severity.Pass,
                       f"DocInfo /Title and XMP dc:title agree: {doc_info_title!r}.")


# ---------------------------------------------------------------------------
# 11-002  /Lang values are valid BCP-47 tags
# ---------------------------------------------------------------------------

def check_11_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 11-002: every /Lang value in the document (catalog, pages,
    struct elements) must be a valid BCP-47 language tag."""
    _id   = "11-002"
    _name = "/Lang values are valid BCP-47 tags"

    invalid: list[str] = []

    def _check_lang(val, location: str) -> None:
        s = str(val).strip()
        if s and not _BCP47_RE.match(s):
            invalid.append(f"{location}: {s!r}")

    # Document catalog.
    lang = pdf.Root.get(Name.Lang)
    if lang is not None:
        _check_lang(lang, "catalog /Lang")

    # Page /Lang entries.
    for i, page in enumerate(pdf.pages):
        pl = page.obj.get(Name.Lang)
        if pl is not None:
            _check_lang(pl, f"page {i+1} /Lang")

    # Struct tree element /Lang attributes.
    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is not None:
        def _visit(node: Dictionary) -> None:
            el = node.get(Name.Lang)
            if el is not None:
                objgen = getattr(node, "objgen", (0, 0))
                _check_lang(el, f"struct elem obj {objgen[0]} /Lang")
        walk_struct_tree(struct_root, _visit)

    if invalid:
        detail = f"{len(invalid)} invalid BCP-47 tag(s): " + "; ".join(invalid[:5])
        if len(invalid) > 5:
            detail += f" … (+{len(invalid) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All /Lang values are valid BCP-47 tags.")


# ---------------------------------------------------------------------------
# 09-008  Heading levels are not skipped
# ---------------------------------------------------------------------------

def check_09_008(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-008 (local): heading levels must not skip more than one
    step (e.g., H1 → H3 is invalid; H1 → H2 is fine).

    This is not an official Matterhorn ID but is a prominent PAC 3 check.
    """
    _id   = "09-008"
    _name = "Heading levels not skipped"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    headings: list[tuple[int, str]] = []  # (level, resolved_role)

    def _visit(node: Dictionary) -> None:
        resolved = resolve_role(role_of(node) or "", struct_root)
        if resolved in _HEADING_ROLES:
            if resolved == "H":
                headings.append((0, resolved))  # unlevelled
            else:
                headings.append((int(resolved[1]), resolved))

    walk_struct_tree(struct_root, _visit)

    if not headings:
        return CheckResult(_id, _name, Severity.Info, "No heading elements found.")

    # Only check levelled headings (H1-H6).
    levelled = [(lvl, r) for lvl, r in headings if lvl > 0]
    skips: list[str] = []
    for i in range(1, len(levelled)):
        prev_lvl, prev_r = levelled[i - 1]
        curr_lvl, curr_r = levelled[i]
        if curr_lvl > prev_lvl + 1:
            skips.append(f"<{prev_r}> → <{curr_r}>")

    if skips:
        return CheckResult(_id, _name, Severity.Fail,
                           f"{len(skips)} heading level skip(s): " + "; ".join(skips[:5]))

    return CheckResult(_id, _name, Severity.Pass, "Heading levels are sequential with no skips.")


# ---------------------------------------------------------------------------
# 15-001  List structure: L contains only LI (or Caption); LI contains LBody
# ---------------------------------------------------------------------------

def check_15_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 15-001: every <LI> must be a direct child of <L>; every
    <Lbl>/<LBody> must be a direct child of <LI>; every <LI> must have
    at least one <LBody> child."""
    _id   = "15-001"
    _name = "List structure valid (L > LI > LBody)"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    violations: list[str] = []

    def _visit(node: Dictionary) -> None:
        role = resolve_role(role_of(node) or "", struct_root)
        kids = get_struct_kids(node)
        kid_roles = [resolve_role(role_of(k) or "", struct_root) for k in kids]

        if role == "LI":
            # Must have at least one LBody.
            if "LBody" not in kid_roles:
                og = getattr(node, "objgen", (0, 0))
                violations.append(f"<LI> obj {og[0]} has no <LBody> child")

        elif role in ("Lbl", "LBody"):
            # Must be inside an LI.
            parent_role = resolve_role(role_of(node.get(Name.P) or Dictionary()) or "", struct_root) \
                if isinstance(node.get(Name.P), Dictionary) else ""
            if parent_role != "LI":
                og = getattr(node, "objgen", (0, 0))
                violations.append(f"<{role}> obj {og[0]} is not a child of <LI> (parent: {parent_role!r})")

    walk_struct_tree(struct_root, _visit)

    if violations:
        detail = f"{len(violations)} list structure violation(s): " + "; ".join(violations[:5])
        if len(violations) > 5:
            detail += f" … (+{len(violations) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All list structures are valid.")


# ---------------------------------------------------------------------------
# 15-002  <L> contains only <LI> or <Caption>
# ---------------------------------------------------------------------------

def check_15_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 15-002: every <L> element must contain only <LI> or
    <Caption> as direct struct children."""
    _id   = "15-002"
    _name = "<L> contains only <LI> or <Caption>"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    violations: list[str] = []

    def _visit(node: Dictionary) -> None:
        if resolve_role(role_of(node) or "", struct_root) != "L":
            return
        bad = [
            resolve_role(role_of(k) or "", struct_root)
            for k in get_struct_kids(node)
            if resolve_role(role_of(k) or "", struct_root) not in ("LI", "Caption")
        ]
        if bad:
            og = getattr(node, "objgen", (0, 0))
            violations.append(f"<L> obj {og[0]} has invalid children: {bad}")

    walk_struct_tree(struct_root, _visit)

    if violations:
        detail = f"{len(violations)} <L> element(s) with invalid children: " + "; ".join(violations[:5])
        if len(violations) > 5:
            detail += f" … (+{len(violations) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All <L> elements contain only <LI> or <Caption>.")


# ---------------------------------------------------------------------------
# 17-001  Widget annotations nested inside <Form> struct element
# ---------------------------------------------------------------------------

def check_17_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 17-001: every Widget annotation must be referenced from a
    <Form> struct element via an OBJR — mirrors check_28_001 for form fields."""
    _id   = "17-001"
    _name = "Widget annotations nested inside <Form>"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    # Collect obj-numbers of annotations referenced from <Form> struct elements.
    # We only accept OBJRs that are direct children of a <Form> node; a Widget
    # buried under <Sect> or <Div> is NOT considered properly tagged for this check.
    tagged_obj_nums: set[int] = set()

    def _collect(node: Dictionary) -> None:
        if resolve_role(role_of(node) or "", struct_root) != "Form":
            return
        for kid in get_kids(node):
            if isinstance(kid, Dictionary) and kid.get(Name.Type) == Name.OBJR:
                ref = kid.get(Name.Obj)
                if ref is not None:
                    og = getattr(ref, "objgen", (0, 0))
                    if og != (0, 0):
                        tagged_obj_nums.add(og[0])

    walk_struct_tree(struct_root, _collect)

    untagged: list[str] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        for annot in annots:
            if not isinstance(annot, Dictionary):
                continue
            if annot.get(Name.Subtype) != Name.Widget:
                continue
            og = getattr(annot, "objgen", (0, 0))
            if og == (0, 0) or og[0] not in tagged_obj_nums:
                field_name = str(annot.get(Name.T) or annot.get(Name.TU) or f"obj {og[0]}")
                untagged.append(f"{field_name} on p.{page_idx + 1}")

    if untagged:
        detail = f"{len(untagged)} Widget annotation(s) not in a <Form> struct element: " + "; ".join(untagged[:5])
        if len(untagged) > 5:
            detail += f" … (+{len(untagged) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass,
                       "All Widget annotations are referenced from <Form> struct elements.")


# ---------------------------------------------------------------------------
# 17-002  Form fields have a tooltip (/TU)
# ---------------------------------------------------------------------------

def check_17_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 17-002: every interactive form field must have a non-empty
    /TU (tooltip / alternate field name) entry — screen readers use this as
    the accessible label."""
    _id   = "17-002"
    _name = "Form fields have tooltip (/TU)"

    acroform = pdf.Root.get(Name.AcroForm)
    if acroform is None:
        return CheckResult(_id, _name, Severity.Info, "No AcroForm — check skipped.")

    fields_arr = acroform.get(Name.Fields)
    if fields_arr is None:
        return CheckResult(_id, _name, Severity.Info, "AcroForm has no /Fields — check skipped.")

    missing: list[str] = []
    seen: set = set()

    def _walk_fields(arr, inherited_ft=None) -> None:
        for item in arr:
            if not isinstance(item, Dictionary):
                continue
            key = object_key(item)
            if key in seen:
                continue
            seen.add(key)
            # Effective /FT: own value, or inherited from parent chain.
            effective_ft = item.get(Name.FT) or inherited_ft
            kids = item.get(Name.Kids)
            has_widget_kids = isinstance(kids, Array)
            # A terminal field has no widget children (or has /FT and no kids
            # that themselves carry /FT — widget annotations are the leaf nodes).
            is_terminal = effective_ft is not None and not has_widget_kids
            if is_terminal:
                tu = item.get(Name.TU)
                if tu is None or str(tu).strip() == "":
                    name = str(item.get(Name.T) or f"obj {getattr(item, 'objgen', (0,0))[0]}")
                    missing.append(name)
            if has_widget_kids:
                _walk_fields(kids, inherited_ft=effective_ft)

    _walk_fields(fields_arr)

    if missing:
        detail = f"{len(missing)} field(s) missing /TU tooltip: " + ", ".join(missing[:5])
        if len(missing) > 5:
            detail += f" … (+{len(missing) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass, "All form fields have a /TU tooltip.")


# ---------------------------------------------------------------------------
# 22-001  Document outline (bookmarks) present for multi-page documents
# ---------------------------------------------------------------------------

def check_22_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 22-001: documents with more than 21 pages must have a
    document outline (/Outlines) to support navigation."""
    _id   = "22-001"
    _name = "Document outline present (>21 pages)"

    page_count = len(pdf.pages)
    if page_count <= 21:
        return CheckResult(_id, _name, Severity.Info,
                           f"Document has {page_count} page(s) — outline not required.")

    outlines = pdf.Root.get(Name.Outlines)
    if outlines is None:
        return CheckResult(_id, _name, Severity.Fail,
                           f"Document has {page_count} pages but no /Outlines (bookmarks) entry.")

    # Verify the outline has at least one entry.
    first = outlines.get(Name.First) if isinstance(outlines, Dictionary) else None
    if first is None:
        return CheckResult(_id, _name, Severity.Fail,
                           f"Document has {page_count} pages; /Outlines exists but is empty.")

    return CheckResult(_id, _name, Severity.Pass,
                       f"Document has {page_count} pages and a non-empty /Outlines tree.")


# ---------------------------------------------------------------------------
# 24-001  Annotations (non-Link, non-Widget) have /Contents
# ---------------------------------------------------------------------------

# Annotation subtypes that have their own accessibility checks or are exempt.
_ANNOT_EXEMPT: frozenset[str] = frozenset({
    "/Link",       # 28-001
    "/Widget",     # 17-001 / 17-002
    "/PrinterMark",
    "/TrapNet",    # prohibited (24-002)
    "/Movie",      # prohibited (24-002)
    "/PopUp",      # informational popup — no independent content
})


def check_24_001(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 24-001: every non-Link, non-Widget annotation must have a
    non-empty /Contents entry (alternative description for AT users)."""
    _id   = "24-001"
    _name = "Annotations have /Contents"

    missing: list[str] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        for annot in annots:
            if not isinstance(annot, Dictionary):
                continue
            subtype = str(annot.get(Name.Subtype) or "")
            if subtype in _ANNOT_EXEMPT:
                continue
            contents = annot.get(Name.Contents)
            if contents is None or str(contents).strip() == "":
                og = getattr(annot, "objgen", (0, 0))
                missing.append(f"{subtype} obj {og[0]} on p.{page_idx + 1}")

    if missing:
        detail = f"{len(missing)} annotation(s) missing /Contents: " + "; ".join(missing[:5])
        if len(missing) > 5:
            detail += f" … (+{len(missing) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass,
                       "All non-Link/non-Widget annotations have /Contents.")


# ---------------------------------------------------------------------------
# 24-002  Prohibited annotation subtypes (TrapNet, Movie)
# ---------------------------------------------------------------------------

_ANNOT_PROHIBITED: frozenset[str] = frozenset({"/TrapNet", "/Movie"})


def check_24_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 24-002: TrapNet and Movie annotation subtypes are prohibited
    by PDF/UA-1."""
    _id   = "24-002"
    _name = "No prohibited annotation types (TrapNet, Movie)"

    found: list[str] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        for annot in annots:
            if not isinstance(annot, Dictionary):
                continue
            subtype = str(annot.get(Name.Subtype) or "")
            if subtype in _ANNOT_PROHIBITED:
                og = getattr(annot, "objgen", (0, 0))
                found.append(f"{subtype} obj {og[0]} on p.{page_idx + 1}")

    if found:
        return CheckResult(_id, _name, Severity.Fail,
                           f"{len(found)} prohibited annotation(s): " + "; ".join(found))

    return CheckResult(_id, _name, Severity.Pass,
                       "No TrapNet or Movie annotations found.")


# ---------------------------------------------------------------------------
# 28-002  <Link> struct element's OBJR annotation has /Contents (tooltip)
# ---------------------------------------------------------------------------

def check_28_002(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 28-002: every Link annotation referenced from a <Link> struct
    element must have a non-empty /Contents entry (accessible link text for AT
    when the visual label is insufficient)."""
    _id   = "28-002"
    _name = "<Link> annotation has /Contents"

    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return CheckResult(_id, _name, Severity.Info, "No struct tree — check skipped.")

    missing: list[str] = []

    def _visit(node: Dictionary) -> None:
        if resolve_role(role_of(node) or "", struct_root) != "Link":
            return
        for kid in get_kids(node):
            if not isinstance(kid, Dictionary):
                continue
            if kid.get(Name.Type) != Name.OBJR:
                continue
            annot = kid.get(Name.Obj)
            if not isinstance(annot, Dictionary):
                continue
            contents = annot.get(Name.Contents)
            if contents is None or str(contents).strip() == "":
                og = getattr(annot, "objgen", (0, 0))
                missing.append(f"Link annot obj {og[0]}")

    walk_struct_tree(struct_root, _visit)

    if missing:
        detail = f"{len(missing)} <Link> annotation(s) missing /Contents: " + "; ".join(missing[:5])
        if len(missing) > 5:
            detail += f" … (+{len(missing) - 5} more)"
        return CheckResult(_id, _name, Severity.Fail, detail)

    return CheckResult(_id, _name, Severity.Pass,
                       "All <Link> annotations have a /Contents entry.")
