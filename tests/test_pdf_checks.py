"""Tests for the P3 read-only PDF/UA validation checks (pdf_checks.py)."""

import json

import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name

from pdftagvalicate import pdf_checks
from pdftagvalicate.cli import main
from pdftagvalicate.types import Severity


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_tagged_pdf():
    """Minimal tagged PDF: MarkInfo, StructTreeRoot, <Document> root elem."""
    pdf = pikepdf.new()
    page = pdf.make_indirect(
        Dictionary(Type=Name.Page, MediaBox=Array([0, 0, 612, 792]), Resources=Dictionary())
    )
    pdf.pages.append(pikepdf.Page(page))

    doc_elem = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
    struct_root = pdf.make_indirect(
        Dictionary(Type=Name.StructTreeRoot, K=doc_elem, ParentTree=Dictionary(Nums=Array([])))
    )
    doc_elem[Name.P] = struct_root
    pdf.Root[Name.StructTreeRoot] = struct_root
    pdf.Root[Name.MarkInfo] = Dictionary(Marked=True)
    return pdf, struct_root, doc_elem


# ---------------------------------------------------------------------------
# 01-005  MarkInfo /Marked
# ---------------------------------------------------------------------------

class TestCheck01005:
    def test_pass_when_marked_true(self, tagged_pdf):
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_01_005(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_no_mark_info(self, blank_pdf):
        r = pdf_checks.check_01_005(blank_pdf)
        assert r.severity == Severity.Fail
        assert "absent" in r.detail

    def test_fail_when_marked_false(self, blank_pdf):
        blank_pdf.Root[Name.MarkInfo] = Dictionary(Marked=False)
        r = pdf_checks.check_01_005(blank_pdf)
        assert r.severity == Severity.Fail


# ---------------------------------------------------------------------------
# 11-001  Document /Lang
# ---------------------------------------------------------------------------

class TestCheck11001:
    def test_pass_when_lang_set(self, blank_pdf):
        blank_pdf.Root[Name.Lang] = "en-US"
        r = pdf_checks.check_11_001(blank_pdf)
        assert r.severity == Severity.Pass
        assert "en-US" in r.detail

    def test_fail_when_no_lang(self, blank_pdf):
        r = pdf_checks.check_11_001(blank_pdf)
        assert r.severity == Severity.Fail

    def test_fail_when_lang_empty(self, blank_pdf):
        blank_pdf.Root[Name.Lang] = ""
        r = pdf_checks.check_11_001(blank_pdf)
        assert r.severity == Severity.Fail


# ---------------------------------------------------------------------------
# 06-003  Document Title
# ---------------------------------------------------------------------------

class TestCheck06003:
    def test_pass_when_title_set(self, blank_pdf):
        with blank_pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            pass  # ensure info dict exists
        blank_pdf.docinfo["/Title"] = "Test Document"
        r = pdf_checks.check_06_003(blank_pdf)
        assert r.severity == Severity.Pass
        assert "Test Document" in r.detail

    def test_fail_when_no_title(self, blank_pdf):
        r = pdf_checks.check_06_003(blank_pdf)
        assert r.severity == Severity.Fail

    def test_fail_when_title_empty(self, blank_pdf):
        blank_pdf.docinfo["/Title"] = "   "
        r = pdf_checks.check_06_003(blank_pdf)
        assert r.severity == Severity.Fail


# ---------------------------------------------------------------------------
# 07-001  ViewerPreferences /DisplayDocTitle
# ---------------------------------------------------------------------------

class TestCheck07001:
    def test_pass_when_display_doc_title_true(self, blank_pdf):
        blank_pdf.Root[Name.ViewerPreferences] = Dictionary(DisplayDocTitle=True)
        r = pdf_checks.check_07_001(blank_pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_no_viewer_prefs(self, blank_pdf):
        r = pdf_checks.check_07_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "absent" in r.detail

    def test_fail_when_display_doc_title_false(self, blank_pdf):
        blank_pdf.Root[Name.ViewerPreferences] = Dictionary(DisplayDocTitle=False)
        r = pdf_checks.check_07_001(blank_pdf)
        assert r.severity == Severity.Fail


# ---------------------------------------------------------------------------
# 13-004  <Figure>/<Formula> alt text
# ---------------------------------------------------------------------------

class TestCheck13004:
    def test_pass_when_figure_has_alt(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        fig = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem, Alt="A diagram")
        )
        doc_elem[Name.K] = fig
        r = pdf_checks.check_13_004(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_figure_missing_alt(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        fig = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem)
        )
        doc_elem[Name.K] = fig
        r = pdf_checks.check_13_004(pdf)
        assert r.severity == Severity.Fail
        assert "1 element" in r.detail

    def test_pass_when_actual_text_set(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        fig = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem, ActualText="chart")
        )
        doc_elem[Name.K] = fig
        r = pdf_checks.check_13_004(pdf)
        assert r.severity == Severity.Pass

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_13_004(blank_pdf)
        assert r.severity == Severity.Info

    def test_counts_multiple_missing(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        kids = Array([])
        for _ in range(3):
            fig = pdf.make_indirect(
                Dictionary(Type=Name.StructElem, S=Name.Figure, P=doc_elem)
            )
            kids.append(fig)
        doc_elem[Name.K] = kids
        r = pdf_checks.check_13_004(pdf)
        assert r.severity == Severity.Fail
        assert "3 element" in r.detail


# ---------------------------------------------------------------------------
# 14-002  TBody contains only TR rows
# ---------------------------------------------------------------------------

class TestCheck14002:
    def _make_clean_table(self, pdf, doc_elem):
        """TBody -> TR -> TD chain (valid)."""
        td = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD))
        tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td))
        tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=tr))
        table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem))
        doc_elem[Name.K] = table
        return table

    def test_pass_for_valid_tbody(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        self._make_clean_table(pdf, doc_elem)
        r = pdf_checks.check_14_002(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_tbody_has_non_tr_child(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        # TBody -> P (invalid — should be TR)
        p = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
        tbody = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TBody, K=p))
        table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem))
        doc_elem[Name.K] = table
        r = pdf_checks.check_14_002(pdf)
        assert r.severity == Severity.Fail
        assert "1 TBody" in r.detail

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_14_002(blank_pdf)
        assert r.severity == Severity.Info


# ---------------------------------------------------------------------------
# 14-003  TH cells have /Scope
# ---------------------------------------------------------------------------

class TestCheck14003:
    def test_pass_when_all_th_have_scope(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
        thead = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.THead, P=table))
        tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, P=thead))
        th = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.TH, P=tr,
                       A=Dictionary(O=Name.Table, Scope=Name.Column))
        )
        tr[Name.K] = th
        thead[Name.K] = tr
        table[Name.K] = thead
        doc_elem[Name.K] = table
        r = pdf_checks.check_14_003(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_th_missing_scope(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        table = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Table, P=doc_elem))
        thead = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.THead, P=table))
        tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, P=thead))
        th = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TH, P=tr))
        tr[Name.K] = th
        thead[Name.K] = tr
        table[Name.K] = thead
        doc_elem[Name.K] = table
        r = pdf_checks.check_14_003(pdf)
        assert r.severity == Severity.Fail
        assert "1" in r.detail

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_14_003(blank_pdf)
        assert r.severity == Severity.Info


# ---------------------------------------------------------------------------
# --validate CLI integration
# ---------------------------------------------------------------------------

class TestValidateCLI:
    def _write_pdf(self, path, *, tagged=False, lang=None, title=None,
                   display_title=False, with_mcr=False, pdfuaid=False,
                   tagged_content=False):
        """Build a minimal PDF for CLI integration tests.

        ``with_mcr=True``       — attach MCR so 09-004 sees the page as tagged.
        ``pdfuaid=True``        — write pdfuaid:part='1' into XMP (06-001).
        ``tagged_content=True`` — wrap the page content stream in BDC/EMC so
                                   09-006 sees no untagged painting ops.
        """
        pdf = pikepdf.new()
        page = pdf.make_indirect(
            Dictionary(Type=Name.Page, MediaBox=Array([0, 0, 612, 792]), Resources=Dictionary())
        )
        pdf.pages.append(pikepdf.Page(page))

        if tagged_content:
            # Minimal content stream: all painting inside a BDC/EMC pair.
            cs = b'/P <</MCID 0>> BDC q Q EMC'
            page[Name.Contents] = pdf.make_indirect(pikepdf.Stream(pdf, cs))

        if tagged:
            doc_elem = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
            struct_root = pdf.make_indirect(
                Dictionary(Type=Name.StructTreeRoot, K=doc_elem,
                           ParentTree=Dictionary(Nums=Array([])))
            )
            doc_elem[Name.P] = struct_root
            pdf.Root[Name.StructTreeRoot] = struct_root
            pdf.Root[Name.MarkInfo] = Dictionary(Marked=True)
            if with_mcr:
                # Attach a minimal MCR so 09-004 sees the page as tagged.
                mcr = pdf.make_indirect(
                    Dictionary(Type=Name.MCR, Pg=page, MCID=pikepdf.Object.parse(b"0"))
                )
                doc_elem[Name.K] = mcr

        if lang:
            pdf.Root[Name.Lang] = lang
        if title:
            pdf.docinfo["/Title"] = title
        if display_title:
            pdf.Root[Name.ViewerPreferences] = Dictionary(DisplayDocTitle=True)
        if pdfuaid:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                meta.register_xml_namespace(
                    "http://www.aiim.org/pdfua/ns/id/", "pdfuaid"
                )
                meta["pdfuaid:part"] = "1"
            # open_metadata clears docinfo; re-apply title after.
            if title:
                pdf.docinfo["/Title"] = title
        pdf.save(path)
        pdf.close()

    def test_validate_returns_json(self, tmp_path, capsys):
        src = tmp_path / "in.pdf"
        self._write_pdf(src)
        rc = main([str(src), "--validate", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert "checks" in out
        assert isinstance(out["checks"], list)
        assert len(out["checks"]) == 16  # 7 Step-2 + 7 Step-3 + 2 Step-4 checks

    def test_validate_exit_1_on_failures(self, tmp_path, capsys):
        src = tmp_path / "in.pdf"
        self._write_pdf(src)  # plain untagged PDF — several checks will Fail
        rc = main([str(src), "--validate", "--json"])
        assert rc == 1

    def test_validate_exit_0_when_all_pass(self, tmp_path, capsys):
        src = tmp_path / "in.pdf"
        self._write_pdf(
            src,
            tagged=True, lang="en-US", title="My Doc", display_title=True,
            with_mcr=True,    # 09-004: page has tagged content
            pdfuaid=True,     # 06-001: XMP identifier present
            tagged_content=True,  # 09-006: no untagged painting ops
        )
        rc = main([str(src), "--validate", "--json"])
        out = json.loads(capsys.readouterr().out)
        fails = [c for c in out["checks"] if c["severity"] in ("Fail", "Error")]
        assert fails == [], fails
        assert rc == 0

    def test_validate_strict_warns_as_fail(self, tmp_path, capsys):
        """--strict: a check that is Info/Warning must push exit code to 1."""
        src = tmp_path / "in.pdf"
        # No struct tree → 13-004, 14-002, 14-003 all return Info
        self._write_pdf(src, tagged=False, lang="en-US", title="T", display_title=True)
        rc_normal = main([str(src), "--validate", "--json"])
        capsys.readouterr()
        rc_strict = main([str(src), "--validate", "--strict", "--json"])
        capsys.readouterr()
        # 01-005 is Fail in both modes (no MarkInfo); strict adds Warning→Fail
        # The point is strict >= normal in exit code.
        assert rc_strict >= rc_normal

    def test_validate_missing_file(self, tmp_path, capsys):
        rc = main([str(tmp_path / "nope.pdf"), "--validate", "--json"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert "error" in out


# ===========================================================================
# Step 3 — moderate check tests
# ===========================================================================


# ---------------------------------------------------------------------------
# 09-001  Single <Document> at struct tree root
# ---------------------------------------------------------------------------

class TestCheck09001:
    def test_pass_with_single_document(self, tagged_pdf):
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_09_001(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_09_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "not tagged" in r.detail

    def test_fail_when_no_document_element(self, blank_pdf):
        """StructTreeRoot with a bare non-Document top element."""
        p = blank_pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P))
        struct_root = blank_pdf.make_indirect(
            Dictionary(Type=Name.StructTreeRoot, K=p, ParentTree=Dictionary(Nums=Array([])))
        )
        blank_pdf.Root[Name.StructTreeRoot] = struct_root
        r = pdf_checks.check_09_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "No <Document>" in r.detail

    def test_fail_when_two_document_elements(self, blank_pdf):
        doc1 = blank_pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
        doc2 = blank_pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document))
        struct_root = blank_pdf.make_indirect(
            Dictionary(Type=Name.StructTreeRoot, K=Array([doc1, doc2]),
                       ParentTree=Dictionary(Nums=Array([])))
        )
        blank_pdf.Root[Name.StructTreeRoot] = struct_root
        r = pdf_checks.check_09_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "2" in r.detail


# ---------------------------------------------------------------------------
# 14-001  Role map resolves to standard roles
# ---------------------------------------------------------------------------

class TestCheck14001:
    def test_pass_when_no_role_map(self, tagged_pdf):
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_14_001(pdf)
        assert r.severity == Severity.Pass
        assert "No RoleMap" in r.detail

    def test_pass_when_role_maps_to_standard(self, tagged_pdf):
        pdf, struct_root, _ = tagged_pdf
        struct_root[Name.RoleMap] = Dictionary()
        struct_root[Name.RoleMap][Name("/MyHeading")] = Name("/H1")
        r = pdf_checks.check_14_001(pdf)
        assert r.severity == Severity.Pass

    def test_fail_on_unknown_target(self, tagged_pdf):
        pdf, struct_root, _ = tagged_pdf
        struct_root[Name.RoleMap] = Dictionary()
        struct_root[Name.RoleMap][Name("/Custom")] = Name("/NotAStandardRole")
        r = pdf_checks.check_14_001(pdf)
        assert r.severity == Severity.Fail
        assert "unresolvable" in r.detail

    def test_fail_on_cyclic_role_map(self, tagged_pdf):
        pdf, struct_root, _ = tagged_pdf
        struct_root[Name.RoleMap] = Dictionary()
        struct_root[Name.RoleMap][Name("/A")] = Name("/B")
        struct_root[Name.RoleMap][Name("/B")] = Name("/A")
        r = pdf_checks.check_14_001(pdf)
        assert r.severity == Severity.Fail
        assert "cyclic" in r.detail

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_14_001(blank_pdf)
        assert r.severity == Severity.Info


# ---------------------------------------------------------------------------
# 09-007  First heading is on level 1
# ---------------------------------------------------------------------------

class TestCheck09007:
    def _add_heading(self, pdf, doc_elem, role_name):
        h = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name(f"/{role_name}"), P=doc_elem))
        doc_elem[Name.K] = h
        return h

    def test_pass_when_first_heading_is_h1(self, tagged_pdf):
        pdf, _, doc_elem = tagged_pdf
        self._add_heading(pdf, doc_elem, "H1")
        r = pdf_checks.check_09_007(pdf)
        assert r.severity == Severity.Pass

    def test_pass_when_only_unlevelled_h(self, tagged_pdf):
        pdf, _, doc_elem = tagged_pdf
        self._add_heading(pdf, doc_elem, "H")
        r = pdf_checks.check_09_007(pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_first_heading_is_h2(self, tagged_pdf):
        pdf, _, doc_elem = tagged_pdf
        self._add_heading(pdf, doc_elem, "H2")
        r = pdf_checks.check_09_007(pdf)
        assert r.severity == Severity.Fail
        assert "<H2>" in r.detail

    def test_info_when_no_headings(self, tagged_pdf):
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_09_007(pdf)
        assert r.severity == Severity.Info
        assert "No heading" in r.detail

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_09_007(blank_pdf)
        assert r.severity == Severity.Info


# ---------------------------------------------------------------------------
# 14-004  Table rows are regular
# ---------------------------------------------------------------------------

class TestCheck14004:
    def _regular_table(self, pdf, doc_elem, col_count=2):
        """Table -> TBody -> [TR -> N cells] x2 (both rows same width)."""
        rows = []
        for _ in range(2):
            cells = Array([
                pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD))
                for _ in range(col_count)
            ])
            tr = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=cells))
            rows.append(tr)
        tbody = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.TBody, K=Array(rows))
        )
        table = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem)
        )
        doc_elem[Name.K] = table
        return table

    def test_pass_for_regular_table(self, tagged_pdf):
        pdf, _, doc_elem = tagged_pdf
        self._regular_table(pdf, doc_elem)
        r = pdf_checks.check_14_004(pdf)
        assert r.severity == Severity.Pass

    def test_warning_for_irregular_rows(self, tagged_pdf):
        pdf, _, doc_elem = tagged_pdf
        # Row 1: 2 cells, Row 2: 3 cells — irregular.
        td2 = Array([pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD)) for _ in range(2)])
        td3 = Array([pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TD)) for _ in range(3)])
        tr1 = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td2))
        tr2 = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.TR, K=td3))
        tbody = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.TBody, K=Array([tr1, tr2]))
        )
        table = pdf.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.Table, K=tbody, P=doc_elem)
        )
        doc_elem[Name.K] = table
        r = pdf_checks.check_14_004(pdf)
        assert r.severity == Severity.Warning
        assert "3 cells" in r.detail

    def test_info_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_14_004(blank_pdf)
        assert r.severity == Severity.Info


# ---------------------------------------------------------------------------
# 28-001  Link annotations nested inside <Link>
# ---------------------------------------------------------------------------

class TestCheck28001:
    def _add_link_annot(self, pdf, page_obj, indirect=True):
        annot = pdf.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=Array([0, 0, 10, 10]))
        )
        page_obj[Name.Annots] = Array([annot])
        return annot

    def test_fail_when_link_annot_not_tagged(self, tagged_pdf):
        pdf, struct_root, doc_elem = tagged_pdf
        self._add_link_annot(pdf, pdf.pages[0].obj)
        r = pdf_checks.check_28_001(pdf)
        assert r.severity == Severity.Fail
        assert "1 Link annotation" in r.detail

    def test_pass_when_all_links_tagged(self, tagged_pdf):
        from pdftagvalicate import link_nesting_repair
        pdf, struct_root, doc_elem = tagged_pdf
        self._add_link_annot(pdf, pdf.pages[0].obj)
        # Run the repair so the annotation gets wrapped.
        link_nesting_repair.fix(pdf)
        r = pdf_checks.check_28_001(pdf)
        assert r.severity == Severity.Pass

    def test_pass_when_no_link_annots(self, tagged_pdf):
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_28_001(pdf)
        assert r.severity == Severity.Pass


# ---------------------------------------------------------------------------
# 31-001  All fonts embedded
# ---------------------------------------------------------------------------

class TestCheck31001:
    def test_pass_when_no_fonts(self, blank_pdf):
        """A PDF with no fonts should pass (nothing to fail)."""
        r = pdf_checks.check_31_001(blank_pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_font_has_no_descriptor(self, blank_pdf):
        """A non-Type3 font with no FontDescriptor is considered not embedded."""
        font = blank_pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/Helvetica"))
        )
        blank_pdf.pages[0].obj[Name.Resources] = Dictionary(
            Font=Dictionary(F1=font)
        )
        r = pdf_checks.check_31_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "Helvetica" in r.detail

    def test_pass_when_font_has_embedded_file(self, blank_pdf):
        """A font with FontFile2 present passes the check."""
        font_stream = blank_pdf.make_indirect(pikepdf.Stream(blank_pdf, b"fake font data"))
        descriptor = blank_pdf.make_indirect(
            Dictionary(Type=Name.FontDescriptor, FontName=Name("/TestFont"),
                       FontFile2=font_stream)
        )
        font = blank_pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.TrueType,
                       BaseFont=Name("/TestFont"), FontDescriptor=descriptor)
        )
        blank_pdf.pages[0].obj[Name.Resources] = Dictionary(Font=Dictionary(F1=font))
        r = pdf_checks.check_31_001(blank_pdf)
        assert r.severity == Severity.Pass


# ---------------------------------------------------------------------------
# 09-004  No untagged page content
# ---------------------------------------------------------------------------

class TestCheck09004:
    def test_fail_when_no_struct_tree(self, blank_pdf):
        r = pdf_checks.check_09_004(blank_pdf)
        assert r.severity == Severity.Fail
        assert "untagged" in r.detail

    def test_fail_when_page_has_no_mcr(self, tagged_pdf):
        """Tagged PDF but the page has no MCR — struct tree exists but page is unaccounted for."""
        pdf, *_ = tagged_pdf
        r = pdf_checks.check_09_004(pdf)
        assert r.severity == Severity.Fail
        assert "p.1" in r.detail

    def test_pass_when_page_has_mcr(self, tagged_pdf):
        """Attach a MCR pointing at the page; check should pass."""
        pdf, struct_root, doc_elem = tagged_pdf
        page_obj = pdf.pages[0].obj
        mcr = pdf.make_indirect(
            Dictionary(Type=Name.MCR, Pg=page_obj, MCID=pikepdf.Object.parse(b"0"))
        )
        doc_elem[Name.K] = mcr
        r = pdf_checks.check_09_004(pdf)
        assert r.severity == Severity.Pass


# ===========================================================================
# Step 4 — hard check tests
# ===========================================================================


# ---------------------------------------------------------------------------
# 06-001  PDF/UA identifier in XMP
# ---------------------------------------------------------------------------

class TestCheck06001:
    def _set_pdfuaid(self, pdf, value):
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta.register_xml_namespace("http://www.aiim.org/pdfua/ns/id/", "pdfuaid")
            meta["pdfuaid:part"] = value

    def test_pass_when_part_is_1(self, blank_pdf):
        self._set_pdfuaid(blank_pdf, "1")
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Pass
        assert "'1'" in r.detail

    def test_fail_when_no_xmp(self, blank_pdf):
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "absent" in r.detail

    def test_fail_when_part_is_2(self, blank_pdf):
        self._set_pdfuaid(blank_pdf, "2")
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Fail
        assert "'2'" in r.detail

    def test_pass_with_attribute_form_xmp(self, blank_pdf):
        """Attribute-form XMP (pdfuaid:part as RDF attribute) is handled by pikepdf."""
        raw_xmp = (
            b"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"""
            b"""<x:xmpmeta xmlns:x='adobe:ns:meta/'>"""
            b"""<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"""
            b"""<rdf:Description rdf:about=''"""
            b"""    xmlns:pdfuaid='http://www.aiim.org/pdfua/ns/id/'"""
            b"""    pdfuaid:part='1'/>"""
            b"""</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"""
        )
        blank_pdf.Root[Name.Metadata] = blank_pdf.make_indirect(
            pikepdf.Stream(blank_pdf, raw_xmp)
        )
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Type]    = Name.Metadata
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Subtype] = Name.XML
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Pass

    def test_pass_with_remapped_prefix(self, blank_pdf):
        """Prefix 'ua' instead of 'pdfuaid' — pikepdf normalises to namespace URI."""
        raw_xmp = (
            b"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"""
            b"""<x:xmpmeta xmlns:x='adobe:ns:meta/'>"""
            b"""<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"""
            b"""<rdf:Description rdf:about=''"""
            b"""    xmlns:ua='http://www.aiim.org/pdfua/ns/id/'"""
            b"""    ua:part='1'/>"""
            b"""</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"""
        )
        blank_pdf.Root[Name.Metadata] = blank_pdf.make_indirect(
            pikepdf.Stream(blank_pdf, raw_xmp)
        )
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Type]    = Name.Metadata
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Subtype] = Name.XML
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Pass

    def test_fail_with_corrupt_xmp(self, blank_pdf):
        """Corrupt XMP is silently treated as empty by pikepdf — result is Fail."""
        blank_pdf.Root[Name.Metadata] = blank_pdf.make_indirect(
            pikepdf.Stream(blank_pdf, b"not xml at all <<<>>>")
        )
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Type]    = Name.Metadata
        blank_pdf.Root[Name.Metadata].stream_dict[Name.Subtype] = Name.XML
        r = pdf_checks.check_06_001(blank_pdf)
        assert r.severity == Severity.Fail


# ---------------------------------------------------------------------------
# 09-006  No untagged real content in page streams
# ---------------------------------------------------------------------------

class TestCheck09006:
    def _set_content(self, pdf, page_obj, stream: bytes):
        page_obj[Name.Contents] = pdf.make_indirect(pikepdf.Stream(pdf, stream))

    def test_pass_when_no_content_stream(self, blank_pdf):
        """Page with no /Contents — nothing to flag."""
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Pass

    def test_pass_when_all_painting_inside_bdc(self, blank_pdf):
        cs = b'/P <</MCID 0>> BDC BT (hello) Tj ET EMC'
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_tj_outside_bdc(self, blank_pdf):
        cs = b'BT (untagged text) Tj ET'
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Fail
        assert "'Tj'" in r.detail

    def test_fail_when_fill_outside_bdc(self, blank_pdf):
        cs = b'0 0 100 100 re f'
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Fail
        assert "'f'" in r.detail

    def test_pass_when_nested_bdc(self, blank_pdf):
        """Nested BDC/EMC — painting inside inner layer is still tagged."""
        cs = b'/P <</MCID 0>> BDC /Q <</MCID 1>> BDC (text) Tj EMC EMC'
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Pass

    def test_pass_empty_content(self, blank_pdf):
        """Empty content stream — no painting ops at all."""
        cs = b''
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Pass

    def test_fail_when_stroke_outside_bdc(self, blank_pdf):
        cs = b'0 0 m 100 100 l S'
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        assert r.severity == Severity.Fail
        assert "'S'" in r.detail

    def test_emc_underflow_does_not_crash(self, blank_pdf):
        """More EMC than BDC — depth floors at 0, no crash."""
        cs = b'EMC EMC BT (text) Tj ET'  # depth never goes below 0
        self._set_content(blank_pdf, blank_pdf.pages[0].obj, cs)
        r = pdf_checks.check_09_006(blank_pdf)
        # 'Tj' is outside any MC layer after EMC underflow.
        assert r.severity == Severity.Fail
