from app.core.settings import get_settings


class HashEmbeddings:
    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in text.lower().split():
            idx = hash(token) % self.dims
            vector[idx] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def __call__(self, text: str) -> list[float]:
        return self.embed_query(text)


def get_embedding_model():
    settings = get_settings()
    provider = settings.embedding_provider.strip().lower()

    if provider == "hash":
        return HashEmbeddings()

    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=settings.embedding_model)

    if provider == "openai":
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise ValueError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER is 'openai'."
            )
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        )

    raise ValueError(
        "Unsupported EMBEDDING_PROVIDER. Use 'hash', 'huggingface', or 'openai'."
    )
