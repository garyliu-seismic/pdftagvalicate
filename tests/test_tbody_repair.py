from pdftagvalicate import tbody_repair
from pikepdf import Dictionary, Name


def _table_chain(pdf, parent):
    """Builds parent -> Table -> TBody -> TR -> TD(with content) and links it
    into parent's /K. Returns (table, td)."""
    content = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
    td = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD, K=content))
    content[Name.P] = td
    tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td))
    td[Name.P] = tr
    tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=tr))
    tr[Name.P] = tbody
    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=parent))
    tbody[Name.P] = table
    parent[Name.K] = table
    return table, content


def test_dissolves_fake_table_chain(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    table, content = _table_chain(pdf, doc_elem)

    report = tbody_repair.fix(pdf)

    assert report.fixed == 1
    # doc_elem's /K should now point directly at the cell's content, not the table.
    assert doc_elem[Name.K].objgen == content.objgen
    assert content[Name.P].objgen == doc_elem.objgen


def test_leaves_real_table_with_thead_alone(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    table, content = _table_chain(pdf, doc_elem)
    thead = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.THead, P=table))
    from pikepdf import Array

    table[Name.K] = Array([thead, table[Name.K]])

    report = tbody_repair.fix(pdf)

    assert report.fixed == 0
    assert doc_elem[Name.K].objgen == table.objgen


def test_skips_untagged_document(blank_pdf):
    report = tbody_repair.fix(blank_pdf)
    assert report.fixed == 0
    assert "not tagged" in report.detail


# ---------------------------------------------------------------------------
# P1 extension: multi-row fake tables and wrapper elements
# ---------------------------------------------------------------------------

def _multi_row_chain(pdf, parent, n_rows=3):
    """Table -> TBody -> [TR -> TD(with content)] x n_rows."""
    rows = []
    contents = []
    for _ in range(n_rows):
        content = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
        td = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD, K=content))
        content[Name.P] = td
        tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td))
        td[Name.P] = tr
        rows.append(tr)
        contents.append(content)
    from pikepdf import Array
    tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=Array(rows)))
    for tr in rows:
        tr[Name.P] = tbody
    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=parent))
    tbody[Name.P] = table
    parent[Name.K] = table
    return table, contents


def test_dissolves_multi_row_fake_table(tagged_pdf):
    """A fake table with 3 single-cell rows should be dissolved."""
    pdf, struct_root, doc_elem = tagged_pdf
    table, contents = _multi_row_chain(pdf, doc_elem, n_rows=3)

    report = tbody_repair.fix(pdf)

    assert report.fixed == 1
    # doc_elem's /K should now be an array of the 3 content elements.
    from pikepdf import Array
    k = doc_elem[Name.K]
    assert isinstance(k, Array)
    assert len(k) == 3
    for content in contents:
        assert content[Name.P].objgen == doc_elem.objgen


def test_does_not_dissolve_multi_cell_row(tagged_pdf):
    """A row with 2 cells is a real table — must not be touched."""
    pdf, struct_root, doc_elem = tagged_pdf
    from pikepdf import Array
    td1 = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD))
    td2 = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD))
    tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=Array([td1, td2])))
    tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=tr))
    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem))
    tbody[Name.P] = table
    doc_elem[Name.K] = table

    report = tbody_repair.fix(pdf)
    assert report.fixed == 0
    assert doc_elem[Name.K].objgen == table.objgen


def test_dissolves_fake_table_behind_div_wrapper(tagged_pdf):
    """TBody hidden behind a Div wrapper inside the Table should still be found."""
    pdf, struct_root, doc_elem = tagged_pdf
    content = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
    td = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD, K=content))
    content[Name.P] = td
    tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td))
    td[Name.P] = tr
    tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=tr))
    tr[Name.P] = tbody
    # Wrap TBody in a Div.
    wrapper = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Div, K=tbody))
    tbody[Name.P] = wrapper
    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=wrapper, P=doc_elem))
    wrapper[Name.P] = table
    doc_elem[Name.K] = table

    report = tbody_repair.fix(pdf)
    assert report.fixed == 1
    assert content[Name.P].objgen == doc_elem.objgen
