from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.services.extraction import Page

# Tried in order: paragraphs, lines, sentence ends, clauses, words.
# Long paragraphs are cut at sentence ends before anything smaller.
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=SEPARATORS,
    keep_separator="end",
)


@dataclass
class TextChunk:
    chunk_index: int
    content: str
    page_number: int | None = None


def split_pages(pages: list[Page]) -> list[TextChunk]:
    chunks = []
    for page in pages:
        for piece in splitter.split_text(page.text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=piece,
                    page_number=page.page_number,
                )
            )
    return chunks
