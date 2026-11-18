"""
Provider-agnostic LLM client (no SDKs needed — plain HTTPS via `requests`).

Choose the provider with environment variables:

    DARKLENS_PROVIDER = gemini | openai | anthropic | ollama
    DARKLENS_MODEL    = (optional) model name, e.g. gemini-2.5-flash
    GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY
    OLLAMA_HOST       = http://localhost:11434   (local open-weight models)

Every response is cached on disk (data/llm_cache) keyed by provider, model,
prompt and image, so re-running an evaluation costs nothing and is
reproducible.  The exact model string and date are logged with each call, as
recommended for LLM studies (model behaviour drifts between versions).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-5-5",
    "ollama": "qwen2.5vl:7b",
}
KEY_ENV = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class LLMError(RuntimeError):
    pass


def available_providers() -> dict[str, bool]:
    out = {p: bool(os.getenv(env)) for p, env in KEY_ENV.items()}
    out["ollama"] = bool(os.getenv("OLLAMA_HOST"))
    return out


def default_provider() -> str | None:
    p = os.getenv("DARKLENS_PROVIDER")
    if p:
        return p
    for name, ok in available_providers().items():
        if ok:
            return name
    return None


def _mime(img: bytes) -> str:
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img[:4] == b"RIFF" and img[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def extract_json(text: str):
    """Parse JSON from a model reply, tolerating ```json fences and prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = text.find(open_c), text.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Could not parse JSON from model output: {text[:300]}")


@dataclass
class LLMResponse:
    text: str
    data: object
    provider: str
    model: str
    latency_s: float
    cached: bool
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None,
                 cache_dir: str | Path = "data/llm_cache", temperature: float = 0.0, timeout: int = 120):
        self.provider = provider or default_provider()
        if not self.provider:
            raise LLMError("No LLM provider configured. Set DARKLENS_PROVIDER and the matching API key "
                           "(see README), or use offline mode.")
        if self.provider not in DEFAULT_MODELS:
            raise LLMError(f"Unknown provider {self.provider}")
        self.model = model or os.getenv("DARKLENS_MODEL") or DEFAULT_MODELS[self.provider]
        self.temperature = temperature
        self.timeout = timeout
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    # ------------------------------------------------------------------ public
    def complete_json(self, system: str, user: str, images: list[bytes] | None = None,
                      max_tokens: int = 4096, retries: int = 4) -> LLMResponse:
        images = images or []
        key = hashlib.sha256(json.dumps([self.provider, self.model, system, user, self.temperature]).encode()
                             + b"".join(hashlib.sha256(i).digest() for i in images)).hexdigest()
        cpath = self.cache_dir / f"{key}.json"
        if cpath.exists():
            c = json.loads(cpath.read_text(encoding="utf-8"))
            return LLMResponse(c["text"], extract_json(c["text"]), self.provider, self.model, 0.0, True,
                               c.get("input_tokens"), c.get("output_tokens"))

        last = None
        for attempt in range(retries):
            try:
                t0 = time.time()
                text, itok, otok = getattr(self, f"_call_{self.provider}")(system, user, images, max_tokens)
                lat = time.time() - t0
                data = extract_json(text)
                self.calls += 1
                self.usage["input_tokens"] += itok or 0
                self.usage["output_tokens"] += otok or 0
                cpath.write_text(json.dumps({"text": text, "provider": self.provider, "model": self.model,
                                             "date": time.strftime("%Y-%m-%d"), "input_tokens": itok,
                                             "output_tokens": otok}, ensure_ascii=False), encoding="utf-8")
                return LLMResponse(text, data, self.provider, self.model, lat, False, itok, otok)
            except (requests.RequestException, LLMError) as exc:
                last = exc
                wait = 2 ** attempt * 3
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (400, 401, 403, 404):
                    break  # not retryable
                time.sleep(wait)
        raise LLMError(f"{self.provider} call failed: {last}")

    # -------------------------------------------------------------- providers
    def _post(self, url, headers, body):
        r = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if r.status_code >= 400:
            err = requests.HTTPError(f"{r.status_code}: {r.text[:500]}")
            err.response = r
            raise err
        return r.json()

    def _call_gemini(self, system, user, images, max_tokens):
        key = os.environ["GEMINI_API_KEY"]
        parts = [{"text": user}] + [
            {"inline_data": {"mime_type": _mime(i), "data": base64.b64encode(i).decode()}} for i in images]
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        d = self._post(url, {"x-goog-api-key": key, "Content-Type": "application/json"}, body)
        try:
            text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no content: {json.dumps(d)[:300]}")
        u = d.get("usageMetadata", {})
        return text, u.get("promptTokenCount"), u.get("candidatesTokenCount")

    def _call_openai(self, system, user, images, max_tokens):
        key = os.environ["OPENAI_API_KEY"]
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": f"data:{_mime(i)};base64,{base64.b64encode(i).decode()}"}}
            for i in images]
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        d = self._post(f"{base}/chat/completions", {"Authorization": f"Bearer {key}"}, body)
        u = d.get("usage", {})
        return d["choices"][0]["message"]["content"], u.get("prompt_tokens"), u.get("completion_tokens")

    def _call_anthropic(self, system, user, images, max_tokens):
        key = os.environ["ANTHROPIC_API_KEY"]
        content = [{"type": "image", "source": {"type": "base64", "media_type": _mime(i),
                                                "data": base64.b64encode(i).decode()}} for i in images]
        content.append({"type": "text", "text": user + "\n\nRespond with JSON only."})
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": self.temperature,
                "system": system, "messages": [{"role": "user", "content": content}]}
        d = self._post("https://api.anthropic.com/v1/messages",
                       {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       body)
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage", {})
        return text, u.get("input_tokens"), u.get("output_tokens")

    def _call_ollama(self, system, user, images, max_tokens):
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        msg = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.b64encode(i).decode() for i in images]
        body = {"model": self.model, "stream": False, "format": "json",
                "options": {"temperature": self.temperature, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, msg]}
        d = self._post(f"{host}/api/chat", {}, body)
        return d["message"]["content"], d.get("prompt_eval_count"), d.get("eval_count")
