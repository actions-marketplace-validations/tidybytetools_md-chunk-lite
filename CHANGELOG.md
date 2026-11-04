# Changelog

What changed in md-chunk-lite, newest first.

## 1.0.0 - 2026-11-04

- First release.
- Splits Markdown into chunks by heading. Each chunk keeps its heading path, anchor and start and end line numbers.
- Big sections are split at blank lines. Tables repeat their header row and code blocks get their fence again when they must be split.
- Options: `--max-chars`, `--overlap-chars`, `--prefix-path`, `--outline` and `--json`.
- Free MCP server with four tools: `chunk_markdown`, `outline_markdown`, `get_section` and `save_chunks_jsonl`. Start it with `uvx md-chunk-lite mcp`.
- Needs Python 3.10 or newer.
