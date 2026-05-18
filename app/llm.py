from openai import OpenAI
from .providers.settings_provider import get_api_key_sync


def generate_ai_reply(user_text: str) -> str:
    """
    Call OpenAI chat completion to produce a short, friendly response.
    """
    client = OpenAI(api_key=get_api_key_sync("openai"))

    system_prompt = "You are a polite assistant on a phone call. Keep responses under 20 words."
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text.strip() if user_text else ""},
        ],
        temperature=0.7,
        max_tokens=60,
    )
    content = completion.choices[0].message.content or ""
    return content.strip()


