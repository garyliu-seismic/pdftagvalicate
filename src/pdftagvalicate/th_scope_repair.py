"""Add a /Scope attribute to <TH> cells that are missing one.

Walks each <Table> top-down, tracking whether we're inside a <THead> section
(column headers) or a body/foot row that also contains <TD> cells (row
headers), to infer the correct scope for each unscoped <TH>.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Dictionary, Name

from .pdfutil import get_kids, get_struct_kids, is_tagged, object_key, role_of

# Roles treated as transparent wrappers when searching for table sections/rows.
_WRAPPER_ROLES: frozenset[str] = frozenset({
    "Part", "Div", "Sect", "Art", "BlockQuote", "NonStruct", "Private",
})
from .types import RepairReport


def collect_missing_scopes(pdf: pikepdf.Pdf) -> list[tuple[Dictionary, str]]:
    """Read-only: returns (TH element, inferred scope) for each <TH> cell
    missing a /Scope attribute. Does not modify the PDF."""
    struct_root = pdf.Root.get(Name.StructTreeRoot)
    findings: list[tuple[Dictionary, str]] = []
    if struct_root is not None:
        _collect_missing_scopes(struct_root, findings, set())
    return findings


def fix(pdf: pikepdf.Pdf) -> RepairReport:
    name = "TH /Scope attribute"

    if not is_tagged(pdf):
        return RepairReport(name, 0, "Document is not tagged - skipped.")

    findings = collect_missing_scopes(pdf)

    if not findings:
        return RepairReport(name, 0, "All <TH> cells already have /Scope.")

    for elem, scope in findings:
        _apply_scope(elem, scope)

    col = sum(1 for _, scope in findings if scope == "Column")
    row = sum(1 for _, scope in findings if scope == "Row")
    return RepairReport(
        name, len(findings), f"Added /Scope to {len(findings)} <TH> cell(s): {col} /Column, {row} /Row."
    )


# ---- traversal ---------------------------------------------------------------


def _collect_missing_scopes(node, findings: list, visited: set | None = None) -> None:
    if visited is None:
        visited = set()
    if not isinstance(node, Dictionary):
        return
    node_key = getattr(node, "objgen", (0, 0))
    node_key = node_key if node_key != (0, 0) else id(node)
    if node_key in visited:
        return
    visited.add(node_key)
    if role_of(node) == "Table":
        _walk_table(node, findings)
        return
    for kid in get_kids(node):
        _collect_missing_scopes(kid, findings, visited)


def _walk_table(table: Dictionary, findings: list) -> None:
    """Walk a <Table> element, tolerating wrapper elements (Div, Part, …)
    between the Table and its section/row children."""
    for kid in _iter_struct_through_wrappers(table):
        role = role_of(kid)
        if role == "THead":
            _walk_section(kid, is_head=True, findings=findings)
        elif role in ("TBody", "TFoot"):
            _walk_section(kid, is_head=False, findings=findings)
        elif role == "TR":
            _walk_row(kid, is_head=False, findings=findings)


def _walk_section(section: Dictionary, is_head: bool, findings: list) -> None:
    """Walk a THead/TBody/TFoot, tolerating wrapper elements before TR."""
    for kid in _iter_struct_through_wrappers(section):
        if role_of(kid) == "TR":
            _walk_row(kid, is_head, findings)


def _iter_struct_through_wrappers(elem: Dictionary):
    """Yield direct struct-element children of *elem*, descending one level
    into transparent wrapper elements (Part, Div, …) so that wrapper-wrapped
    sections and rows are visible to the caller."""
    for kid in get_struct_kids(elem):
        if role_of(kid) in _WRAPPER_ROLES:
            # One level of wrapper: yield the wrapper's struct children.
            for grandkid in get_struct_kids(kid):
                yield grandkid
        else:
            yield kid


def _walk_row(tr: Dictionary, is_head: bool, findings: list) -> None:
    kids = get_struct_kids(tr)
    has_td = any(role_of(k) == "TD" for k in kids)

    for kid in kids:
        if role_of(kid) != "TH":
            continue
        if _has_scope(kid):
            continue
        scope = "Column" if is_head else ("Row" if has_td else "Column")
        findings.append((kid, scope))


def _has_scope(elem: Dictionary) -> bool:
    a = elem.get(Name.A)
    if isinstance(a, Dictionary):
        return Name.Scope in a
    if isinstance(a, Array):
        return any(isinstance(item, Dictionary) and Name.Scope in item for item in a)
    return False


def _apply_scope(elem: Dictionary, scope: str) -> None:
    scope_name = Name.Column if scope == "Column" else Name.Row
    a = elem.get(Name.A)

    if isinstance(a, Dictionary):
        # Clone the attribute dict before mutating to avoid corrupting a
        # shared/aliased /A object referenced by another struct element.
        attr_dict = Dictionary()
        for key in a.keys():
            attr_dict[key] = a[key]
        elem[Name.A] = attr_dict
    elif isinstance(a, Array):
        table_owner = next(
            (item for item in a if isinstance(item, Dictionary) and item.get(Name.O) == Name.Table),
            None,
        )
        if table_owner is not None:
            # Clone to avoid mutating a shared dict.
            new_owner = Dictionary()
            for key in table_owner.keys():
                new_owner[key] = table_owner[key]
            new_array = Array([])
            for item in a:
                if item is table_owner or (
                    isinstance(item, Dictionary) and item.get(Name.O) == Name.Table
                ):
                    new_array.append(new_owner)
                else:
                    new_array.append(item)
            elem[Name.A] = new_array
            attr_dict = new_owner
        else:
            attr_dict = Dictionary()
            new_array = Array(list(a) + [attr_dict])
            elem[Name.A] = new_array
    else:
        attr_dict = Dictionary()
        elem[Name.A] = attr_dict

    attr_dict[Name.O] = Name.Table
    attr_dict[Name.Scope] = scope_name
