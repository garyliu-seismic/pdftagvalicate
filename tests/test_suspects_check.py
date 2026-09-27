from pikepdf import Name

from pdftagvalicate import suspects_check


def test_reports_suspects_true(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.Root[Name.MarkInfo][Name.Suspects] = True

    report = suspects_check.check(pdf)

    assert report.issues == 1


def test_no_suspects_flag_is_clean(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    report = suspects_check.check(pdf)

    assert report.issues == 0
