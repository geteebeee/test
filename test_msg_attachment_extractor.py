from pathlib import Path

from msg_attachment_extractor import AttachmentRecord, MsgAttachmentExtractor


def test_filter_records_accepts_dot_and_no_dot():
    records = [
        AttachmentRecord(Path("a.msg"), "x.pdf", ".pdf", 1),
        AttachmentRecord(Path("a.msg"), "x.docx", ".docx", 1),
    ]

    pdf_a = MsgAttachmentExtractor.filter_records(records, ".pdf")
    pdf_b = MsgAttachmentExtractor.filter_records(records, "pdf")

    assert len(pdf_a) == 1
    assert len(pdf_b) == 1
    assert pdf_a[0].attachment_name == "x.pdf"
    assert pdf_b[0].attachment_name == "x.pdf"


def test_records_for_extraction_applies_filter_when_enabled():
    records = [
        AttachmentRecord(Path("a.msg"), "x.pdf", ".pdf", 1, selected=True),
        AttachmentRecord(Path("a.msg"), "x.docx", ".docx", 1, selected=True),
        AttachmentRecord(Path("a.msg"), "x.txt", ".txt", 1, selected=False),
    ]

    with_filter = MsgAttachmentExtractor.records_for_extraction(records, "pdf", True)
    without_filter = MsgAttachmentExtractor.records_for_extraction(records, "pdf", False)

    assert [r.attachment_name for r in with_filter] == ["x.pdf"]
    assert [r.attachment_name for r in without_filter] == ["x.pdf", "x.docx"]


def test_safe_destination_deduplicates(tmp_path: Path):
    (tmp_path / "report.pdf").write_text("exists")

    path1 = MsgAttachmentExtractor._safe_destination(tmp_path, "report.pdf")
    path1.write_text("new")

    path2 = MsgAttachmentExtractor._safe_destination(tmp_path, "report.pdf")

    assert path1.name == "report_1.pdf"
    assert path2.name == "report_2.pdf"
