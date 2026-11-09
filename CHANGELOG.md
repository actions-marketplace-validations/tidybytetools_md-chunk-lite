# Changelog

What changed in md-chunk-lite, newest first.

## 1.1.1 - 2026-11-09

- Point Homepage, Documentation, and the MCP Registry websiteUrl at the official product page on [tidybytetools.github.io](https://tidybytetools.github.io/tools/markdown-chunker/).
- README: add a clear Links section (Website, Apify cloud version where it exists, Pro on Gumroad) and a short FAQ.

## 1.1.0 - 2026-11-09

- Fix: if the JSONL file was saved under a hidden folder like `.github/`, the artifact upload could miss it. The upload now includes hidden folders.
- New: a GitHub Action (`action.yml`). Add `uses: tidybytetools/md-chunk-lite@v1` to a workflow to chunk your Markdown docs on every push.
- The action saves all chunks to one JSONL file, can upload it as an artifact, and writes a report to the run page.
- It warns on the exact line when a section is too big for one chunk. Set `fail-on-split: "true"` to fail instead.
- The command-line tool and MCP server did not change.

## 1.0.0 - 2026-11-04

- First release.
- Splits Markdown into chunks by heading. Each chunk keeps its heading path, anchor and start and end line numbers.
- Big sections are split at blank lines. Tables repeat their header row and code blocks get their fence again when they must be split.
- Options: `--max-chars`, `--overlap-chars`, `--prefix-path`, `--outline` and `--json`.
- Free MCP server with four tools: `chunk_markdown`, `outline_markdown`, `get_section` and `save_chunks_jsonl`. Start it with `uvx md-chunk-lite mcp`.
- Needs Python 3.10 or newer.
