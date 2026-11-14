import io
import re
from dataclasses import dataclass

from docx import Document
from docx.table import Table
from pypdf import PdfReader

PDF_TYPES = {"application/pdf"}
DOCX_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MARKDOWN_TYPES = {"text/markdown", "text/x-markdown"}


class UnsupportedFileType(Exception):
    pass


@dataclass
class Page:
    """Text from one part of a file. page_number is None for formats without pages (DOCX, MD)."""

    page_number: int | None
    text: str


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pdf_text(text: str) -> str:
    # Words hyphenated across lines: "infor-\nmation" -> "information".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # A single line break inside a paragraph is just PDF layout: join the lines.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return normalize_whitespace(text)


def extract_pdf(data: bytes) -> list[Page]:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = clean_pdf_text(page.extract_text() or "")
        if text:
            pages.append(Page(page_number=number, text=text))
    return pages


def extract_docx(data: bytes) -> list[Page]:
    document = Document(io.BytesIO(data))
    blocks = []
    # Paragraphs and tables, in the order they appear in the document.
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))
        elif block.text.strip():
            blocks.append(block.text)
    text = normalize_whitespace("\n\n".join(blocks))
    return [Page(page_number=None, text=text)] if text else []


def extract_markdown(data: bytes) -> list[Page]:
    text = normalize_whitespace(data.decode("utf-8", errors="replace"))
    return [Page(page_number=None, text=text)] if text else []


def extract_text(data: bytes, mime_type: str) -> list[Page]:
    if mime_type in PDF_TYPES:
        return extract_pdf(data)
    if mime_type in DOCX_TYPES:
        return extract_docx(data)
    if mime_type in MARKDOWN_TYPES:
        return extract_markdown(data)
    raise UnsupportedFileType(f"Text extraction is not supported for '{mime_type}'")
