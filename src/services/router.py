import logging
from functools import lru_cache
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger("uvicorn.error")

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You route questions in a document Q&A app. The user has opened one document "
            "and is most likely asking about it.\n\n"
            "Document: {filename}\n\n"
            "Pick one route:\n"
            "- document_specific: asks for a particular fact, detail or section that could be "
            "in the document. This is the default.\n"
            "- document_broad: asks about the document as a whole, e.g. a summary, overview, "
            "key or important points, main parts, or 'explain this'.\n"
            "- general: clearly unrelated to the document, e.g. other topics, news or current events.\n"
            "Words like 'this', 'here', 'it', 'the project' or 'the paper' mean the document. "
            "If unsure, pick document_specific.\n\n"
            "Also rewrite the question as one clear, complete English question: fix typos and "
            "short forms (e.g. 'imp' means 'important'), keep its meaning, keep names and terms "
            "as the user wrote them (they may be names from the document), and do not add facts.",
        ),
        ("human", "{question}"),
    ]
)


class RouteDecision(BaseModel):
    route: Literal["document_specific", "document_broad", "general"]
    rewritten_question: str = Field(description="The question, rewritten clearly")


@lru_cache
def get_router():
    llm = ChatGroq(model=settings.router_model, api_key=settings.groq_api_key, temperature=0)
    # Strict json_schema: Groq guarantees the output matches (GPT-OSS models); tool calling often broke it.
    return prompt | llm.with_structured_output(RouteDecision, method="json_schema", strict=True)


async def route(question: str, filename: str) -> RouteDecision:
    """Decide where the question goes, and rewrite it clearly for retrieval and answering."""
    try:
        return await get_router().ainvoke({"question": question, "filename": filename})
    except Exception:
        # Any failure (API error, bad output): the document is the safest default.
        logger.exception("Router failed, using document_specific")
        return RouteDecision(route="document_specific", rewritten_question=question)
