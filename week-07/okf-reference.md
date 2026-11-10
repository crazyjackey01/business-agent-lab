# OKF reference for this exercise

This is a short teaching guide to Open Knowledge Format v0.2, not a replacement for the specification. Checked on 2 November 2026 against [Google Cloud's specification](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/ad30107c31c06aec8a7d5636e0d1058118604e6f/SPEC.md), sections 3, 4, 6, 8, and 12.

## Files

A bundle is a directory of UTF-8 Markdown files. Choose a small structure that helps a new session navigate the lab.

- `index.md` lists pages with Markdown links and short descriptions. It is a reserved index filename, not a concept page.
- The bundle-root `index.md` can have `okf_version: "0.2"` in YAML frontmatter. Index files otherwise have no frontmatter.
- Every topic page is a concept. It starts with YAML frontmatter containing `type`. A descriptive type such as `Reference` or `Playbook` is sufficient.
- `title` and `description` are recommended. Other metadata is optional. There are no required body headings.
- `log.md` is reserved for an optional change log. This exercise does not require one.

Example concept metadata, not a required page structure:

```yaml
---
type: Reference
title: Lab programs
description: Where the lab programs are defined and how to run them.
---
```

## Links and evidence

Ordinary relative Markdown links are valid. Resolve them from the page containing the link. For example, a concept directly under `knowledge/` can link to `../week-05/tools.py`. Adjust the path if the concept is in a subdirectory.

Link important claims to original source files. The OKF `sources` metadata is optional; plain body links are sufficient for this exercise's source-checking activity. Do not claim a page has been human-reviewed or that a command has been tested unless that actually happened.

The format does not select passages, run searches, or load every page into context. An agent still needs to find and read relevant pages. A graph of Markdown links is not automatically a GraphRAG implementation.
