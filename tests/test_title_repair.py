import pikepdf
from pikepdf import Dictionary, Name

from pdftagvalicate import title_repair


def test_backfills_title_from_info(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.trailer[Name.Info] = Dictionary(Title="My Document")

    report = title_repair.fix(pdf)

    assert report.fixed == 1
    with pdf.open_metadata() as meta:
        assert meta["dc:title"] == "My Document"


def test_no_title_cannot_auto_generate(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    report = title_repair.fix(pdf)

    assert report.fixed == 0
    assert "cannot auto-generate" in report.detail


def test_is_idempotent(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.trailer[Name.Info] = Dictionary(Title="My Document")

    first = title_repair.fix(pdf)
    second = title_repair.fix(pdf)

    assert first.fixed == 1
    assert second.fixed == 0
