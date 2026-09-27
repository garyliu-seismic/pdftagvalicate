from pikepdf import Dictionary, Name

from pdftagvalicate import th_scope_check, th_scope_repair


def _cell(pdf, role, parent):
    return pdf.make_indirect(Dictionary(Type=Name.StructElem, S=role, P=parent))


def _table_with_unscoped_th(pdf, doc_elem):
    table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
    thead = _cell(pdf, Name.THead, table)
    tr = _cell(pdf, Name.TR, thead)
    th = _cell(pdf, Name.TH, tr)
    tr[Name.K] = th
    thead[Name.K] = tr
    table[Name.K] = thead
    doc_elem[Name.K] = table
    return th


def test_reports_th_missing_scope(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _table_with_unscoped_th(pdf, doc_elem)

    report = th_scope_check.check(pdf)

    assert report.issues == 1


def test_clean_after_fix(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _table_with_unscoped_th(pdf, doc_elem)

    th_scope_repair.fix(pdf)
    report = th_scope_check.check(pdf)

    assert report.issues == 0


def test_skips_untagged(blank_pdf):
    report = th_scope_check.check(blank_pdf)
    assert report.issues == 0
    assert "not tagged" in report.detail
