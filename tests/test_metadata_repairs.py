from pdftagvalicate import metadata_repairs
from pikepdf import Array, Dictionary, Name
import pikepdf


def _add_struct_tree_root(pdf):
    """Attach a minimal StructTreeRoot so fix_mark_info will act."""
    doc_elem = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
    struct_root = pdf.make_indirect(
        Dictionary(Type=Name.StructTreeRoot, K=doc_elem, ParentTree=Dictionary(Nums=Array([])))
    )
    doc_elem[Name.P] = struct_root
    pdf.Root[Name.StructTreeRoot] = struct_root
    return struct_root


def test_fix_mark_info_sets_marked_true(blank_pdf):
    _add_struct_tree_root(blank_pdf)
    report = metadata_repairs.fix_mark_info(blank_pdf)
    assert report.fixed == 1
    assert blank_pdf.Root[Name.MarkInfo][Name.Marked] is True


def test_fix_mark_info_skips_when_no_struct_tree(blank_pdf):
    """Setting Marked=true on an unstructured PDF would be a false claim."""
    report = metadata_repairs.fix_mark_info(blank_pdf)
    assert report.fixed == 0
    assert "StructTreeRoot" in report.detail


def test_fix_mark_info_is_idempotent(blank_pdf):
    _add_struct_tree_root(blank_pdf)
    metadata_repairs.fix_mark_info(blank_pdf)
    second = metadata_repairs.fix_mark_info(blank_pdf)
    assert second.fixed == 0


def test_fix_display_doc_title_sets_true(blank_pdf):
    report = metadata_repairs.fix_display_doc_title(blank_pdf)
    assert report.fixed == 1
    assert blank_pdf.Root[Name.ViewerPreferences][Name.DisplayDocTitle] is True


def test_fix_display_doc_title_is_idempotent(blank_pdf):
    metadata_repairs.fix_display_doc_title(blank_pdf)
    second = metadata_repairs.fix_display_doc_title(blank_pdf)
    assert second.fixed == 0


def test_fix_pdf_ua_identifier_sets_xmp(blank_pdf):
    report = metadata_repairs.fix_pdf_ua_identifier(blank_pdf)
    assert report.fixed == 1
    with blank_pdf.open_metadata() as meta:
        assert meta["pdfuaid:part"] == "1"


def test_fix_pdf_ua_identifier_is_idempotent(blank_pdf):
    metadata_repairs.fix_pdf_ua_identifier(blank_pdf)
    second = metadata_repairs.fix_pdf_ua_identifier(blank_pdf)
    assert second.fixed == 0
