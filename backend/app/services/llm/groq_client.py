from types import SimpleNamespace

from app.core.settings import get_settings


def get_groq_chat_model():
    from groq import AsyncGroq

    settings = get_settings()
    client = AsyncGroq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
    )

    class GroqChatAdapter:
        def __init__(self) -> None:
            self.model_name = settings.groq_model
            self.temperature = settings.groq_temperature

        async def ainvoke(self, prompt: str):
            completion = await client.chat.completions.create(
                model=self.model_name,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            message = completion.choices[0].message.content or ""
            return SimpleNamespace(content=message)

    return GroqChatAdapter()
