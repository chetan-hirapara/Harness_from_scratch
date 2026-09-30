"""Provider-agnostic LLM client over the OpenAI-compatible Chat Completions API.

Defaults to a local Ollama server (http://localhost:11434/v1). To target OpenAI,
OpenRouter, or any OpenAI-compatible provider, change base_url + api_key + model
(via the spec `llm:` section or LLM_* environment variables). Every call is
best-effort: on any failure the helpers return None so callers fall back to
deterministic keyword/template logic.
"""

import os
import re
import json
from typing import Any, Dict, Optional

try:
    from openai import AsyncOpenAI
except ImportError:  # openai is optional; tools fall back to keyword/template logic
    AsyncOpenAI = None


_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)

_config: Dict[str, Any] = {
    "enabled": True,
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen3.8:latest",
    "temperature": 0.0,
    "timeout": 60.0,
    "max_tokens": 2048,
    # Ollama-native flag to skip qwen3 reasoning; ignored/retried-away for other providers.
    "extra_body": {"think": False},
}

_client: Optional["AsyncOpenAI"] = None


def _apply_env() -> None:
    _config["base_url"] = os.environ.get("LLM_BASE_URL", _config["base_url"])
    _config["api_key"] = os.environ.get("LLM_API_KEY", _config["api_key"])
    _config["model"] = os.environ.get("LLM_MODEL", _config["model"])
    if "LLM_ENABLED" in os.environ:
        _config["enabled"] = os.environ["LLM_ENABLED"].lower() not in ("0", "false", "no", "off")


def configure(cfg: Optional[Dict[str, Any]]) -> None:
    """Merge spec config, apply env overrides, and rebuild the client lazily."""
    global _client
    if cfg:
        for key in ("enabled", "base_url", "api_key", "model", "temperature",
                    "timeout", "max_tokens", "extra_body"):
            if key in cfg and cfg[key] is not None:
                _config[key] = cfg[key]
    _apply_env()
    _client = None


def is_enabled() -> bool:
    return bool(_config["enabled"] and AsyncOpenAI is not None)


def _get_client() -> Optional["AsyncOpenAI"]:
    global _client
    if not is_enabled():
        return None
    if _client is None:
        _client = AsyncOpenAI(
            base_url=_config["base_url"],
            api_key=_config["api_key"],
            timeout=_config["timeout"],
        )
    return _client


async def _chat(system: str, user: str, json_mode: bool) -> Optional[str]:
    client = _get_client()
    if client is None:
        return None

    kwargs: Dict[str, Any] = {
        "model": _config["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": _config["temperature"],
        "max_tokens": _config["max_tokens"],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    extra_body = _config.get("extra_body") or None
    try:
        resp = await client.chat.completions.create(**kwargs, extra_body=extra_body)
    except Exception:
        # Retry once without provider-specific extra_body (non-Ollama providers reject it).
        if extra_body:
            try:
                resp = await client.chat.completions.create(**kwargs)
            except Exception:
                return None
        else:
            return None

    try:
        return resp.choices[0].message.content
    except (AttributeError, IndexError):
        return None


def _strip_think(text: str) -> str:
    return _THINK_TAG_RE.sub("", text).strip()


async def chat_text(system: str, user: str) -> Optional[str]:
    """Return a plain-text completion, or None if the LLM is unavailable/failed."""
    content = await _chat(system, user, json_mode=False)
    if content is None:
        return None
    cleaned = _strip_think(content)
    return cleaned or None


async def chat_json(system: str, user: str) -> Optional[Dict[str, Any]]:
    """Return a parsed JSON object completion, or None on any failure."""
    content = await _chat(system, user, json_mode=True)
    if content is None:
        return None
    cleaned = _strip_think(content)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        match = _JSON_OBJ_RE.search(cleaned)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
