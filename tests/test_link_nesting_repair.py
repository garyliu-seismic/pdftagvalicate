import pikepdf
from pdftagvalicate import link_nesting_repair
from pikepdf import Array, Dictionary, Name


def _add_link_annot(pdf, page_obj):
    annot = pdf.make_indirect(
        Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=Array([0, 0, 10, 10]))
    )
    annots = page_obj.get(Name.Annots)
    if annots is None:
        page_obj[Name.Annots] = Array([annot])
    else:
        annots.append(annot)
    return annot


def test_wraps_orphaned_link_annotation(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    page_obj = pdf.pages[0].obj
    annot = _add_link_annot(pdf, page_obj)

    report = link_nesting_repair.fix(pdf)

    assert report.fixed == 1
    assert Name.StructParent in annot
    nums = struct_root[Name.ParentTree][Name.Nums]
    assert len(nums) == 2
    link_elem = nums[1]
    assert link_elem[Name.S] == Name.Link
    assert link_elem[Name.K][Name.Obj].objgen == annot.objgen


def test_already_tagged_link_is_left_alone(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    page_obj = pdf.pages[0].obj
    annot = _add_link_annot(pdf, page_obj)

    # Pre-tag it exactly like the repair itself would.
    first = link_nesting_repair.fix(pdf)
    assert first.fixed == 1

    second = link_nesting_repair.fix(pdf)
    assert second.fixed == 0


def test_creates_struct_tree_for_fully_untagged_pdf(blank_pdf):
    page_obj = blank_pdf.pages[0].obj
    _add_link_annot(blank_pdf, page_obj)

    report = link_nesting_repair.fix(blank_pdf)

    assert report.fixed == 1
    assert blank_pdf.Root.get(Name.StructTreeRoot) is not None


def test_parent_tree_next_key_not_stale(tagged_pdf):
    """ParentTreeNextKey hint must be honoured as a *floor*, not a ceiling.
    If the hint is stale (lower than the actual max key), the repair must
    still produce a key higher than any existing entry."""
    pdf, struct_root, doc_elem = tagged_pdf
    page_obj = pdf.pages[0].obj

    # Manually insert a ParentTree entry at key 99 to simulate a stale hint.
    nums = struct_root[Name.ParentTree][Name.Nums]
    nums.append(pikepdf.Object.parse(b"99"))
    nums.append(doc_elem)  # value doesn't matter for this test
    struct_root[Name.ParentTreeNextKey] = 5  # intentionally stale

    _add_link_annot(pdf, page_obj)
    report = link_nesting_repair.fix(pdf)

    assert report.fixed == 1
    # The new entry must be at key 100 (max(5, 99+1)), not at stale key 5.
    new_nums = struct_root[Name.ParentTree][Name.Nums]
    keys = [int(new_nums[i]) for i in range(0, len(new_nums), 2)]
    assert 100 in keys
    assert keys.count(100) == 1  # no collision


def test_kids_parent_tree_refused_gracefully(tagged_pdf):
    """A /Kids-shaped ParentTree must not be corrupted; repair should report
    a clear error and fix 0 items."""
    pdf, struct_root, doc_elem = tagged_pdf
    page_obj = pdf.pages[0].obj
    _add_link_annot(pdf, page_obj)

    # Replace the flat Nums-based ParentTree with a Kids-based one.
    leaf = Dictionary(Nums=Array([]))
    struct_root[Name.ParentTree] = Dictionary(Kids=Array([leaf]))

    report = link_nesting_repair.fix(pdf)

    assert report.fixed == 0
    assert "not yet supported" in report.detail or "unsupported" in report.detail.lower()


def test_cycle_in_struct_tree_does_not_recurse(tagged_pdf):
    """A cyclic struct tree must not cause RecursionError in _collect_tagged."""
    pdf, struct_root, doc_elem = tagged_pdf
    page_obj = pdf.pages[0].obj
    _add_link_annot(pdf, page_obj)

    # Create a cycle: doc_elem -> cycle_child -> doc_elem
    cycle_child = pdf.make_indirect(
        Dictionary(Type=Name.StructElem, S=Name.Div, P=doc_elem)
    )
    cycle_child[Name.K] = doc_elem  # cycle back
    doc_elem[Name.K] = cycle_child

    # Must complete without RecursionError.
    report = link_nesting_repair.fix(pdf)
    assert report.fixed == 1
