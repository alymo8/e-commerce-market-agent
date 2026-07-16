import json
import re

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.2,
        timeout=settings.request_timeout,
    )


def extract_json_object(text: str) -> dict:
    # Assumes a single JSON object per reply; greedy match spans nested braces.
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in LLM reply")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in LLM reply: {exc}") from exc


def complete_json(system: str, user: str) -> dict:
    llm = get_llm()
    reply = llm.invoke([("system", system), ("human", user)])
    content = reply.content if isinstance(reply.content, str) else str(reply.content)
    return extract_json_object(content)
