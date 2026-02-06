from openai import OpenAI
from app.core.deps import get_openai_client


class AIService:
    def __init__(self):
        self.client: OpenAI = get_openai_client()

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""


def get_ai_service() -> AIService:
    return AIService()
