# Create the lab knowledge bundle

Start Claude Code in `business-agent-lab/`, then paste the prompt below.

```text
Build a small Open Knowledge Format v0.2 bundle under knowledge/ so a new agent session can understand and work on this lab without a long explanation from me. Read week-07/okf-reference.md for the format.

Use the supplied README files, Python scripts, and exercise instructions in week-05/ and week-06/ as sources. Include useful information about project structure, running the programs, and project conventions. Student-created skills or reports are optional sources, not prerequisites. Leave .env, credentials, environments, caches, and week-07/rag-documents/ out of your inspection. You do not need to inspect the CSV or schedule data for this task.

Create knowledge/index.md as the entry point and a few short topic pages. Choose the organization yourself. Make the bundle a quick guide to finding information, not a copy of the documentation. Link to existing setup and exercise instructions rather than repeating them. Link important claims to the original files. Record supported facts and confirmed decisions only. Keep code and original project files as the source of truth. Describe commands as documented unless you actually ran them. Do not run programs, install packages, or make API calls for this task.

Preserve existing files and instructions. Add a short section to the root CLAUDE.md asking agents to start with knowledge/index.md, read relevant pages, and update affected pages when their work changes documented information. Keep this section short; it should point to the bundle, not copy it.

Check your file links. Finish with a short summary of what you created and any unresolved source conflicts.
```
