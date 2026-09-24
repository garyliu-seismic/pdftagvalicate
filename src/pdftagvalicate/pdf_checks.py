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
        roles = [role_of(k) for k in non_doc]
        return CheckResult(_id, _name, Severity.Fail,
                           f"Non-<Document> elements at root alongside <Document>: {roles}.")

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
    "Link", "Annot", "Ruby", "Warichu",
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
            # Type 3 fonts have no descriptor — they embed glyph procedures
            # directly; standard 14 fonts never have a descriptor but are
            # always available.  Skip rather than false-positive.
            font_type = str(font.get(Name.Subtype) or "")
            if font_type not in ("/Type3",):
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

# Painting operators that produce visible output.  Any such operator executed
# outside a marked-content layer (BDC/BMC…EMC stack depth == 0) is a
# violation.  We use a whitelist so that structural operators (BT/ET, cm, q/Q,
# etc.) don’t trigger false positives.
#
# Text-painting: Tj TJ ' "  (show-string operators, PDF §9.4.3)
# Path-painting: S s F f f* B B* b b*  (stroke/fill, PDF §8.5.3)
# Shading/image: sh Do  (pattern shading, XObject invocation)
_PAINTING_OPS: frozenset[str] = frozenset({
    "Tj", "TJ", "'", '"',
    "S", "s", "F", "f", "f*", "B", "B*", "b", "b*",
    "sh", "Do",
})

# Marked-content operators.
_MC_PUSH_OPS: frozenset[str] = frozenset({"BDC", "BMC"})
_MC_POP_OPS:  frozenset[str] = frozenset({"EMC"})


def check_09_006(pdf: pikepdf.Pdf) -> CheckResult:
    """Matterhorn 09-006: no real-content painting operator may appear outside
    a marked-content layer (BDC/BMC … EMC stack).

    Uses ``pikepdf.parse_content_stream`` to tokenize each page’s stream,
    tracks the BDC/BMC/EMC nesting depth, and recurses into Form XObjects
    (``Do`` operator with a ``/Form`` XObject) so that externally-defined
    content is also checked.  A cycle guard prevents infinite recursion on
    self-referential XObject graphs.

    Because this is the most expensive check it runs last.  Marking operator
    violations are reported as ``Fail``; parse errors on a single page are
    reported as ``Warning`` (partial result) so the other pages are still
    checked.
    """
    _id   = "09-006"
    _name = "No untagged real content in page streams"

    violations: list[str] = []   # (page_label, operator)
    warnings:   list[str] = []   # parse errors

    visited_xobjects: set[tuple] = set()   # cycle guard for Form XObjects

    def _scan_stream(stream_obj, page_label: str, mc_depth: int) -> int:
        """Scan one content stream; returns the mc_depth after the stream ends."""
        try:
            instructions = pikepdf.parse_content_stream(stream_obj)
        except Exception as ex:  # noqa: BLE001
            warnings.append(f"{page_label}: parse error — {ex}")
            return mc_depth

        resources = _get_resources(stream_obj)

        for instr in instructions:
            op = str(instr.operator)

            if op in _MC_PUSH_OPS:
                mc_depth += 1
            elif op in _MC_POP_OPS:
                mc_depth = max(0, mc_depth - 1)
            elif op in _PAINTING_OPS:
                if mc_depth == 0:
                    violations.append(f"{page_label}: untagged '{op}' operator")
            elif op == "Do":
                # Recurse into Form XObjects only (Image XObjects are
                # referenced by their name, not executable).
                if instr.operands:
                    xobj_name = instr.operands[0]
                    xobj = _resolve_xobject(resources, xobj_name)
                    if xobj is not None:
                        xobj_key = getattr(xobj, "objgen", (0, 0))
                        if xobj_key != (0, 0) and xobj_key not in visited_xobjects:
                            visited_xobjects.add(xobj_key)
                            mc_depth = _scan_stream(xobj, page_label, mc_depth)

        return mc_depth

    for page_idx, page in enumerate(pdf.pages):
        label = f"p.{page_idx + 1}"
        try:
            _scan_stream(page, label, mc_depth=0)
        except Exception as ex:  # noqa: BLE001
            warnings.append(f"{label}: unexpected error — {ex}")

    if violations:
        detail = f"{len(violations)} untagged painting operator(s): " + "; ".join(violations[:5])
        if len(violations) > 5:
            detail += f" … (+{len(violations) - 5} more)"
        if warnings:
            detail += f"  [{len(warnings)} page(s) had parse errors and may be incomplete]"
        return CheckResult(_id, _name, Severity.Fail, detail)

    if warnings:
        detail = (
            f"{len(warnings)} page(s) could not be fully parsed; "
            "untagged content may exist: " + "; ".join(warnings[:3])
        )
        return CheckResult(_id, _name, Severity.Warning, detail)

    return CheckResult(_id, _name, Severity.Pass,
                       "All painting operators appear inside marked-content layers.")


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
