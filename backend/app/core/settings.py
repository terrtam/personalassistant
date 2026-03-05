from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = Field(..., min_length=1)
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.2
    groq_timeout_seconds: int = 30
    openai_api_key: str | None = None
    embedding_provider: str = "huggingface"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_index_path: str = "./data/faiss_index"
    embedding_chunk_size: int = 800
    embedding_chunk_overlap: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if not settings.groq_api_key.strip():
        raise ValueError("GROQ_API_KEY is required and cannot be empty.")
    return settings
