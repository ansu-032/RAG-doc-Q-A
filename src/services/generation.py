from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from src.config import settings
from src.logging_config import logger

NOT_FOUND = "Not found in the documents."

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions using ONLY the numbered context passages below from the uploaded documents.\n"
            "- When multiple documents are referenced in the passages, correlate, synthesize, and compare their concepts to answer relational questions thoroughly.\n"
            "- Cite every fact with the passage number in brackets, like [1] or [2][3].\n"
            "- Do not use outside knowledge, and do not guess.\n"
            f"- If the passages do not contain the answer, reply exactly: {NOT_FOUND}\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)


@lru_cache
def get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
    )


async def answer(question: str, passages: list[str]) -> str:
    """Answer from the given passages; passage i is cited as [i+1]."""
    if not passages:
        return NOT_FOUND
    context = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(passages, start=1))
    message = await (prompt | get_llm()).ainvoke({"context": context, "question": question})
    usage = message.usage_metadata or {}
    logger.info(
        "Answer LLM usage: model=%s %s input, %s output tokens",
        settings.llm_model,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )
    return message.content.strip()