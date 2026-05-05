import httpx
from config import GROQ_API_KEY, GROQ_CHAT_COMPLETIONS_URL, LLM_MODEL


def has_llm() -> bool:
    return bool(GROQ_API_KEY and GROQ_API_KEY.strip())


async def chat_complete(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.2,
    *,
    max_tokens: int | None = None,
    response_format_json: bool = False,
) -> str:
    if not has_llm():
        raise RuntimeError('GROQ_API_KEY is not configured')

    payload = {
        'model': model or LLM_MODEL,
        'messages': messages,
        'temperature': temperature,
    }
    if max_tokens is not None:
        payload['max_tokens'] = max_tokens
    if response_format_json:
        payload['response_format'] = {'type': 'json_object'}

    headers = {
        'Authorization': f'Bearer {GROQ_API_KEY}',
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(GROQ_CHAT_COMPLETIONS_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    choices = data.get('choices') or []
    if not choices:
        return ''
    msg = choices[0].get('message') or {}
    return (msg.get('content') or '').strip()
