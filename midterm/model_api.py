"""Claude Sonnet through OpenRouter, for writing the analysis.

The key comes from OPENROUTER_API_KEY in the .env file one folder above this one and is never
printed. To use another model, set OPENROUTER_MODEL there.
"""
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)
MODEL = os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-5.5"
MAX_REPLY_TOKENS = 4000  # analyses use about 2,000; without a cap OpenRouter reserves credit for 65k
TRIES = 3


class ModelRequestError(Exception):
    """The model did not reply."""


def read_json(response):
    """The response body as a dict, even when the server answered with something else."""
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text[:200]}}


def error_message(data):
    error = data.get("error") or {}
    return (error.get("message") or "no message") if isinstance(error, dict) else str(error)


def request_model(messages):
    """Returns the model's reply message as a dict, with its text in "content"."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ModelRequestError(f"OPENROUTER_API_KEY is missing. Add it to {ENV_FILE}")
    body = {"model": MODEL, "messages": messages, "max_tokens": MAX_REPLY_TOKENS}
    for attempt in range(TRIES):
        try:
            response = requests.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
        except requests.RequestException as error:
            raise ModelRequestError(f"could not reach OpenRouter ({type(error).__name__})")
        if response.status_code != 429 or attempt == TRIES - 1:
            break
        time.sleep(2 ** (attempt + 1))  # rate limited: wait, then try again
    data = read_json(response)
    if response.status_code != 200 or "error" in data:
        raise ModelRequestError(f"HTTP {response.status_code}: {error_message(data)}")
    return data["choices"][0]["message"]


def parse_json_reply(text):
    """The JSON object in a reply, ignoring any text around it."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("the model did not reply with JSON")
    return json.loads(match.group(0))
