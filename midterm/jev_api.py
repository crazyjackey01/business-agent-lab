"""Ask Jev (TypeSafe's decision model) typed questions through OpenCode Zen.

Jev writes no text. It reads a "state" and answers questions whose possible
answers we fix in advance: yes/no ("noul"), one of a list ("choice"), or a level
("score"), each with probabilities. So it cannot invent an answer, which makes it
a good independent checker for claims the text model wrote.

The key comes from OPENCODE_API_KEY in the project's .env file.
"""
import os
import time

import requests

import model_api  # loads the .env file

ENDPOINT = "https://opencode.ai/zen/v1/systemone"
MODEL = os.getenv("JEV_MODEL") or "jev-1.13-free"
MAX_QUESTIONS = 100  # per request: Jev refuses requests over ~60k tokens (about 150 intent questions)


class JevError(Exception):
    """Jev did not answer."""


def available():
    return bool(os.getenv("OPENCODE_API_KEY", "").strip())


def ask(state, questions):
    """Send one state and a dict of questions; return the dict of answers.

    Example question: {"type": "choice", "instructions": "...",
                       "criteria": {"label": "what the label means", ...}}
    Example answer:   {"type": "choice", "choice": "label", "confidence": 0.9,
                       "probabilities": {"label": 0.9, ...}}
    """
    answers = {}
    ids = list(questions)
    for start in range(0, len(ids), MAX_QUESTIONS):
        batch = {q: questions[q] for q in ids[start:start + MAX_QUESTIONS]}
        for attempt in range(4):
            try:
                response = requests.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {os.getenv('OPENCODE_API_KEY', '').strip()}"},
                    json={"model": MODEL, "state": state, "questions": batch},
                    timeout=60,
                )
            except requests.RequestException as error:
                raise JevError(f"could not reach Jev ({type(error).__name__})")
            if response.status_code != 429 or attempt == 3:
                break
            time.sleep(1.5 * 2 ** attempt)  # the free tier rejects bursts; wait and retry
        data = model_api.read_json(response)
        if response.status_code != 200 or "answers" not in data:
            raise JevError(f"HTTP {response.status_code}: {model_api.error_message(data)}")
        answers.update(data["answers"])
    return answers
