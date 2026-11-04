import asyncio
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from groq import APIError, AsyncGroq

from src.config import settings

logger = logging.getLogger("uvicorn.error")

UNAVAILABLE = "Not found in the document, and the general model is unavailable right now."
SEARCH_UNAVAILABLE = "This needs recent information, and web search is unavailable right now."

IDENTITY = (
    "You are Citely, an AI document assistant. If asked who you are, say you are Citely, the "
    "user's AI document assistant. Do not name the model, company or product behind you, do not "
    "claim to be ChatGPT or any other named assistant; if pressed, say you can't share that.\n"
)

SYSTEM_PROMPT = (
    f"{IDENTITY}"
    "You answer general questions concisely and accurately.\n"
    "- Do not invent facts; if you do not know, say so."
)

WEB_SYSTEM_PROMPT = (
    f"{IDENTITY}"
    "You answer questions using ONLY the numbered web search results below.\n"
    "- Be concise and cite facts with the result number in brackets, like [1].\n"
    "- If the results do not contain the answer, say so.\n\n"
    "Search results:\n{results}"
)

# Hard limits on what one general question can cost.
SEARCH_MAX_RESULTS = 3
SNIPPET_MAX_CHARS = 300
# These include the model's hidden reasoning tokens, so they cannot be set very low.
MAX_COMPLETION_TOKENS = 500
WEB_MAX_COMPLETION_TOKENS = 700


@dataclass
class GeneralAnswer:
    text: str
    # "web" if the answer used search results, "llm" if it came from the model's own knowledge.
    source: Literal["web", "llm", "none"]
    web_sources: list[tuple[str, str]] = field(default_factory=list)  # (title, url)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


@lru_cache
def get_client() -> AsyncGroq:
    # A separate key, so general questions do not use up the document-answer quota.
    return AsyncGroq(api_key=settings.general_groq_api_key)


def search_web(query: str) -> list[SearchResult]:
    """Top results as short snippets only: full pages never reach the model. Blocking call."""
    # Imported here so a missing package only disables search, not the whole app.
    from ddgs import DDGS

    return [
        SearchResult(r.get("title") or r["href"], r["href"], (r.get("body") or "")[:SNIPPET_MAX_CHARS])
        for r in DDGS().text(query, max_results=SEARCH_MAX_RESULTS)
        if r.get("href")
    ]


async def complete(system_prompt: str, question: str, max_tokens: int) -> str | None:
    try:
        response = await get_client().chat.completions.create(
            model=settings.general_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            reasoning_effort="low",
            max_completion_tokens=max_tokens,
        )
    except APIError:
        logger.exception("General LLM failed")
        return None
    if response.usage:
        logger.info(
            "General LLM usage: %d input, %d output tokens",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
    content = response.choices[0].message.content
    return content.strip() if content else None


async def answer(question: str, needs_web: bool = False) -> GeneralAnswer:
    """Answer without the document, searching the web only if the router says it needs recent data."""
    # Only the question is sent: document text never goes into the web search.
    if not needs_web:
        text = await complete(SYSTEM_PROMPT, question, MAX_COMPLETION_TOKENS)
        return GeneralAnswer(text, "llm") if text else GeneralAnswer(UNAVAILABLE, "none")

    try:
        results = await asyncio.to_thread(search_web, question)
    except Exception:
        # No LLM call without results: it could only guess at recent data.
        logger.exception("Web search failed")
        return GeneralAnswer(SEARCH_UNAVAILABLE, "none")
    if not results:
        return GeneralAnswer(SEARCH_UNAVAILABLE, "none")

    numbered = "\n\n".join(f"[{i}] {r.title}\n{r.snippet}" for i, r in enumerate(results, start=1))
    text = await complete(WEB_SYSTEM_PROMPT.format(results=numbered), question, WEB_MAX_COMPLETION_TOKENS)
    if not text:
        return GeneralAnswer(UNAVAILABLE, "none")
    return GeneralAnswer(text, "web", [(r.title, r.url) for r in results])
