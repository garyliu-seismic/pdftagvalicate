"""Orchestrates running the selected set of repairs against an open PDF.

When all three struct-tree repairs are selected together (i.e. ``--all``),
``run_repairs`` performs a *single* depth-first walk of the struct tree and
dispatches to each repair's collector in the same pass, then applies the
collected findings.  This avoids three separate O(n) traversals at large-
document scale while keeping each repair module self-contained.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Dictionary, Name

from . import link_nesting_repair, metadata_repairs, tbody_repair, th_scope_repair
from .pdfutil import get_kids, object_key, role_of, walk_struct_tree
from .types import RepairOptions, RepairReport


def run_repairs(pdf: pikepdf.Pdf, options: RepairOptions) -> list[RepairReport]:
    reports: list[RepairReport] = []

    if options.metadata:
        _run_one(reports, lambda: metadata_repairs.fix_pdf_ua_identifier(pdf))
        _run_one(reports, lambda: metadata_repairs.fix_mark_info(pdf))
        _run_one(reports, lambda: metadata_repairs.fix_display_doc_title(pdf))

    # When all three struct-tree repairs are active, do one combined walk.
    if options.fix_tbody and options.th_scope and options.link_nesting:
        _run_one(reports, lambda: _fix_struct_tree_combined(pdf))
    else:
        if options.fix_tbody:
            _run_one(reports, lambda: tbody_repair.fix(pdf))
        if options.th_scope:
            _run_one(reports, lambda: th_scope_repair.fix(pdf))
        if options.link_nesting:
            _run_one(reports, lambda: link_nesting_repair.fix(pdf))

    return reports


# ---------------------------------------------------------------------------
# Combined single-pass struct-tree repair (used by --all)
# ---------------------------------------------------------------------------

def _fix_struct_tree_combined(pdf: pikepdf.Pdf) -> list[RepairReport]:
    """Run tbody, th-scope, and link-nesting repairs in a single struct-tree
    walk.  Returns three RepairReports in the same order as the individual
    repairs would produce."""

    # ---- tbody: collect Table elements -------------------------------------
    tables: list[Dictionary] = []
    _collect_by_role_visited: set = set()

    # ---- th-scope: collect missing-scope findings --------------------------
    scope_findings: list[tuple[Dictionary, str]] = []

    # ---- link-nesting: collect already-tagged annotation obj-numbers -------
    tagged_obj_nums: set[int] = set()

    struct_root = pdf.Root.get(Name.StructTreeRoot)

    # Single walk: dispatch to all three collectors at each node.
    if struct_root is not None:
        def _visit(node: Dictionary) -> None:
            r = role_of(node)

            # tbody collector: gather Table elements (same logic as
            # tbody_repair._collect_by_role but inline to avoid a second walk).
            if r == "Table":
                tables.append(node)

            # th-scope collector: when we hit a Table, walk it for TH scope.
            if r == "Table":
                th_scope_repair._walk_table(node, scope_findings)

            # link-nesting collector: OBJR inside a Link → record annot obj#.
            if r == "Link":
                for kid in get_kids(node):
                    if isinstance(kid, Dictionary) and kid.get(Name.Type) == Name.OBJR:
                        annot_ref = kid.get(Name.Obj)
                        if annot_ref is not None:
                            objgen = getattr(annot_ref, "objgen", (0, 0))
                            if objgen != (0, 0):
                                tagged_obj_nums.add(objgen[0])

        walk_struct_tree(struct_root, _visit)

    # ---- Apply tbody fixes -------------------------------------------------
    tbody_changes = 0
    for table in tables:
        try:
            if tbody_repair._try_fix_fake_table(table, pdf):
                tbody_changes += 1
        except Exception:  # noqa: BLE001
            continue

    tbody_report = (
        RepairReport("Fake TBody wrappers", tbody_changes,
                     f"Dissolved {tbody_changes} fake Table->TBody->TR->TD chain(s).")
        if tbody_changes > 0
        else RepairReport("Fake TBody wrappers", 0, "No fake-table wrappers found.")
    )

    # ---- Apply th-scope fixes ----------------------------------------------
    if not scope_findings:
        scope_report = RepairReport("TH /Scope attribute", 0,
                                    "All <TH> cells already have /Scope.")
    else:
        for elem, scope in scope_findings:
            th_scope_repair._apply_scope(elem, scope)
        col = sum(1 for _, s in scope_findings if s == "Column")
        row = sum(1 for _, s in scope_findings if s == "Row")
        scope_report = RepairReport(
            "TH /Scope attribute", len(scope_findings),
            f"Added /Scope to {len(scope_findings)} <TH> cell(s): {col} /Column, {row} /Row."
        )

    # ---- Apply link-nesting fixes ------------------------------------------
    # Delegate to link_nesting_repair.fix() for the annotation walk + ParentTree
    # wiring — that logic is not trivially separable from the page loop.
    # We pass `tagged_obj_nums` by pre-populating it so the repair skips the
    # struct-tree collection phase it would otherwise repeat.
    link_report = _fix_link_nesting_with_known_tagged(pdf, tagged_obj_nums)

    return [tbody_report, scope_report, link_report]


def _fix_link_nesting_with_known_tagged(
    pdf: pikepdf.Pdf, tagged_obj_nums: set[int]
) -> RepairReport:
    """link_nesting repair using a pre-collected tagged-obj set (skips the
    struct-tree walk that link_nesting_repair.fix() would otherwise do)."""
    from .pdfutil import append_kid, ensure_tagged, is_tagged

    name = "Link annotation nesting"

    if not is_tagged(pdf):
        try:
            ensure_tagged(pdf)
        except Exception as ex:  # noqa: BLE001
            return RepairReport(name, 0,
                                f"Could not enable tagging on this document: {ex}")

    root = pdf.Root.get(Name.StructTreeRoot)
    doc_elem = (link_nesting_repair._find_document_element(root)
                or link_nesting_repair._create_document_element(pdf, root))

    parent_tree = link_nesting_repair._ensure_parent_tree(pdf, root)
    try:
        nums = link_nesting_repair._ensure_nums(parent_tree)
    except ValueError as ex:
        return RepairReport(name, 0, str(ex))
    next_key = link_nesting_repair._next_parent_tree_key(nums, root)

    fixed = 0
    for page in pdf.pages:
        annots = page.get(Name.Annots)
        if annots is None:
            continue
        for annot in annots:
            if not isinstance(annot, Dictionary):
                continue
            if annot.get(Name.Subtype) != Name.Link:
                continue
            if getattr(annot, "objgen", (0, 0)) == (0, 0):
                annot = pdf.make_indirect(annot)  # noqa: PLW2901
                raw_annots = page.get(Name.Annots)
                if isinstance(raw_annots, Array):
                    for idx, item in enumerate(raw_annots):
                        if item is annot or (
                            getattr(item, "objgen", None) == (0, 0)
                            and id(item) == id(annot)
                        ):
                            raw_annots[idx] = annot
                            break
            objgen = annot.objgen
            if objgen[0] in tagged_obj_nums:
                continue
            page_obj = page.obj
            obj_ref = Dictionary(Type=Name.OBJR, Pg=page_obj, Obj=annot)
            link_dict = pdf.make_indirect(
                Dictionary(Type=Name.StructElem, S=Name.Link,
                           Pg=page_obj, P=doc_elem, K=obj_ref)
            )
            append_kid(doc_elem, link_dict)
            annot[Name.StructParent] = next_key
            nums.append(next_key)
            nums.append(link_dict)
            next_key += 1
            fixed += 1

    root[Name.ParentTreeNextKey] = next_key

    if fixed > 0:
        return RepairReport(name, fixed,
                            f"Wrapped {fixed} Link annotation(s) inside <Link> struct elements.")
    return RepairReport(name, 0, "All Link annotations are already properly nested.")


def _run_one(reports: list[RepairReport], repair) -> None:
    """Runs a single repair, catching any unexpected exception so the others
    still run; surfaces the failure as a zero-fixed report."""
    try:
        result = repair()
        # Combined repairs return a list; individual ones return a single report.
        if isinstance(result, list):
            reports.extend(result)
        else:
            reports.append(result)
    except Exception as ex:  # noqa: BLE001
        reports.append(RepairReport(type(ex).__name__, 0, f"Unexpected error: {ex}"))
