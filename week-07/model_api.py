"""OpenRouter access. Never print credentials or raw provider errors."""

import math
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://openrouter.ai/api/v1"


class DemoError(Exception):
    """A safe, student-readable error."""


def load_key():
    # In the student lab, .env is one level above week-07/.
    # Ancestor lookup also permits instructor testing in the course repository.
    for folder in Path(__file__).resolve().parents:
        env_file = folder / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
            break

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise DemoError("Add OPENROUTER_API_KEY to the lab-root .env file.")
    return key


def redact(text):
    key = os.getenv("OPENROUTER_API_KEY", "")
    return text.replace(key, "[REDACTED]") if key else text


class OpenRouter:
    def __init__(self):
        self.key = load_key()
        self.session = requests.Session()

        # Record request timings and avoid repeating catalog checks.
        self.calls = []
        self.checked = set()

    def require_free(self, model, kind):
        # Check both the model name and the catalog price before sending data.
        if not model.endswith(":free"):
            raise DemoError("Only explicit :free model IDs are allowed.")
        if (model, kind) in self.checked:
            return

        try:
            response = self.session.get(
                BASE_URL + "/models",
                params={"output_modalities": kind},
                timeout=30,
            )
            response.raise_for_status()
            models = response.json()["data"]
            entry = next(item for item in models if item["id"] == model)
            pricing = entry["pricing"]

            if not {"prompt", "completion"} <= pricing.keys():
                raise DemoError("The catalog does not confirm free input and output.")
            if any(float(value) != 0 for value in pricing.values()):
                raise DemoError("The catalog lists a nonzero price. Request blocked.")
        except (requests.RequestException, ValueError, KeyError, StopIteration):
            raise DemoError("Cannot verify the free model in the current catalog.") from None

        self.checked.add((model, kind))

    def post(self, endpoint, model, payload, kind):
        self.require_free(model, kind)

        body = {
            "model": model,
            # No paid provider or automatic fallback is permitted.
            "provider": {
                "max_price": {"prompt": 0, "completion": 0},
                "allow_fallbacks": False,
            },
            **payload,
        }

        started = time.perf_counter()
        try:
            response = self.session.post(
                BASE_URL + endpoint,
                headers={"Authorization": f"Bearer {self.key}"},
                json=body,
                timeout=90,
            )
            data = response.json()
        except (requests.RequestException, ValueError):
            raise DemoError(
                "OpenRouter did not return a usable response. Try again later."
            ) from None

        if response.status_code != 200 or "error" in data:
            # Raw provider messages can contain request information. Do not print them.
            raise DemoError(
                f"OpenRouter HTTP {response.status_code}. Check availability or request limits. "
                "No paid fallback was attempted."
            )

        # Keep useful run details without storing the API key.
        self.calls.append(
            {
                "endpoint": endpoint,
                "requested_model": model,
                "returned_model": data.get("model"),
                "provider": data.get("provider"),
                "seconds": round(time.perf_counter() - started, 3),
                "usage": data.get("usage", {}),
            }
        )
        return data

    def embed(self, texts, model, input_type):
        # Documents and questions use the same model with different input types.
        data = self.post(
            "/embeddings",
            model,
            {"input": texts, "input_type": input_type, "encoding_format": "float"},
            "embeddings",
        )

        try:
            # Match the returned vectors to the order of the input texts.
            rows = sorted(data["data"], key=lambda item: item["index"])
            if [row["index"] for row in rows] != list(range(len(texts))):
                raise ValueError

            vectors = [row["embedding"] for row in rows]
            if not vectors or not vectors[0]:
                raise ValueError

            dimension = len(vectors[0])
            if any(
                len(v) != dimension or not all(math.isfinite(x) for x in v)
                for v in vectors
            ):
                raise ValueError
            return vectors
        except (KeyError, TypeError, ValueError):
            raise DemoError("The embedding response has invalid vectors.") from None

    def answer(self, messages, model):
        # Send the assembled conversation to the answer-generating model.
        data = self.post(
            "/chat/completions",
            model,
            {
                "messages": messages,
                "temperature": 0,
                "max_tokens": 1400,
                "reasoning": {"enabled": False},
            },
            "text",
        )

        try:
            choice = data["choices"][0]

            # Reject incomplete output instead of presenting it as a full answer.
            if choice.get("finish_reason") == "length":
                raise DemoError("The answer hit its output limit. Do not use the partial answer.")

            text = choice["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            return redact(text.strip())
        except (KeyError, TypeError, ValueError, IndexError):
            raise DemoError("The chat model returned no usable answer.") from None
