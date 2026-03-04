from langchain_groq import ChatGroq

from app.core.settings import get_settings


def get_groq_chat_model() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=settings.groq_temperature,
        timeout=settings.groq_timeout_seconds,
    )
