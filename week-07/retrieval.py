"""Split Markdown sections, store embeddings, and rank by cosine similarity."""

import hashlib
import json
import math
import re

from model_api import DemoError
from settings import DOCUMENTS, INDEX_FILE


def load_passages(folder=DOCUMENTS):
    passages = []

    for file in sorted(folder.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix("# ")

        # Each second-level Markdown heading starts a passage in this example.
        for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
            heading, _, content = section.partition("\n")
            passages.append(
                {
                    "id": heading.split()[0],
                    "source": file.name,
                    "heading": heading,
                    "text": f"{title}\n{heading}\n{content.strip()}",
                }
            )

    if not passages or len({p["id"] for p in passages}) != len(passages):
        raise DemoError("Source sections are missing or have duplicate identifiers.")
    return passages


def fingerprint(passages):
    # This identifier changes when the document passages change.
    serialized = json.dumps(passages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def index_text(data):
    # Put each field on its own line, but keep each long vector on one line.
    text = json.dumps({**data, "vectors": None}, indent=2, ensure_ascii=False)
    vectors = ",\n    ".join(json.dumps(v) for v in data["vectors"])
    return text.replace('"vectors": null', f'"vectors": [\n    {vectors}\n  ]') + "\n"


def build_index(client, model, path=INDEX_FILE):
    passages = load_passages()
    vectors = client.embed([p["text"] for p in passages], model, "passage")

    # Keep passage text and source information alongside its embedding.
    data = {
        "schema": 1,
        "embedding_model": model,
        "fingerprint": fingerprint(passages),
        "passages": passages,
        "vectors": vectors,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(index_text(data), encoding="utf-8")
    return data


def read_index(model, path=INDEX_FILE):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        # Rebuild rather than mixing old embeddings with changed sources.
        if (
            data["schema"] != 1
            or data["embedding_model"] != model
            or data["fingerprint"] != fingerprint(load_passages())
            or len(data["vectors"]) != len(data["passages"])
            or fingerprint(data["passages"]) != data["fingerprint"]
        ):
            raise ValueError

        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise DemoError(
            "The index is missing or out of date. Run 01_build_index.py."
        ) from None


def cosine(a, b):
    # Compare the directions of the question and passage vectors.
    if len(a) != len(b) or not a:
        raise DemoError("Vector dimensions do not match. Rebuild the index.")

    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if not norm_a or not norm_b:
        raise DemoError("A vector has zero length.")

    return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


def rank_passages(index, query_vector, top_k, min_score):
    if top_k < 1 or not -1 <= min_score <= 1:
        raise DemoError("top_k must be positive; min_score must be between -1 and 1.")

    # Score every passage, then put the most similar passages first.
    ranked = [
        {**passage, "score": cosine(query_vector, vector)}
        for passage, vector in zip(index["passages"], index["vectors"])
    ]
    ranked.sort(key=lambda item: (-item["score"], item["id"]))

    # Apply the score filter before keeping at most top_k results.
    return [p for p in ranked if p["score"] >= min_score][:top_k]


def retrieve(client, index, question, top_k, min_score):
    # Only the question needs a new embedding here. Passage vectors are cached.
    vector = client.embed([question], index["embedding_model"], "query")[0]
    return rank_passages(index, vector, top_k, min_score)
