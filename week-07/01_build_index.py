"""Prepare document embeddings once. Rebuild after document/model changes."""

from model_api import DemoError, OpenRouter
from retrieval import build_index
from settings import EMBEDDING_MODEL


def main():
    # Read the documents, embed their sections, and save the index locally.
    client = OpenRouter()
    index = build_index(client, EMBEDDING_MODEL)

    # This step prepares retrieval. It does not ask the chat model a question.
    print(f"Embedded {len(index['passages'])} sections.")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Vector dimension: {len(index['vectors'][0])}")
    print("Saved .cache/index.json. No answer model was called.")
    print(f"Embedding request: {client.calls[-1]['seconds']} seconds")


if __name__ == "__main__":
    try:
        main()
    except DemoError as error:
        # Show a short message instead of a full Python traceback.
        raise SystemExit(str(error)) from None
