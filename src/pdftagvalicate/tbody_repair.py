"""Dissolve fake Table -> TBody -> TR -> TD wrapper chains.

A "fake table" is a <Table> struct element that:
  (a) has no <THead> or <TFoot> section, and
  (b) contains only a single <TBody> whose rows each hold exactly one cell
      (a <TD> or <TH>).

Such chains are sometimes produced by upstream conversion tools and confuse
assistive technology.  We dissolve them by re-parenting every cell's children
directly under the table's original parent element.

Enhanced in P1: handles multi-row fake tables (all rows must be single-cell)
and skips over transparent wrapper elements (Part, Div, Sect, …) when
locating the TBody or TR layer, so realistic malformed input is no longer
silently skipped.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Dictionary, Name

from .pdfutil import get_kids, object_key, replace_kid, role_of
from .types import RepairReport


def fix(pdf: pikepdf.Pdf) -> RepairReport:
    name = "Fake TBody wrappers"

    if not is_tagged(pdf):
        return RepairReport(name, 0, "Document is not tagged - skipped.")

    tables = collect_fake_tables(pdf)

    changes = 0
    for table in tables:
        try:
            if _try_fix_fake_table(table, pdf):
                changes += 1
        except Exception:  # noqa: BLE001 - one malformed table shouldn't abort the rest
            continue

    if changes > 0:
        return RepairReport(name, changes, f"Dissolved {changes} fake Table->TBody->TR->TD chain(s).")
    return RepairReport(name, 0, "No fake-table wrappers found.")


# ---- helpers ---------------------------------------------------------------


# Roles that are transparent structural wrappers — we skip over them when
# searching for TBody / TR layers in a fake-table chain.
_WRAPPER_ROLES: frozenset[str] = frozenset({
    "Part", "Div", "Sect", "Art", "BlockQuote", "NonStruct", "Private",
})


def _unwrap(elem: Dictionary, target_role: str) -> Dictionary | None:
    """Return *elem* if its role matches *target_role*, otherwise descend
    through transparent wrapper elements (Part, Div, Sect, …) looking for
    a single descendant with that role.  Returns ``None`` if not found or
    if there is more than one candidate (ambiguous)."""
    if role_of(elem) == target_role:
        return elem
    if role_of(elem) not in _WRAPPER_ROLES:
        return None
    struct_kids = [k for k in get_kids(elem) if isinstance(k, Dictionary)]
    candidates = [k for k in struct_kids if _unwrap(k, target_role) is not None]
    if len(candidates) == 1:
        return _unwrap(candidates[0], target_role)
    return None


def _try_fix_fake_table(table: Dictionary, pdf: pikepdf.Pdf) -> bool:
    """Attempt to dissolve *table* if it is a fake-table wrapper chain.

    Recognises:
    - Tables with no THead/TFoot.
    - A single TBody (possibly behind wrapper elements) whose rows
      *all* contain exactly one cell (TD or TH).
    - Multi-row fake tables: every TR must have exactly one cell.

    Returns True if the table was dissolved, False otherwise.
    """
    if _has_kid_role(table, "THead") or _has_kid_role(table, "TFoot"):
        return None

    # Find a single TBody, optionally behind wrapper elements.
    dict_kids = _get_all_dict_kids(table)
    tbody_candidates = [_unwrap(k, "TBody") for k in dict_kids]
    tbody_candidates = [t for t in tbody_candidates if t is not None]
    if len(tbody_candidates) != 1:
        return False
    tbody = tbody_candidates[0]

    # Collect all TR rows (possibly behind wrappers inside TBody).
    tr_rows = _collect_trs(tbody)
    if not tr_rows:
        return False

    # Every row must have exactly one cell for this to qualify as a fake table.
    row_cells: list[Dictionary] = []
    for tr in tr_rows:
        dict_tr_kids = _get_all_dict_kids(tr)
        cells = [k for k in dict_tr_kids if role_of(k) in ("TD", "TH")]
        if len(cells) != 1:
            return False   # real multi-column table — leave it alone
        row_cells.append(cells[0])

    parent = table.get(Name.P)
    if not isinstance(parent, Dictionary):
        return False

    # Gather all content children from every cell.
    all_children: list = []
    for cell in row_cells:
        children = get_kids(cell)
        if not children:
            continue
        for child in children:
            if isinstance(child, Dictionary):
                child[Name.P] = parent
        all_children.extend(children)

    if not all_children:
        return False

    # --- ParentTree repair ---------------------------------------------------
    discarded_keys = {object_key(table), object_key(tbody)}
    for tr in tr_rows:
        discarded_keys.add(object_key(tr))
    for cell in row_cells:
        discarded_keys.add(object_key(cell))
    _repoint_parent_tree_entries(pdf, discarded_keys, parent)
    # -------------------------------------------------------------------------

    return replace_kid(parent, table, all_children)


def _collect_trs(section: Dictionary) -> list[Dictionary]:
    """Collect all TR elements that are direct struct children of *section*,
    skipping transparent wrapper elements one level deep."""
    trs: list[Dictionary] = []
    for kid in _get_all_dict_kids(section):
        r = role_of(kid)
        if r == "TR":
            trs.append(kid)
        elif r in _WRAPPER_ROLES:
            # Descend one extra level through wrappers.
            for grandkid in _get_all_dict_kids(kid):
                if role_of(grandkid) == "TR":
                    trs.append(grandkid)
    return trs


def _repoint_parent_tree_entries(
    pdf: pikepdf.Pdf,
    discarded_keys: set,
    new_parent: Dictionary,
) -> None:
    """Scan the flat /Nums section of ParentTree and redirect any entry that
    points to one of the *discarded* struct elements so it now points at
    *new_parent*.  Silently skips /Kids-shaped trees (we don’t corrupt them).
    """
    struct_root = pdf.Root.get(Name.StructTreeRoot)
    if struct_root is None:
        return
    pt = struct_root.get(Name.ParentTree)
    if pt is None:
        return
    nums = pt.get(Name.Nums)
    if not isinstance(nums, Array):
        return

    def _is_discarded(obj) -> bool:
        if not isinstance(obj, Dictionary):
            return False
        return object_key(obj) in discarded_keys

    for i in range(1, len(nums), 2):
        entry = nums[i]
        # Each entry is either a single struct-element ref or an array of refs
        if isinstance(entry, Array):
            for j, item in enumerate(entry):
                if _is_discarded(item):
                    entry[j] = new_parent
        elif _is_discarded(entry):
            nums[i] = new_parent


def _collect_by_role(k, role: str, result: list, visited: set) -> None:
    if k is None:
        return
    if isinstance(k, Array):
        for item in k:
            _collect_by_role(item, role, result, visited)
        return
    if not isinstance(k, Dictionary):
        return

    visit_key = object_key(k)
    if visit_key in visited:
        return
    visited.add(visit_key)

    if role_of(k) == role:
        result.append(k)
    _collect_by_role(k.get(Name.K), role, result, visited)


def _get_all_dict_kids(elem: Dictionary) -> list:
    return [k for k in get_kids(elem) if isinstance(k, Dictionary)]


def _has_kid_role(elem: Dictionary, role: str) -> bool:
    if _get_single_kid_by_role(elem, role) is not None:
        return True
    return any(role_of(d) == role for d in _get_all_dict_kids(elem))


def _get_single_kid_by_role(elem: Dictionary, role: str) -> Dictionary | None:
    kids = _get_all_dict_kids(elem)
    if len(kids) == 1 and role_of(kids[0]) == role:
        return kids[0]
    return None


