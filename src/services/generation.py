from functools import lru_cache

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from src.config import settings

NOT_FOUND = "Not found in the documents."

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions using ONLY the numbered context passages below.\n"
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


async def answer(question: str, passages: list[str]) -> tuple[str, AIMessage | None]:
    """Answer from the given passages; passage i is cited as [i+1].

    Also returns the raw LLM reply (token usage, timings), or None when the LLM was not called.
    """
    if not passages:
        return NOT_FOUND, None
    context = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(passages, start=1))
    message = await (prompt | get_llm()).ainvoke({"context": context, "question": question})
    return message.content.strip(), message
