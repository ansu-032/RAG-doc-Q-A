from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every value comes from .env; there are no defaults in code."""

    model_config = SettingsConfigDict(env_file=".env")

    database_url: str

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str

    allowed_mime_types: list[str]

    chunk_size: int
    chunk_overlap: int

    # Output size must match EMBEDDING_DIM in src/db/models.py.
    embedding_model: str
    embedding_batch_size: int

    groq_api_key: str
    llm_model: str
    llm_temperature: float

    # Reads the question first: picks a route and rewrites it clearly. Uses GROQ_API_KEY;
    # each Groq model has its own rate limit, so it does not slow answers down.
    router_model: str

    # Fallback when the document has no answer: a second Groq key and a model that can search the web.
    general_groq_api_key: str
    general_llm_model: str

    # Retrieval: chunks sent to the LLM, and the lowest cosine similarity that counts as relevant.
    top_k: int
    min_score: float


settings = Settings()
