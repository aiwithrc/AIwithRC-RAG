from pathlib import Path

import pytest

from app.rag.chunk import chunk_blocks, count_tokens, split_sentences
from app.rag.parse import NO_TEXT_LAYER, Block, ParseError, file_type, parse, sniff_ok
from tests.fixtures import make_blank_pdf, make_docx, make_pdf, make_xlsx


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


def write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    p = tmp_path / name
    p.write_bytes(data.encode() if isinstance(data, str) else data)
    return p


# ---- parsing ----

def test_pdf_keeps_pages_and_numbered_sections(tmp_path):
    pdf = make_pdf([
        "Master Services Agreement\n\nThis agreement is between Acme and Vendor.",
        "11.2 Termination for Convenience\nEither party may terminate this Agreement upon sixty (60) days notice.",
    ])
    blocks = parse(write(tmp_path, "msa.pdf", pdf), "msa.pdf")
    assert {b.page for b in blocks} == {1, 2}
    term = [b for b in blocks if "sixty" in b.text][0]
    assert term.page == 2
    assert term.section == "§11.2 Termination for Convenience"


def test_scanned_pdf_fails_with_ocr_message(tmp_path):
    with pytest.raises(ParseError) as e:
        parse(write(tmp_path, "scan.pdf", make_blank_pdf()), "scan.pdf")
    assert str(e.value) == NO_TEXT_LAYER == "No text layer found. Turn on OCR in Settings."


def test_damaged_pdf(tmp_path):
    with pytest.raises(ParseError, match="damaged"):
        parse(write(tmp_path, "bad.pdf", b"%PDF-1.4\ngarbage"), "bad.pdf")


def test_docx_headings_become_sections_and_tables_are_kept(tmp_path):
    data = make_docx(
        [("Heading 1", "Fees"), ("Normal", "Invoices are due within 45 days."),
         ("Heading 2", "Late payment"), ("Normal", "Interest is 1% per month.")],
        table=[["Role", "Rate"], ["Engineer", "$150/h"]],
    )
    blocks = parse(write(tmp_path, "a.docx", data), "a.docx")
    by_text = {b.text: b for b in blocks}
    assert by_text["Invoices are due within 45 days."].section == "Fees"
    assert by_text["Interest is 1% per month."].section == "Fees › Late payment"
    assert any("Engineer | $150/h" in b.text for b in blocks)


def test_xlsx_rows_become_header_value_text(tmp_path):
    data = make_xlsx({"Rates": [["Role", "Rate", "Currency"], ["Engineer", 150, "USD"], ["PM", 120.0, "USD"]]})
    # Stored like real uploads: named by hash, no extension.
    blocks = parse(write(tmp_path, "3f9a0c", data), "r.xlsx")
    assert blocks[0].text == "Role: Engineer; Rate: 150; Currency: USD"
    assert blocks[1].text == "Role: PM; Rate: 120; Currency: USD"
    assert blocks[0].section == "Sheet: Rates"


def test_csv_with_semicolons_and_bom(tmp_path):
    blocks = parse(write(tmp_path, "c.csv", "﻿name;city\nAda;London\nGrace;Arlington\n"), "c.csv")
    assert [b.text for b in blocks] == ["name: Ada; city: London", "name: Grace; city: Arlington"]


def test_markdown_sections(tmp_path):
    md = "# Runbook\n\nIntro text.\n\n## Rollback\n\nRedeploy the previous tag.\n\n```\n# not a heading\n```\n"
    blocks = parse(write(tmp_path, "r.md", md), "r.md")
    rollback = [b for b in blocks if b.text.startswith("Redeploy")][0]
    assert rollback.section == "Runbook › Rollback"
    assert any("# not a heading" in b.text for b in blocks)
    # A heading followed directly by another heading has no body, so it's dropped.
    bare = parse(write(tmp_path, "e.md", "# Deploy\n\n## Rollback\n\nRedeploy.\n"), "e.md")
    assert [b.text for b in bare] == ["Rollback", "Redeploy."]


def test_txt_cp1252_and_empty(tmp_path):
    blocks = parse(write(tmp_path, "t.txt", "Caf\xe9 menu\n\nSecond para.".encode("cp1252")), "t.txt")
    assert blocks[0].text == "Café menu"
    with pytest.raises(ParseError, match="no text"):
        parse(write(tmp_path, "e.txt", "   \n\n "), "e.txt")


def test_file_type_and_sniffing(tmp_path):
    assert file_type("Report.PDF").label == "PDF"
    assert file_type("notes.markdown").label == "MD"
    assert file_type("x.exe") is None and file_type("noext") is None
    pdf = write(tmp_path, "a.pdf", make_pdf(["hi there"]))
    assert sniff_ok(file_type("a.pdf"), pdf.read_bytes()[:8192], pdf)
    fake = write(tmp_path, "b.pdf", b"MZ\x90\x00 not a pdf")
    assert not sniff_ok(file_type("b.pdf"), fake.read_bytes(), fake)
    docx = write(tmp_path, "c.docx", make_docx([("Normal", "x")]))
    assert sniff_ok(file_type("c.docx"), docx.read_bytes()[:8192], docx)
    assert not sniff_ok(file_type("c.xlsx"), docx.read_bytes()[:8192], docx)  # a docx renamed .xlsx
    assert not sniff_ok(file_type("d.txt"), b"abc\x00def", tmp_path / "d.txt")


# ---- chunking ----

def test_split_sentences_respects_abbreviations():
    s = split_sentences("Dr. Smith signed on Jan. 5. The fee is $5.00 per unit. See e.g. Annex 2. Done!")
    assert s == ["Dr. Smith signed on Jan. 5.", "The fee is $5.00 per unit.", "See e.g. Annex 2.", "Done!"]


def _sentences(n: int, prefix: str = "Clause") -> str:
    return " ".join(f"{prefix} {i} says the parties agree to item number {i} in full." for i in range(n))


def test_chunks_fit_size_and_never_split_sentences():
    blocks = [Block(_sentences(80), page=1)]
    chunks = chunk_blocks(blocks, chunk_size=100, overlap=20)
    assert len(chunks) > 5
    for c in chunks:
        assert c.token_count <= 100
        assert c.text.endswith(".")
        assert c.text.startswith("Clause")


def test_chunks_overlap_by_whole_sentences():
    chunks = chunk_blocks([Block(_sentences(40))], chunk_size=80, overlap=30)
    for a, b in zip(chunks, chunks[1:]):
        last_of_a = split_sentences(a.text)[-1]
        assert last_of_a in b.text  # trailing sentence carried over
    no_overlap = chunk_blocks([Block(_sentences(40))], chunk_size=80, overlap=0)
    joined = " ".join(c.text for c in no_overlap)
    assert joined.count("Clause 7 says") == 1


def test_new_section_starts_new_chunk_without_overlap():
    blocks = [Block("Fees are due monthly.", section="§5 Fees"), Block("Either party may terminate.", section="§11 Term")]
    chunks = chunk_blocks(blocks, chunk_size=500, overlap=100)
    assert [(c.text, c.section) for c in chunks] == [
        ("Fees are due monthly.", "§5 Fees"),
        ("Either party may terminate.", "§11 Term"),
    ]


def test_page_change_breaks_full_chunks_and_records_start_page():
    blocks = [Block(_sentences(6, "Alpha"), page=1), Block(_sentences(6, "Beta"), page=2)]
    chunks = chunk_blocks(blocks, chunk_size=200, overlap=0)
    assert [c.page for c in chunks] == [1, 2]
    assert chunks[1].text.startswith("Beta")
    # A small tail on page 1 merges into the page-2 chunk instead of making a tiny chunk.
    merged = chunk_blocks([Block("Short.", page=1), Block(_sentences(3, "Beta"), page=2)], chunk_size=200)
    assert len(merged) == 1 and merged[0].page == 1


def test_overlong_sentence_is_hard_split():
    long = "word " * 500
    chunks = chunk_blocks([Block(long.strip() + ".")], chunk_size=100, overlap=0)
    assert len(chunks) >= 5
    assert all(c.token_count <= 100 for c in chunks)


def test_paragraphs_keep_blank_line_between_them():
    chunks = chunk_blocks([Block("First para one. First para two.\n\nSecond para.")], chunk_size=200)
    assert chunks[0].text == "First para one. First para two.\n\nSecond para."
    assert count_tokens(chunks[0].text) == chunks[0].token_count
