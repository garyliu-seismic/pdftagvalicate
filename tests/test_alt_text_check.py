from pikepdf import Dictionary, Name

from pdftagvalicate import alt_text_check


def _add_figure(pdf, doc_elem, **extra):
    fig = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem, **extra))
    doc_elem[Name.K] = fig
    return fig


def test_reports_figure_without_alt(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _add_figure(pdf, doc_elem)

    report = alt_text_check.check(pdf)

    assert report.issues == 1


def test_figure_with_alt_is_clean(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _add_figure(pdf, doc_elem, Alt="A bar chart")

    report = alt_text_check.check(pdf)

    assert report.issues == 0


def test_empty_alt_counts_as_missing(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _add_figure(pdf, doc_elem, Alt="")

    report = alt_text_check.check(pdf)

    assert report.issues == 1


def test_skips_untagged_document(blank_pdf):
    report = alt_text_check.check(blank_pdf)
    assert report.issues == 0
    assert "not tagged" in report.detail


def test_handles_cyclic_struct_tree(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    fig = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem))
    doc_elem[Name.K] = fig
    fig[Name.K] = doc_elem  # cycle back to the document

    report = alt_text_check.check(pdf)

    assert report.issues == 1
