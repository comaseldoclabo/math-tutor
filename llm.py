"""Appel du modèle de langage (API Messages d'Anthropic). Sans clé : LLMUnavailable."""
import httpx

from ..config import settings


class LLMUnavailable(RuntimeError):
    pass


def _normalize(messages: list[dict]) -> list[dict]:
    """L'API exige : alternance user/assistant, début par 'user'."""
    out: list[dict] = []
    for m in messages:
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + m["content"]
        else:
            out.append({"role": m["role"], "content": m["content"]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def complete(system: str, messages: list[dict], max_tokens: int = 900) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise LLMUnavailable("ANTHROPIC_API_KEY manquante")
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": _normalize(messages)},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        raise LLMUnavailable(str(exc)) from exc
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise LLMUnavailable("réponse vide")
    return text
