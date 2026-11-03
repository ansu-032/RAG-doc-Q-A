import uuid

from pydantic import BaseModel, Field


class QueryIn(BaseModel):
    question: str = Field(min_length=1)


class Source(BaseModel):
    """A chunk the answer was based on; cited in the answer as [number]."""

    number: int
    chunk_index: int
    score: float
    content: str


class QueryOut(BaseModel):
    file_id: uuid.UUID
    filename: str
    question: str
    answer: str
    sources: list[Source]
