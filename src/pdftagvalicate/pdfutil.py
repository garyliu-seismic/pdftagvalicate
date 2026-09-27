"""Small helpers shared across repair modules.

pikepdf transparently dereferences indirect references when you read a
dictionary/array value, so unlike the original iText port we rarely need to
resolve references by hand. The one place identity still matters is when we
need to find *which* slot in a parent's /K array holds a particular struct
element so we can replace or remove it — for that we compare by (obj, gen)
via ``same_object``.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Optional

import pikepdf
from pikepdf import Array, Dictionary, Name, Object

# Common XMP namespaces (element local names are matched against these).
DC_NS = "http://purl.org/dc/elements/1.1/"
PDFUAID_NS = "http://www.aiim.org/pdfua/ns/id/"


def is_tagged(pdf: pikepdf.Pdf) -> bool:
    """Mirrors iText's PdfDocument.IsTagged(): a StructTreeRoot exists and
    /MarkInfo /Marked is true."""
    root = pdf.Root
    struct_root = root.get(Name.StructTreeRoot)
    mark_info = root.get(Name.MarkInfo)
    marked = bool(mark_info.get(Name.Marked)) if mark_info is not None else False
    return struct_root is not None and marked


def ensure_tagged(pdf: pikepdf.Pdf) -> None:
    """Mirrors iText's PdfDocument.SetTagged(): ensure /MarkInfo /Marked and a
    minimal /StructTreeRoot both exist."""
    root = pdf.Root

    mark_info = root.get(Name.MarkInfo)
    if mark_info is None:
        mark_info = pdf.make_indirect(Dictionary())
        root[Name.MarkInfo] = mark_info
    mark_info[Name.Marked] = True

    if root.get(Name.StructTreeRoot) is None:
        struct_root = pdf.make_indirect(
            Dictionary(Type=Name.StructTreeRoot, ParentTree=Dictionary(Nums=Array([])))
        )
        root[Name.StructTreeRoot] = struct_root


def get_xmp_property(
    pdf: pikepdf.Pdf, local_name: str, namespace: Optional[str] = None
) -> Optional[str]:
    """Read an XMP property without mutating the PDF.

    pikepdf's ``open_metadata()`` mutates the document even in read-only mode
    (it creates a /Metadata stream and syncs/clears the legacy /Info
    dictionary), so report-only checks must not use it. Instead we read the
    raw /Metadata stream bytes and parse them here.

    Returns the property's text, or the first ``rdf:li`` text for
    Bag/Alt/Seq properties (e.g. dc:title, dc:language).
    """
    md = pdf.Root.get(Name.Metadata)
    if md is None:
        return None
    try:
        raw = md.read_raw_bytes()
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except (ET.ParseError, AttributeError, RuntimeError, ValueError):
        return None

    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if "}" in el.tag:
            ns, name = el.tag[1:].split("}", 1)
        else:
            ns, name = "", el.tag
        if name != local_name:
            continue
        if namespace is not None and ns != namespace:
            continue

        if el.text and el.text.strip():
            return el.text.strip()
        for li in el.iter():
            if not isinstance(li.tag, str):
                continue
            if li.tag.rsplit("}", 1)[-1] == "li" and li.text and li.text.strip():
                return li.text.strip()
        return None
    return None


def get_kids(elem: Dictionary) -> list:
    """Returns the raw contents of /K as a Python list, regardless of whether
    /K is a single value or an array. Kids may be struct-element
    dictionaries, OBJR/MCR dictionaries, or bare MCIDs (ints)."""
    k = elem.get(Name.K)
    if k is None:
        return []
    if isinstance(k, Array):
        return list(k)
    return [k]


def get_struct_kids(elem: Dictionary) -> list:
    """Kids of /K that are themselves struct elements (i.e. have /S)."""
    return [k for k in get_kids(elem) if isinstance(k, Dictionary) and Name.S in k]


def role_of(elem) -> Optional[str]:
    if not isinstance(elem, Dictionary):
        return None
    name = elem.get(Name.S)
    return str(name)[1:] if name is not None else None  # strip leading '/'


def visit_key(obj) -> tuple | int:
    """Stable identity key for cycle detection when walking a struct tree.

    Uses the (obj, gen) pair for indirect objects and ``id()`` for direct
    objects, so a malformed /K that points back at an ancestor can be
    detected instead of recursing forever.
    """
    objgen = getattr(obj, "objgen", (0, 0))
    return objgen if objgen != (0, 0) else id(obj)


def same_object(a: Object, b: Object) -> bool:
    """Identity comparison that works for both indirect and direct objects."""
    try:
        a_ref, b_ref = a.objgen, b.objgen
    except AttributeError:
        return a is b
    if a_ref != (0, 0) or b_ref != (0, 0):
        return a_ref == b_ref
    return a is b


def replace_kid(parent: Dictionary, old_kid: Dictionary, new_kids: Iterable[Object]) -> bool:
    """Replaces old_kid inside parent's /K with new_kids (0, 1 or many)."""
    new_kids = list(new_kids)
    k = parent.get(Name.K)
    if isinstance(k, Array):
        for i, item in enumerate(k):
            if same_object(item, old_kid):
                items = list(k)
                items[i:i + 1] = new_kids
                parent[Name.K] = Array(items)
                return True
        return False
    if k is not None and same_object(k, old_kid):
        if len(new_kids) == 1:
            parent[Name.K] = new_kids[0]
        else:
            parent[Name.K] = Array(new_kids)
        return True
    return False


def object_key(obj) -> object:
    """Stable identity key for a pikepdf object.

    Returns ``(obj_number, gen_number)`` for indirect objects and ``id(obj)``
    for bare direct objects.  Use this (not ``objgen`` alone) whenever you need
    a hashable key that distinguishes direct objects from one another.

    This consolidates the independent ``_visit_key`` implementations that used
    to live in *tbody_repair* and *link_nesting_repair* so they can’t silently
    diverge.
    """
    objgen = getattr(obj, "objgen", (0, 0))
    return objgen if objgen != (0, 0) else id(obj)


def walk_struct_tree(
    node,
    visitor,
    visited: set | None = None,
) -> None:
    """Depth-first walk of a PDF struct tree.

    Calls ``visitor(node)`` for every *Dictionary* node encountered (including
    *node* itself).  A cycle guard (via :func:`object_key`) prevents infinite
    loops on malformed/cyclic struct trees — exactly the input class this tool
    targets.

    Parameters
    ----------
    node:
        Starting node — may be a :class:`~pikepdf.Dictionary`,
        :class:`~pikepdf.Array`, or anything else (non-dict values are skipped).
    visitor:
        Callable receiving each dictionary node.  Return value is ignored.
    visited:
        Mutable set of already-seen :func:`object_key` values; created
        automatically on the first call.
    """
    if visited is None:
        visited = set()
    if isinstance(node, Array):
        for item in node:
            walk_struct_tree(item, visitor, visited)
        return
    if not isinstance(node, Dictionary):
        return
    key = object_key(node)
    if key in visited:
        return
    visited.add(key)
    visitor(node)
    k = node.get(Name.K)
    if k is not None:
        walk_struct_tree(k, visitor, visited)


# ---------------------------------------------------------------------------
# P3 validator helpers
# ---------------------------------------------------------------------------

# Standard PDF 1.7 structure roles (PDF 1.7 §14.8.4).
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


def resolve_role(role: str, struct_root: Dictionary) -> str:
    """Resolve *role* transitively through ``StructTreeRoot/RoleMap``.

    Returns the terminal standard role name, or *role* itself if it is
    already standard or if the RoleMap is absent.  A cycle guard prevents
    infinite loops on malformed role maps.

    Shared by: check 14-001 (role map validity) and 09-007 (first heading).
    """
    if role in _STANDARD_ROLES:
        return role

    role_map = struct_root.get(Name.RoleMap)
    if role_map is None or not isinstance(role_map, Dictionary):
        return role

    visited: set[str] = set()
    current = role
    while current not in _STANDARD_ROLES:
        if current in visited:
            # Cycle detected — return the last seen name.
            return current
        visited.add(current)
        mapped = role_map.get(Name("/" + current))
        if mapped is None:
            return current  # not in role map → unresolvable
        current = str(mapped)[1:]  # strip leading '/'
    return current


def find_page_index(struct_elem: Dictionary, pdf: pikepdf.Pdf) -> Optional[int]:
    """Return the zero-based page index for the content of *struct_elem*.

    Strategy (mirrors C# ``FindPage()``):
    1. ``/Pg`` on the element itself.
    2. ``/Pg`` on the first MCR or OBJR descendant.
    3. ``None`` if no page reference can be found.

    The C# original duplicates this pattern in 09-004, 14-002, 14-003,
    14-004.  One shared helper avoids the drift.
    """
    # Build a fast page-obj → index map (cached on the pdf object).
    cache_attr = "_pdftagvalicate_page_index"
    if not hasattr(pdf, cache_attr):
        index_map: dict[tuple, int] = {}
        for i, page in enumerate(pdf.pages):
            key = getattr(page.obj, "objgen", None)
            if key and key != (0, 0):
                index_map[key] = i
        object.__setattr__(pdf, cache_attr, index_map)  # type: ignore[arg-type]
    page_index_map: dict[tuple, int] = getattr(pdf, cache_attr)

    def _resolve_pg(pg_obj) -> Optional[int]:
        if pg_obj is None:
            return None
        key = getattr(pg_obj, "objgen", (0, 0))
        return page_index_map.get(key)

    # 1. Direct /Pg on the element.
    direct = _resolve_pg(struct_elem.get(Name.Pg))
    if direct is not None:
        return direct

    # 2. First MCR/OBJR descendant's /Pg  (BFS, cycle-guarded).
    queue = list(get_kids(struct_elem))
    seen: set = set()
    while queue:
        kid = queue.pop(0)
        if not isinstance(kid, Dictionary):
            continue
        kid_key = object_key(kid)
        if kid_key in seen:
            continue
        seen.add(kid_key)
        pg = kid.get(Name.Pg)
        if pg is not None:
            idx = _resolve_pg(pg)
            if idx is not None:
                return idx
        queue.extend(get_kids(kid))

    return None


def iter_font_resources(pdf: pikepdf.Pdf) -> Iterator[Dictionary]:
    """Yield every font dictionary reachable from any page's resources.

    Walks ``/Resources/Font`` on each page (falling back to inherited
    resources via pikepdf's transparent dereferencing).  Deduplicates by
    indirect-object identity so shared font dicts aren't reported twice.

    Used by: check 31-001 (all fonts embedded).
    """
    seen_keys: set = set()
    for page in pdf.pages:
        resources = page.obj.get(Name.Resources)
        if resources is None:
            continue
        font_dict = resources.get(Name.Font)
        if not isinstance(font_dict, Dictionary):
            continue
        for key in font_dict.keys():
            font = font_dict[key]
            if not isinstance(font, Dictionary):
                continue
            fkey = object_key(font)
            if fkey in seen_keys:
                continue
            seen_keys.add(fkey)
            yield font


def append_kid(parent: Dictionary, new_kid: Object) -> None:
    """Appends new_kid to parent's /K, upgrading a single value to an array
    as needed (mirrors LinkNestingRepair.AppendKid)."""
    k = parent.get(Name.K)
    if isinstance(k, Array):
        k.append(new_kid)
        return
    if k is not None:
        parent[Name.K] = Array([k, new_kid])
        return
    parent[Name.K] = new_kid
