from pdftagvalicate import metadata_check, metadata_repairs


def test_reports_missing_pdf_ua_identifier(blank_pdf):
    report = metadata_check.check_pdf_ua_identifier(blank_pdf)
    assert report.issues == 1


def test_pdf_ua_identifier_clean_after_fix(blank_pdf):
    metadata_repairs.fix_pdf_ua_identifier(blank_pdf)
    report = metadata_check.check_pdf_ua_identifier(blank_pdf)
    assert report.issues == 0


def test_reports_missing_mark_info(blank_pdf):
    report = metadata_check.check_mark_info(blank_pdf)
    assert report.issues == 1


def test_mark_info_clean_after_fix(blank_pdf):
    metadata_repairs.fix_mark_info(blank_pdf)
    report = metadata_check.check_mark_info(blank_pdf)
    assert report.issues == 0


def test_reports_missing_display_doc_title(blank_pdf):
    report = metadata_check.check_display_doc_title(blank_pdf)
    assert report.issues == 1


def test_display_doc_title_clean_after_fix(blank_pdf):
    metadata_repairs.fix_display_doc_title(blank_pdf)
    report = metadata_check.check_display_doc_title(blank_pdf)
    assert report.issues == 0
