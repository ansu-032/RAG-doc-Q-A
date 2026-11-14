import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """One earlier message in the chat, sent by the frontend so follow-up questions make sense."""

    role: Literal["user", "assistant"]
    content: str


class QueryIn(BaseModel):
    question: str = Field(min_length=1)
    # Oldest first. The router trims it again, so a client cannot send a huge prompt.
    history: list[ChatTurn] = Field(default_factory=list)


class Source(BaseModel):
    """A chunk the answer was based on; cited in the answer as [number]."""

    number: int
    chunk_index: int
    score: float
    content: str
    file_id: uuid.UUID | None = None
    filename: str | None = None
    page_number: int | None = None


class WebSource(BaseModel):
    """A web page the general model searched or opened."""

    title: str
    url: str


class QueryOut(BaseModel):
    file_id: uuid.UUID | None = None
    filename: str | None = None
    files_searched: list[str] = Field(default_factory=list)
    question: str
    # What the router decided, and the question as it rewrote it (used for search and answering).
    route: Literal["document_specific", "document_broad", "general"]
    rewritten_question: str
    # document: from the file's chunks; web: the general model searched the web; llm: its own knowledge.
    answer_source: Literal["document", "web", "llm", "none"]
    answer: str
    sources: list[Source]
    web_sources: list[WebSource]
