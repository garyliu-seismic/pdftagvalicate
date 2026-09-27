from pikepdf import Name

from pdftagvalicate import lang_repair


def test_sets_lang_from_xmp(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["dc:language"] = "en-US"

    report = lang_repair.fix(pdf)

    assert report.fixed == 1
    assert pdf.Root[Name.Lang] == "en-US"


def test_cannot_determine_without_source(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    report = lang_repair.fix(pdf)

    assert report.fixed == 0
    assert "Cannot determine" in report.detail


def test_explicit_lang_value(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf

    report = lang_repair.fix(pdf, lang_value="fr-FR")

    assert report.fixed == 1
    assert pdf.Root[Name.Lang] == "fr-FR"


def test_already_set_is_left_alone(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    pdf.Root[Name.Lang] = "de-DE"

    report = lang_repair.fix(pdf)

    assert report.fixed == 0
