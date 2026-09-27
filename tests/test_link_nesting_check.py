from pikepdf import Array, Dictionary, Name

from pdftagvalicate import link_nesting_check, link_nesting_repair


def _add_link_annot(pdf, page_obj):
    annot = pdf.make_indirect(
        Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=Array([0, 0, 10, 10]))
    )
    annots = page_obj.get(Name.Annots)
    if annots is None:
        page_obj[Name.Annots] = Array([annot])
    else:
        annots.append(annot)
    return annot


def test_reports_orphaned_link(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _add_link_annot(pdf, pdf.pages[0].obj)

    report = link_nesting_check.check(pdf)

    assert report.issues == 1


def test_clean_after_fix(tagged_pdf):
    pdf, struct_root, doc_elem = tagged_pdf
    _add_link_annot(pdf, pdf.pages[0].obj)

    link_nesting_repair.fix(pdf)
    report = link_nesting_check.check(pdf)

    assert report.issues == 0


def test_reports_orphaned_link_when_untagged(blank_pdf):
    _add_link_annot(blank_pdf, blank_pdf.pages[0].obj)

    report = link_nesting_check.check(blank_pdf)

    assert report.issues == 1
