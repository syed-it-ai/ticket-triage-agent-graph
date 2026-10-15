"""
A tiny, provider-agnostic client for Groq and Gemini, both free.
Built on plain `requests` rather than an SDK, so the actual HTTP
request is visible. Reused from the same pattern proven across this
project's wider 15-stage curriculum.
"""

import os
import time
import requests
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    raw: dict


class LLMClient:
    """One object, one provider. Configuration comes from environment
    variables so no key ever ends up hardcoded in a committed file."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        self.api_key = os.getenv(f"{self.provider.upper()}_API_KEY", "")
        self.model = os.getenv(f"{self.provider.upper()}_MODEL", self._default_model())
        if not self.api_key:
            raise ValueError(f"No API key found. Set {self.provider.upper()}_API_KEY in your .env file.")

    def _default_model(self) -> str:
        # gemini-2.5-flash retires October 16, 2026, confirmed directly
        # against Google's own deprecation schedule, so gemini-3.5-flash
        # is the current correct default, not 2.5.
        defaults = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.5-flash"}
        if self.provider not in defaults:
            raise ValueError(f"Unknown provider '{self.provider}'. Pick one of: {', '.join(defaults)}")
        return defaults[self.provider]

    def _redact_key(self, message: str) -> str:
        """Gemini puts the API key directly in the request URL, which
        means it leaks into any raw error message by default, including
        this project's own retry log and traceback output, confirmed
        directly from a real run. This strips it before the message
        ever reaches a print statement or an exception string."""
        if self.api_key:
            message = message.replace(self.api_key, "[REDACTED]")
        return message

    def chat(self, prompt: str, temperature: float = 0.3, max_tokens: int = 400,
             max_retries: int = 5) -> LLMResponse:
        """
        Retries on 503 (service temporarily unavailable) and 429 (rate
        limited), both transient server-side conditions, not request
        errors. A 400 or 401 fails immediately instead, since retrying
        a genuinely bad request or a bad key wastes time and never
        succeeds no matter how many attempts it gets.
        """
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if self.provider == "groq":
                    return self._chat_groq(prompt, temperature, max_tokens)
                if self.provider == "gemini":
                    return self._chat_gemini(prompt, temperature, max_tokens)
                raise ValueError(f"Unhandled provider '{self.provider}'")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status not in (503, 429):
                    raise ValueError(self._redact_key(str(e)))  # fail immediately, key-safe
                last_error = ValueError(self._redact_key(str(e)))
                if attempt < max_retries:
                    # A 429 is a rate limit. A newly-released model's
                    # free tier, confirmed directly in a real run, can
                    # have a quota tight enough that even 20s and 40s
                    # waits aren't always enough, so this also grows
                    # max_retries' effective ceiling for 429 specifically.
                    wait = 30 * attempt if status == 429 else 2 ** attempt
                    print(f"  ({status} from {self.provider}, retrying in {wait}s, attempt {attempt}/{max_retries})")
                    time.sleep(wait)
        raise last_error

    def _chat_groq(self, prompt: str, temperature: float, max_tokens: int) -> LLMResponse:
        """
        openai/gpt-oss-120b is a reasoning model, confirmed directly in
        this project's own Stage 4 testing. reasoning_effort set to low
        keeps it from spending the shared token budget on deep internal
        reasoning for tasks that just need structured extraction, the
        same class of failure just confirmed and fixed on the Gemini side.
        """
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_effort": "low",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        content = data["choices"][0]["message"].get("content")
        if not content:
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            raise ValueError(
                f"Groq returned no answer text (finish_reason={finish_reason}). "
                f"Likely the reasoning budget consumed all of max_tokens. Raise max_tokens on this call."
            )
        return LLMResponse(
            text=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw=data,
        )

    def _chat_gemini(self, prompt: str, temperature: float, max_tokens: int) -> LLMResponse:
        """
        Confirmed directly from Google's own documentation and multiple
        independently reported cases: Gemini's thinking models (the 2.5
        and 3.x families) spend tokens reasoning before answering, and
        those thinking tokens come out of the SAME max_tokens budget as
        the visible answer. A small max_tokens, fine for a one-word
        classification, can let thinking consume the entire budget and
        leave zero room for the actual answer, finishReason: MAX_TOKENS,
        content with no "parts" key at all. thinkingBudget: 0 disables
        this for tasks that don't need it, confirmed as supported on
        models that permit disabling thinking.
        """
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        response = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usageMetadata", {})

        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts")
        if not parts:
            finish_reason = candidate.get("finishReason", "unknown")
            hint = (
                " This model spent its entire token budget thinking and had nothing left "
                "to answer with. Raise max_tokens on this call."
                if finish_reason == "MAX_TOKENS" else ""
            )
            raise ValueError(f"Gemini returned no answer text (finishReason={finish_reason}).{hint}")

        return LLMResponse(
            text=parts[0]["text"],
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            raw=data,
        )
