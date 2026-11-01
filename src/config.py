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

    # Retrieval: chunks sent to the LLM, and the lowest cosine similarity that counts as relevant.
    top_k: int
    min_score: float


settings = Settings()
