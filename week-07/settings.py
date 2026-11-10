"""Classroom settings. Change TOP_K for the exercise."""

from pathlib import Path

# Paths are relative to this script, not the terminal's current folder.
HERE = Path(__file__).resolve().parent
DOCUMENTS = HERE / "rag-documents"
INDEX_FILE = HERE / ".cache" / "index.json"

# One model creates embeddings; the other generates the answer.
CHAT_MODEL = "nvidia/nemotron-3.5-super-vl:free"
EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b:free"

# Return at most this many passages after applying the score filter.
TOP_K = 5

# This is a model/collection-specific setting, not a universal cutoff.
# Inspect the scores before choosing a different value.
MIN_SCORE = 0.0

# Use the same question when comparing retrieval settings.
MAIN_QUESTION = (
    "A customer ordered Wave H1 headphones but received a different product. "
    "The order arrived two calendar days ago. The customer opened the box and "
    "needs the headphones by Friday. Today is Tuesday at 11:00 KST, and this "
    "week has no public holidays. What should I do, and can I promise delivery "
    "by Friday?"
)
