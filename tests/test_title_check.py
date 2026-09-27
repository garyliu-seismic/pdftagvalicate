from pikepdf import Dictionary, Name

from pdftagvalicate import title_check, title_repair


def test_reports_missing_title(blank_pdf):
    report = title_check.check(blank_pdf)
    assert report.issues == 1


def test_reports_title_missing_but_info_present(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.trailer[Name.Info] = Dictionary(Title="My Document")

    report = title_check.check(pdf)

    assert report.issues == 1
    assert "back-fill" in report.detail


def test_clean_after_fix(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.trailer[Name.Info] = Dictionary(Title="My Document")

    title_repair.fix(pdf)
    report = title_check.check(pdf)

    assert report.issues == 0
