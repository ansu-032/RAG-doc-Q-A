import logging
from functools import lru_cache
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from src.config import settings
from src.schemas.query import ChatTurn

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
            "Asking for an opinion or evaluation of the document (is it useful, good, does it "
            "work) is document_broad. If unsure, pick document_specific.\n\n"
            "Recent conversation, oldest first (may be empty):\n{history}\n\n"
            "Also rewrite the question as one clear, complete English question that makes sense "
            "without the conversation: replace words like 'this college', 'he', 'it' or 'that' "
            "with what they refer to in the conversation, fix typos and short forms (e.g. 'imp' "
            "means 'important'), keep its meaning, keep names and terms as the user wrote them "
            "(they may be names from the document), and add no facts beyond those references.\n\n"
            "Also set needs_web. It is true ONLY if a correct answer requires recent or current "
            "information that changes over time, e.g. today's news, latest versions or releases, "
            "current prices, weather, scores, or who holds a position now. It is false for "
            "everything else: greetings, opinions, definitions, explanations, history, and "
            "established facts a language model already knows.",
        ),
        ("human", "{question}"),
    ]
)

# Only the router sees the history, so this caps the only extra prompt size it adds.
HISTORY_MAX_MESSAGES = 6  # 3 question/answer turns
HISTORY_MAX_CHARS = 300


def format_history(history: list[ChatTurn]) -> str:
    lines = []
    for turn in history[-HISTORY_MAX_MESSAGES:]:
        text = " ".join(turn.content.split())
        if len(text) > HISTORY_MAX_CHARS:
            text = text[:HISTORY_MAX_CHARS] + "…"
        lines.append(f"{turn.role}: {text}")
    return "\n".join(lines) or "(none)"


class RouteDecision(BaseModel):
    route: Literal["document_specific", "document_broad", "general"]
    rewritten_question: str = Field(description="The question, rewritten clearly")
    needs_web: bool = Field(description="True only if answering requires recent or current information")


@lru_cache
def get_router():
    llm = ChatGroq(model=settings.router_model, api_key=settings.groq_api_key, temperature=0)
    # Strict json_schema: Groq guarantees the output matches (GPT-OSS models); tool calling often broke it.
    return prompt | llm.with_structured_output(RouteDecision, method="json_schema", strict=True)


async def route(question: str, filename: str, history: list[ChatTurn]) -> RouteDecision:
    """Decide where the question goes, and rewrite it clearly for retrieval and answering."""
    try:
        return await get_router().ainvoke(
            {"question": question, "filename": filename, "history": format_history(history)}
        )
    except Exception:
        # Any failure (API error, bad output): the document is the safest default.
        logger.exception("Router failed, using document_specific")
        return RouteDecision(route="document_specific", rewritten_question=question, needs_web=False)
