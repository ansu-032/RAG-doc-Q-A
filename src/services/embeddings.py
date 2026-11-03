from functools import lru_cache

from fastembed import TextEmbedding

from src.config import settings


@lru_cache
def get_embedder() -> TextEmbedding:
    """Load the model once: it is slow to load and holds a lot of memory."""
    return TextEmbedding(settings.embedding_model)


# Embedding is CPU-bound: call these with asyncio.to_thread from async code.
def embed_passages(texts: list[str]) -> list[list[float]]:
    vectors = get_embedder().passage_embed(texts, batch_size=settings.embedding_batch_size)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    # query_embed adds the instruction prefix that BGE models expect on questions.
    return next(iter(get_embedder().query_embed(text))).tolist()
