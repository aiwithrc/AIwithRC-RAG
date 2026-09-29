"""Turn an uploaded file into text blocks that keep their page (PDF) or section (DOCX/MD/sheets).

Every parser raises `ParseError` with a message written for the person who uploaded the file;
it is shown as-is in the documents table.
"""

import csv
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

NO_TEXT_LAYER = "No text layer found. Turn on OCR in Settings."


class ParseError(Exception):
    """A file we can't index. The message is user-facing."""


@dataclass
class Block:
    text: str
    page: int | None = None
    section: str | None = None
    heading: bool = False  # a heading line; dropped if no body text follows it in its section


# ---- File types ----

@dataclass(frozen=True)
class FileType:
    ext: str
    label: str  # badge in the UI: PDF, DOCX, …
    mime: str


FILE_TYPES: dict[str, FileType] = {
    t.ext: t
    for t in [
        FileType("pdf", "PDF", "application/pdf"),
        FileType("docx", "DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        FileType("xlsx", "XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        FileType("csv", "CSV", "text/csv"),
        FileType("md", "MD", "text/markdown"),
        FileType("markdown", "MD", "text/markdown"),
        FileType("txt", "TXT", "text/plain"),
    ]
}


def file_type(filename: str) -> FileType | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return FILE_TYPES.get(ext)


def sniff_ok(ft: FileType, head: bytes, path: Path) -> bool:
    """Check the file's content matches its extension (magic bytes / container layout)."""
    if ft.ext == "pdf":
        return b"%PDF-" in head[:1024]
    if ft.ext in ("docx", "xlsx"):
        if not head.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return False
        return ("word/document.xml" if ft.ext == "docx" else "xl/workbook.xml") in names
    # Text formats: no NUL bytes and decodable.
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError as e:
        # A multi-byte character cut off at the end of the sniffed window is fine.
        if e.start >= len(head) - 4:
            return True
        try:
            head.decode("cp1252")
            return True
        except UnicodeDecodeError:
            return False


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("Couldn't read this file's text encoding. Save it as UTF-8 and upload again.")


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---- PDF ----

# "11.2 Termination for Convenience." / "4 Methods" / "Section 3 - Fees"
_NUMBERED_HEADING = re.compile(r"^(?:(?:Section|Article|§)\s*)?(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^\n]{2,80}?)\.?$")


def _pdf_heading(line: str) -> str | None:
    line = line.strip()
    if len(line) > 90:
        return None
    m = _NUMBERED_HEADING.match(line)
    if m and not line.endswith((",", ";")) and len(m.group(2).split()) <= 10:
        return f"§{m.group(1)} {m.group(2).rstrip('.')}"
    if 3 < len(line) <= 60 and line.isupper() and any(c.isalpha() for c in line):
        return line.title()
    return None


def _ocr(path: Path) -> Path:
    if not shutil.which("ocrmypdf"):
        raise ParseError("OCR is turned on, but OCR support isn't installed on this server. See the README.")
    out = Path(tempfile.mkstemp(suffix=".pdf")[1])
    proc = subprocess.run(
        ["ocrmypdf", "--skip-text", "--quiet", str(path), str(out)], capture_output=True, timeout=900
    )
    if proc.returncode not in (0, 6):  # 6 = "already has text", fine with --skip-text
        out.unlink(missing_ok=True)
        raise ParseError("OCR failed on this PDF.")
    return out


def parse_pdf(path: Path, *, ocr: bool = False) -> list[Block]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("This PDF is password-protected. Remove the password and upload again.")
        pages = [p.extract_text() or "" for p in reader.pages]
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ParseError("This PDF looks damaged and couldn't be read.") from e

    chars = sum(len(p.strip()) for p in pages)
    if not pages or chars < 20 * max(1, len(pages)) * 0.25:
        if not ocr:
            raise ParseError(NO_TEXT_LAYER)
        ocred = _ocr(path)
        try:
            return parse_pdf(ocred, ocr=False)
        except ParseError as e:
            if str(e) == NO_TEXT_LAYER:
                raise ParseError("OCR found no readable text in this PDF.") from e
            raise
        finally:
            ocred.unlink(missing_ok=True)

    blocks: list[Block] = []
    section: str | None = None
    for i, page_text in enumerate(pages, start=1):
        # PDF text extraction often drops the blank line before a heading, so check every line:
        # a heading line ends the current paragraph and starts a new section.
        buf: list[str] = []

        def flush() -> None:
            para = "\n".join(buf).strip()
            buf.clear()
            if para:
                blocks.append(Block(para, page=i, section=section))  # noqa: B023

        for line in _clean(page_text).split("\n"):
            if not line.strip():
                flush()
                continue
            if (h := _pdf_heading(line)) is not None:
                flush()
                section = h
            buf.append(line)
        flush()
    return blocks


# ---- DOCX ----

def _run_pt(run) -> float | None:
    return run.font.size.pt if run.font.size is not None else None


def _docx_body_size(document) -> float | None:
    """Most common font size by amount of text: the body size that headings stand out from."""
    weight: dict[float, int] = {}
    for p in document.paragraphs:
        for r in p.runs:
            if (pt := _run_pt(r)) is not None and r.text.strip():
                weight[pt] = weight.get(pt, 0) + len(r.text)
    return max(weight, key=weight.get) if weight else None


def _docx_visual_heading(p, text: str, body_pt: float | None) -> int | None:
    """Heading level for a paragraph that *looks* like a heading without using a Heading style.

    Many real documents (résumés, reports exported from other tools) format headings as bold or
    larger text. Short, non-list, no trailing full stop, and either all bold (level 1, or 0 for a
    big title) or starting in a larger font than the body (level 2, e.g. job-title lines).
    """
    if len(text) > 120 or text.endswith((".", ":", ";", ",")) or "\n" in text:
        return None
    ppr = p._p.pPr
    if ppr is not None and ppr.numPr is not None or "List" in ((p.style.name if p.style is not None else "") or ""):
        return None
    runs = [r for r in p.runs if r.text.strip()]
    if not runs:
        return None
    sizes = [pt for r in runs if (pt := _run_pt(r)) is not None]
    biggest = max(sizes, default=None)
    if all(r.bold for r in runs):
        return 0 if body_pt and biggest and biggest >= body_pt + 4 else 1
    if body_pt and (first := _run_pt(runs[0])) is not None and first > body_pt + 0.25:
        return 2
    return None


def parse_docx(path: Path) -> list[Block]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(str(path))
    except Exception as e:  # python-docx raises a variety of errors for corrupt files
        raise ParseError("This Word file looks damaged and couldn't be read.") from e

    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []  # (level, text) stack
    body_pt = _docx_body_size(document)

    def section() -> str | None:
        return " › ".join(t for _, t in headings) or None

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = _clean(item.text)
            if not text:
                continue
            style = (item.style.name if item.style is not None else "") or ""
            m = re.match(r"(Heading|Title)\s*(\d*)", style)
            level = (0 if m.group(1) == "Title" else int(m.group(2) or 1)) if m else _docx_visual_heading(item, text, body_pt)
            if level is not None:
                while headings and headings[-1][0] >= level:
                    headings.pop()
                headings.append((level, text))
                blocks.append(Block(text, section=section(), heading=True))
            else:
                blocks.append(Block(text, section=section()))
        elif isinstance(item, Table):
            rows = []
            for row in item.rows:
                cells = [_clean(c.text) for c in row.cells]
                # Merged cells repeat; drop consecutive duplicates.
                dedup = [c for j, c in enumerate(cells) if c and (j == 0 or c != cells[j - 1])]
                if dedup:
                    rows.append(" | ".join(dedup))
            if rows:
                blocks.append(Block("\n".join(rows), section=section()))
    return blocks


# ---- Spreadsheets ----

def _rows_to_blocks(rows: Iterator[list[str]], sheet: str | None) -> list[Block]:
    blocks: list[Block] = []
    header: list[str] | None = None
    for row in rows:
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if header is None:
            header = cells
            continue
        pairs = [f"{h or f'Column {j + 1}'}: {v}" for j, (h, v) in enumerate(zip(header, cells, strict=False)) if v]
        pairs += [v for v in cells[len(header):] if v]
        blocks.append(Block("; ".join(pairs), section=sheet))
    if header is not None and not blocks:
        blocks.append(Block(" | ".join(c for c in header if c), section=sheet))
    return blocks


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def parse_xlsx(path: Path) -> list[Block]:
    import openpyxl

    # Pass a file object: uploads are stored as {sha256} with no extension, and openpyxl
    # rejects paths that don't end in .xlsx.
    with open(path, "rb") as fh:
        try:
            wb = openpyxl.load_workbook(fh, read_only=True, data_only=True)
        except Exception as e:
            raise ParseError("This spreadsheet looks damaged and couldn't be read.") from e
        blocks: list[Block] = []
        try:
            for ws in wb.worksheets:
                rows = ([_cell(v) for v in r] for r in ws.iter_rows(values_only=True))
                blocks += _rows_to_blocks(rows, f"Sheet: {ws.title}")
        finally:
            wb.close()
    return blocks


def parse_csv(path: Path) -> list[Block]:
    text = _read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return _rows_to_blocks(iter(csv.reader(io.StringIO(text), dialect)), None)


# ---- Markdown / text ----

def parse_markdown(path: Path) -> list[Block]:
    text = _read_text(path).replace("\r\n", "\n")
    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []
    in_code = False
    buf: list[str] = []

    def flush() -> None:
        para = _clean("\n".join(buf))
        buf.clear()
        if para:
            blocks.append(Block(para, section=" › ".join(t for _, t in headings) or None))

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            buf.append(line)
            continue
        m = None if in_code else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            flush()
            level = len(m.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, m.group(2).strip()))
            blocks.append(Block(m.group(2).strip(), section=" › ".join(t for _, t in headings), heading=True))
        elif not line.strip() and not in_code:
            flush()
        else:
            buf.append(line)
    flush()
    return blocks


def parse_text(path: Path) -> list[Block]:
    return [Block(p.strip()) for p in re.split(r"\n\s*\n", _clean(_read_text(path))) if p.strip()]


def parse(path: Path, filename: str, *, ocr: bool = False) -> list[Block]:
    ft = file_type(filename)
    if ft is None:
        raise ParseError("Unsupported file type.")
    parser = {
        "pdf": lambda p: parse_pdf(p, ocr=ocr),
        "docx": parse_docx,
        "xlsx": parse_xlsx,
        "csv": parse_csv,
        "md": parse_markdown,
        "markdown": parse_markdown,
        "txt": parse_text,
    }[ft.ext]
    blocks = [b for b in parser(path) if b.text.strip()]
    # A heading with no body before the next section is noise as a passage of its own.
    blocks = [
        b
        for i, b in enumerate(blocks)
        if not b.heading
        or (i + 1 < len(blocks) and not blocks[i + 1].heading and blocks[i + 1].section == b.section)
    ]
    if not blocks:
        raise ParseError("This file has no text to index.")
    return blocks
