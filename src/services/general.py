import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from groq import APIError, AsyncGroq

from src.config import settings

logger = logging.getLogger("uvicorn.error")

UNAVAILABLE = "Not found in the document, and web search is unavailable right now."

SYSTEM_PROMPT = (
    "You answer general questions concisely and accurately.\n"
    "- Search the web when the question needs recent or factual information you are not sure of.\n"
    "- Do not invent facts; if you do not know, say so."
)


@dataclass
class GeneralAnswer:
    text: str
    # "web" if the model searched the web, "llm" if it answered from its own knowledge.
    source: Literal["web", "llm", "none"]
    web_sources: list[tuple[str, str]] = field(default_factory=list)  # (title, url)


@lru_cache
def get_client() -> AsyncGroq:
    # A separate key, so web questions do not use up the document-answer quota.
    return AsyncGroq(api_key=settings.general_groq_api_key)


async def answer(question: str) -> GeneralAnswer:
    """Answer without the document; the model decides by itself whether to search the web."""
    # Only the question is sent: document text never goes into the web search.
    try:
        response = await get_client().chat.completions.create(
            model=settings.general_llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            tools=[{"type": "browser_search"}],
        )
    except APIError:
        logger.exception("General LLM failed")
        return GeneralAnswer(UNAVAILABLE, "none")

    message = response.choices[0].message
    if not message.content:
        return GeneralAnswer(UNAVAILABLE, "none")

    # Every page the model searched or opened, once each, in the order it used them.
    web_sources: dict[str, str] = {}
    for tool in message.executed_tools or []:
        results = tool.search_results.results if tool.search_results else None
        for result in results or []:
            if result.url and result.url not in web_sources:
                web_sources[result.url] = result.title or result.url

    return GeneralAnswer(
        message.content.strip(),
        "web" if web_sources else "llm",
        [(title, url) for url, title in web_sources.items()],
    )
