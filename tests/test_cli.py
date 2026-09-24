import json

import pikepdf
from pikepdf import Array, Dictionary, Name

from pdftagvalicate.cli import main


def _write_blank_pdf(path):
    pdf = pikepdf.new()
    page = pdf.make_indirect(Dictionary(Type=Name.Page, MediaBox=Array([0, 0, 612, 792]), Resources=Dictionary()))
    pdf.pages.append(pikepdf.Page(page))
    pdf.save(path)
    pdf.close()


def test_dry_run_reports_fixes_without_writing(tmp_path, capsys):
    src = tmp_path / "in.pdf"
    _write_blank_pdf(src)

    exit_code = main([str(src), "--dry-run", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    # fix_mark_info skips when there is no StructTreeRoot; only pdfuaid:part
    # and DisplayDocTitle are repaired on a plain untagged PDF.
    assert payload["total_fixed"] == 2
    assert not (tmp_path / "out.pdf").exists()


def test_writes_repaired_output(tmp_path, capsys):
    src = tmp_path / "in.pdf"
    dst = tmp_path / "out.pdf"
    _write_blank_pdf(src)

    exit_code = main([str(src), str(dst), "--json"])

    assert exit_code == 1
    assert dst.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_fixed"] == 2


def test_missing_input_file_errors(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.pdf"

    exit_code = main([str(missing), "--dry-run", "--json"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload


def test_output_required_unless_dry_run(tmp_path):
    src = tmp_path / "in.pdf"
    _write_blank_pdf(src)

    try:
        main([str(src)])
        assert False, "expected SystemExit"
    except SystemExit as ex:
        assert ex.code == 2


def test_in_place_repair(tmp_path, capsys):
    """input == output should work (allow_overwriting_input)."""
    src = tmp_path / "inplace.pdf"
    _write_blank_pdf(src)
    mtime_before = src.stat().st_mtime

    exit_code = main([str(src), str(src), "--json"])

    assert exit_code == 1
    assert src.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_fixed"] >= 1


# ---------------------------------------------------------------------------
# P2 optional: combined single-pass struct-tree walk (--all)
# ---------------------------------------------------------------------------

def _write_tagged_pdf_with_issues(path):
    """PDF with: orphaned Link annotation + TH without /Scope + fake TBody chain."""
    pdf = pikepdf.new()
    page = pdf.make_indirect(
        Dictionary(Type=Name.Page, MediaBox=Array([0, 0, 612, 792]), Resources=Dictionary())
    )
    pdf.pages.append(pikepdf.Page(page))

    # Struct tree: Document > [Table(fake), TH-row table]
    doc_elem = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
    struct_root = pdf.make_indirect(
        Dictionary(Type=Name.StructTreeRoot, K=doc_elem,
                   ParentTree=Dictionary(Nums=Array([])))
    )
    doc_elem[Name.P] = struct_root
    pdf.Root[Name.StructTreeRoot] = struct_root
    pdf.Root[Name.MarkInfo] = Dictionary(Marked=True)

    # 1. Fake table (TBody -> TR -> TD with content)
    content = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
    td      = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD, K=content))
    content[Name.P] = td
    tr      = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td))
    td[Name.P] = tr
    tbody   = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=tr))
    tr[Name.P] = tbody
    fake_table = pdf.make_indirect(
        Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem)
    )
    tbody[Name.P] = fake_table

    # 2. Real table with TH missing /Scope
    th    = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TH))
    tr2   = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=th))
    th[Name.P] = tr2
    thead = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.THead, K=tr2))
    tr2[Name.P] = thead
    real_table = pdf.make_indirect(
        Dictionary(Type=Name.StructElem, S=Name.Table, K=thead, P=doc_elem)
    )
    thead[Name.P] = real_table

    doc_elem[Name.K] = Array([fake_table, real_table])

    # 3. Orphaned Link annotation
    annot = pdf.make_indirect(
        Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=Array([0, 0, 10, 10]))
    )
    page[Name.Annots] = Array([annot])

    pdf.save(path)
    pdf.close()


def test_all_repairs_combined_single_pass(tmp_path, capsys):
    """--all: combined walk fixes tbody + th-scope + link-nesting in one pass."""
    src = tmp_path / "issues.pdf"
    dst = tmp_path / "fixed.pdf"
    _write_tagged_pdf_with_issues(src)

    exit_code = main([str(src), str(dst), "--all", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    reports = {r["name"]: r for r in payload["reports"]}

    # Each of the three struct-tree repairs should have fired.
    assert reports["Fake TBody wrappers"]["fixed"] == 1
    assert reports["TH /Scope attribute"]["fixed"] == 1
    assert reports["Link annotation nesting"]["fixed"] == 1

    # Total must equal the sum of the three.
    assert payload["total_fixed"] >= 3
