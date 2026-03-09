from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = Field(..., min_length=1)
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.2
    groq_timeout_seconds: int = 30
    openai_api_key: str | None = None
    embedding_provider: str = "hash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_index_path: str = "./data/chroma_db"
    embedding_chunk_size: int = 800
    embedding_chunk_overlap: int = 120
    cors_origin_ip: str = "127.0.0.1"
    cors_origin_scheme: str = "http"
    cors_origin_ports: str = "3000,5173"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_calendar_id: str = "primary"
    google_token_uri: str = "https://oauth2.googleapis.com/token"

    @property
    def cors_allow_origins(self) -> list[str]:
        ports = [
            part.strip()
            for part in self.cors_origin_ports.split(",")
            if part.strip()
        ]
        if not ports:
            return [f"{self.cors_origin_scheme}://{self.cors_origin_ip}"]
        return [
            f"{self.cors_origin_scheme}://{self.cors_origin_ip}:{port}"
            for port in ports
        ]

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
