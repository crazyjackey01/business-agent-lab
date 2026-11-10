# Project knowledge across sessions

Create a small knowledge bundle about your lab. Use the lab's source files, not the fictional customer-support documents. No separate submission is required.

## 1. Open the lab root

Start Claude Code in `business-agent-lab/`, not inside `week-07/`.

```text
business-agent-lab/
├── CLAUDE.md                 Existing instructions, or a new file
├── knowledge/                The agent creates this folder
│   └── index.md              Start here in a later session
├── week-05/                  Source material
├── week-06/                  Source material
└── week-07/
    ├── knowledge-bundle-prompt.md
    └── okf-reference.md
```

The agent chooses the other pages. Your bundle does not need the same structure as your classmates' bundles.

## 2. Build the bundle

Paste the prompt from `week-07/knowledge-bundle-prompt.md`. Watch which source files Claude Code reads. Review file changes before accepting them.

## 3. Check one page

Open one generated page and follow a source link. Check one claim against the original file. Then check that the root `CLAUDE.md` keeps your existing instructions and adds a link to `knowledge/index.md`.

Saved information can be wrong or outdated. The maintenance instruction asks future agents to update affected pages. Check their work rather than assuming they comply.

## 4. Test a fresh session

Exit Claude Code with `/exit`, then run `claude` again from the lab root. Do not resume the previous conversation. Paste this prompt:

```text
Start with knowledge/index.md and read the pages relevant to my question. How do I run the Week 05 assistant, and where are its tools defined? Give the command from the lab root and cite the original files. Do not run the program or make API calls.
```

Inspect the file reads and source references. Did the session read the bundle? Does the answer agree with the original files? A correct answer alone does not show that the agent used the bundle. It could read the code directly.

The expected command is `python week-05/03_assistant.py` with the Week 05 environment active. Functions and tool definitions are in `week-05/tools.py`. `TOOLS` and `FUNCTIONS` register them in `week-05/03_assistant.py`.

## 5. Apply the idea to your project

Choose one project decision, convention, or instruction that a later session needs. Save that information with a link to its source. Do not copy every source file.
