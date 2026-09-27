from pikepdf import Dictionary, Name

from pdftagvalicate import tbody_check, tbody_repair


def _table_chain(pdf, parent):
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
    return table


def test_reports_fake_table(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _table_chain(pdf, doc_elem)

    report = tbody_check.check(pdf)

    assert report.issues == 1


def test_clean_after_fix(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _table_chain(pdf, doc_elem)

    tbody_repair.fix(pdf)
    report = tbody_check.check(pdf)

    assert report.issues == 0


def test_skips_untagged(blank_pdf):
    report = tbody_check.check(blank_pdf)
    assert report.issues == 0
    assert "not tagged" in report.detail
