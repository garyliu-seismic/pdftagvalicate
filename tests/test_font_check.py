from pikepdf import Dictionary, Name

from pdftagvalicate import font_check


def _page_fonts(pdf):
    page_obj = pdf.pages[0].obj
    resources = page_obj[Name.Resources]
    fonts = resources.get(Name.Font)
    if fonts is None:
        fonts = Dictionary()
        resources[Name.Font] = fonts
    return fonts


def test_unembedded_font_is_reported(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
    _page_fonts(pdf)[Name.F1] = font

    report = font_check.check(pdf)

    assert report.issues >= 1
    assert "unembedded" in report.detail


def test_type3_font_is_reported(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type3))
    _page_fonts(pdf)[Name.F1] = font

    report = font_check.check(pdf)

    assert report.issues == 1
    assert "Type3" in report.detail


def test_missing_tounicode_is_reported(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    desc = pdf.make_indirect(Dictionary(FontFile2=pdf.make_stream(b"font data")))
    font = pdf.make_indirect(
        Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica, FontDescriptor=desc)
    )
    _page_fonts(pdf)[Name.F1] = font

    report = font_check.check(pdf)

    assert report.issues == 1
    assert "ToUnicode" in report.detail


def test_clean_font_reports_no_issues(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    desc = pdf.make_indirect(Dictionary(FontFile2=pdf.make_stream(b"font data")))
    cmap = pdf.make_indirect(pdf.make_stream(b"cmap data"))
    font = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type1,
            BaseFont=Name.Helvetica,
            FontDescriptor=desc,
            ToUnicode=cmap,
        )
    )
    _page_fonts(pdf)[Name.F1] = font

    report = font_check.check(pdf)

    assert report.issues == 0
