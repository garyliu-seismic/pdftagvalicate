from pikepdf import Name

from pdftagvalicate import lang_check, lang_repair


def test_reports_missing_lang(blank_pdf):
    report = lang_check.check(blank_pdf)
    assert report.issues == 1


def test_clean_when_lang_set(blank_pdf):
    blank_pdf.Root[Name.Lang] = "en-US"
    report = lang_check.check(blank_pdf)
    assert report.issues == 0


def test_clean_after_fix(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    lang_repair.fix(pdf, lang_value="fr-FR")
    report = lang_check.check(pdf)
    assert report.issues == 0


def test_reports_backfill_source_from_xmp(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["dc:language"] = ["en-US"]

    report = lang_check.check(pdf)

    assert report.issues == 1
    assert "back-fill" in report.detail
