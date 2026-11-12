"""The ONLY file that talks to Ollama.

If you ever want to switch to another LLM, change this file only.
"""
from __future__ import annotations

import json
import re
from typing import Iterator

from pydantic import BaseModel

from core import config

_client = None


def get_client():
    global _client
    if _client is None:
        import ollama

        _client = ollama.Client(host=config.OLLAMA_HOST, timeout=config.LLM_TIMEOUT_SECONDS)
    return _client


def _require_model() -> str:
    if not config.OLLAMA_MODEL or config.OLLAMA_MODEL == "your-model-name":
        raise RuntimeError(
            "OLLAMA_MODEL is not set. Open the .env file and set OLLAMA_MODEL to a model "
            "you have pulled (run `ollama list` to see your models)."
        )
    return config.OLLAMA_MODEL


def check_ollama() -> tuple[bool, str]:
    """Check that Ollama is running and the chosen model is installed."""
    try:
        model = _require_model()
    except RuntimeError as error:
        return False, str(error)
    try:
        response = get_client().list()
    except Exception:
        return False, (
            f"Cannot reach Ollama at {config.OLLAMA_HOST}. "
            "Start the Ollama app (or run `ollama serve`) and refresh this page."
        )
    models = getattr(response, "models", None)
    if models is None and isinstance(response, dict):
        models = response.get("models", [])
    names = []
    for item in models or []:
        name = getattr(item, "model", None)
        if name is None and isinstance(item, dict):
            name = item.get("model") or item.get("name")
        if name:
            names.append(name)
    if model not in names and f"{model}:latest" not in names:
        return False, f"Model '{model}' is not installed. Run in a terminal: ollama pull {model}"
    return True, f"Ollama is running with model '{model}'."


def _chat_raw(messages: list[dict], temperature: float | None, schema: dict | None) -> str:
    response = get_client().chat(
        model=_require_model(),
        messages=messages,
        options={"temperature": config.TEMP_TEACH if temperature is None else temperature},
        format=schema,
        stream=False,
    )
    return response["message"]["content"]


def chat(messages: list[dict], temperature: float | None = None) -> str:
    """One normal text answer."""
    return _chat_raw(messages, temperature, None)


def stream_chat(messages: list[dict], temperature: float | None = None) -> Iterator[str]:
    """Yield the answer piece by piece (for a typing effect in Streamlit)."""
    stream = get_client().chat(
        model=_require_model(),
        messages=messages,
        options={"temperature": config.TEMP_TEACH if temperature is None else temperature},
        stream=True,
    )
    for part in stream:
        piece = part["message"]["content"]
        if piece:
            yield piece


def _parse_json(raw: str) -> dict:
    """Parse JSON from a model reply, tolerating code fences and extra text."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the model reply")
    return json.loads(text[start:end + 1])


def chat_validated(
    messages: list[dict],
    model_cls: type[BaseModel],
    temperature: float | None = None,
    retries: int = 2,
) -> BaseModel:
    """Ask for JSON that matches a Pydantic model; retry with the error if it does not."""
    schema = model_cls.model_json_schema()
    temp = config.TEMP_JSON if temperature is None else temperature
    conversation = list(messages)
    last_error: Exception | None = None
    for _ in range(retries + 1):
        raw = _chat_raw(conversation, temp, schema)
        try:
            return model_cls.model_validate(_parse_json(raw))
        except ValueError as error:  # JSON errors and Pydantic ValidationError both end here
            last_error = error
            conversation = conversation + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "That JSON was not valid for the schema: "
                    f"{str(error)[:400]}\nReturn corrected JSON only.",
                },
            ]
    raise RuntimeError(f"The model did not return valid JSON after {retries + 1} tries: {last_error}")