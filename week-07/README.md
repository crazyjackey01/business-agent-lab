# Week 07, context and retrieval

Use a small RAG program to answer support questions using a fictional company's internal documents. All company information is invented. Use no real customer records or private company data. Free model providers may keep the text you send.

## Setup

Extract `week-07.zip` into your existing `business-agent-lab/` folder.

```text
business-agent-lab/
├── .env                    Your existing OpenRouter key, never commit
├── .gitignore              Must exclude .env
├── week-05/
├── week-06/
└── week-07/
    ├── 01_build_index.py
    ├── 02_ask.py
    ├── settings.py
    └── rag-documents/
```

Open a terminal at `business-agent-lab/`. Activate your Week 05 Python environment, then install the required packages.

```bash
python3 -m pip install -r week-07/requirements.txt
```

Reuse `OPENROUTER_API_KEY` in the lab-root `.env`. Do not paste the key into a script or terminal command. Before committing work, check that Git ignores the file.

```bash
git check-ignore .env
```

The command must print `.env`. If it prints nothing, add `.env` to the lab-root `.gitignore` before continuing. If you already committed a key, contact the instructor. An ignore entry does not remove it from Git history.

## Prepare the documents

```bash
python3 week-07/01_build_index.py
```

The script reads the four Markdown files, splits them at section headings, and sends the passages to a free embedding model through OpenRouter. It saves their vectors, text, and source identifiers in `week-07/.cache/index.json`. You do not need a vector database.

Run this preparation again after changing a document or the embedding model. The answer script rejects an outdated index.

## Inspect the evidence and answer

```bash
python3 week-07/02_ask.py
```

The default question is about a wrong-item delivery. The script embeds the question, ranks passages, and prints the selected text. Read the passages, then press Enter to request an answer.

Compare with the same model and question without company documents.

```bash
python3 week-07/02_ask.py --no-context
```

Without company documents, the model can say that it does not know the policy. That is an appropriate answer.

## Exercise

1. Run the default question and inspect the evidence and citations.
2. Open `settings.py`. Change `TOP_K` to `1`, save, and rerun the same question. Which evidence disappears? Restore the original value after comparing.
3. Ask a question not answered in the documents.

```bash
python3 week-07/02_ask.py "What discount does Soundway give student customers?"
```

4. Write a support question of your own. Put it in quotation marks after the script name, as in the command above. Check the answer against the source sections.

A similar passage may still lack the answer. If no passage passes the score filter, the program stops without calling the answer model. Use a threshold of `1.0` to see this empty-result case. It is not a recommended setting for other uses.

```bash
python3 week-07/02_ask.py "What discount does Soundway give student customers?" --min-score 1.0
```

## Reading the code

| File | Purpose |
| --- | --- |
| `settings.py` | Model names, passage count, score filter, and default question |
| `01_build_index.py` | Prepare document embeddings |
| `retrieval.py` | Split sections, validate the index, and calculate similarity |
| `02_ask.py` | Retrieve, pause, assemble model input, and generate an answer |
| `model_api.py` | Load the key and call OpenRouter without a paid fallback |

Both model IDs must end in `:free`, and both models must have zero listed prices. Availability can change. HTTP 429 means a request limit or lack of provider capacity. If the free service fails, use the instructor's recording rather than a paid model.

The assistant recommends actions. It does not look up orders, check stock, or issue refunds. All four files can fit in a single request. We use them to study how retrieval works, not to show that retrieval is necessary for a collection this small.

This activity has no separate submission. Continue with [the knowledge-bundle exercise](knowledge-bundle-exercise.md) when instructed. It uses the wider lab's source files, not the fictional store documents.
