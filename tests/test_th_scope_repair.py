from pdftagvalicate import th_scope_repair
from pikepdf import Array, Dictionary, Name


def _cell(pdf, role, parent):
    d = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=role, P=parent))
    return d


def test_adds_column_scope_in_thead(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    thead = _cell(pdf, Name.THead, table)
    tr = _cell(pdf, Name.TR, thead)
    th = _cell(pdf, Name.TH, tr)
    tr[Name.K] = th
    thead[Name.K] = tr
    table[Name.K] = thead
    doc_elem[Name.K] = table

    report = th_scope_repair.fix(pdf)

    assert report.fixed == 1
    assert th[Name.A][Name.Scope] == Name.Column


def test_adds_row_scope_for_th_alongside_td(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    tbody = _cell(pdf, Name.TBody, table)
    tr = _cell(pdf, Name.TR, tbody)
    th = _cell(pdf, Name.TH, tr)
    td = _cell(pdf, Name.TD, tr)
    tr[Name.K] = Array([th, td])
    tbody[Name.K] = tr
    table[Name.K] = tbody
    doc_elem[Name.K] = table

    report = th_scope_repair.fix(pdf)

    assert report.fixed == 1
    assert th[Name.A][Name.Scope] == Name.Row


def test_skips_th_that_already_has_scope(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    thead = _cell(pdf, Name.THead, table)
    tr = _cell(pdf, Name.TR, thead)
    th = _cell(pdf, Name.TH, tr)
    th[Name.A] = Dictionary(O=Name.Table, Scope=Name.Column)
    tr[Name.K] = th
    thead[Name.K] = tr
    table[Name.K] = thead
    doc_elem[Name.K] = table

    report = th_scope_repair.fix(pdf)

    assert report.fixed == 0


# ---------------------------------------------------------------------------
# P1 extension: wrapper elements between Table and THead/TBody/TR
# ---------------------------------------------------------------------------

def test_adds_scope_through_div_wrapper_in_thead(tagged_pdf):
    """THead hidden behind a Div inside the Table should still be walked."""
    pdf, struct_root, doc_elem = tagged_pdf

    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    thead = _cell(pdf, Name.THead, table)
    tr    = _cell(pdf, Name.TR, thead)
    th    = _cell(pdf, Name.TH, tr)
    tr[Name.K] = th
    thead[Name.K] = tr
    # Wrap THead in a Div.
    wrapper = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Div, P=table))
    wrapper[Name.K] = thead
    table[Name.K] = wrapper
    doc_elem[Name.K] = table

    report = th_scope_repair.fix(pdf)

    assert report.fixed == 1
    assert th[Name.A][Name.Scope] == Name.Column


def test_adds_scope_through_div_wrapper_in_tbody(tagged_pdf):
    """TR hidden behind a Div inside TBody should still be walked."""
    pdf, struct_root, doc_elem = tagged_pdf

    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    tbody = _cell(pdf, Name.TBody, table)
    tr    = _cell(pdf, Name.TR, tbody)
    th    = _cell(pdf, Name.TH, tr)
    td    = _cell(pdf, Name.TD, tr)
    tr[Name.K] = Array([th, td])
    # Wrap TR in a Div inside TBody.
    wrapper = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Div, P=tbody))
    wrapper[Name.K] = tr
    tbody[Name.K] = wrapper
    table[Name.K] = tbody
    doc_elem[Name.K] = table

    report = th_scope_repair.fix(pdf)

    assert report.fixed == 1
    assert th[Name.A][Name.Scope] == Name.Row
