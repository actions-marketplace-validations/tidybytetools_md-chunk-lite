<p>
  <a href="https://github.com/tidybytetools">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/tidybytetools/md-chunk-lite/main/assets/tidybytetools-lockup-dark.png">
      <img alt="Tidy Byte Tools" src="https://raw.githubusercontent.com/tidybytetools/md-chunk-lite/main/assets/tidybytetools-lockup-light.png" height="44">
    </picture>
  </a>
</p>

# md-chunk-lite

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/tidybytetools/md-chunk-lite/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP server](https://img.shields.io/badge/MCP-stdio-purple.svg)](#use-it-from-claude-desktop-or-cursor-mcp)
[![Tests](https://github.com/tidybytetools/md-chunk-lite/actions/workflows/tests.yml/badge.svg)](https://github.com/tidybytetools/md-chunk-lite/actions/workflows/tests.yml)

Free tool that splits Markdown into chunks by heading. Every chunk knows its heading path and the line numbers it came from.
Need PDF, Word or web page files turned into chunks (with page numbers for PDFs), or whole folders? The paid doc2md does that: **[doc2md on Gumroad](https://tidybyte.gumroad.com/l/frlkv)**

Good for AI search (RAG), embeddings, and docs bots. Plain code, not AI, so the same file always gives the same chunks. Runs on your own computer. MIT license. Python 3.10 or newer, on Windows, Mac and Linux.

<!-- mcp-name: io.github.tidybytetools/md-chunk-lite -->

## Install

```
pip install md-chunk-lite
```

Or use pipx, which keeps it in its own space:

```
pipx install md-chunk-lite
```

Want the newest code from GitHub instead?

```
pip install git+https://github.com/tidybytetools/md-chunk-lite
```

## Use it

```
md-chunk-lite guide.md                     # writes guide.chunks.jsonl
md-chunk-lite docs/*.md -o all.jsonl       # many files into one file
md-chunk-lite guide.md -o -                # print the chunks on screen
md-chunk-lite guide.md --max-chars 800     # smaller chunks
md-chunk-lite guide.md --outline           # just show the headings
cat guide.md | md-chunk-lite -             # read from stdin
```

Example run:

```
Saved: guide.chunks.jsonl  (7 chunks, biggest 151 chars)
```

Each line of the `.jsonl` file is one chunk:

```json
{
  "id": "guide.md#3",
  "source": "guide.md",
  "index": 3,
  "heading_path": ["Garden Guide", "Planting", "Tomatoes"],
  "heading_level": 3,
  "anchor": "tomatoes",
  "start_line": 16,
  "end_line": 24,
  "part": 1,
  "parts": 1,
  "chars": 151,
  "text": "### Tomatoes\n\nPlant tomatoes after the last frost. Give them sun.\n\n```python\n..."
}
```

- `heading_path`: all the headings above this chunk, from the top.
- `anchor`: the `#link` GitHub makes for that heading, so you can link straight to it.
- `start_line` and `end_line`: where the chunk is in the file (the first line is 1).
- `part` and `parts`: a big section is split into parts. `part 2, parts 3` means the 2nd of 3.
- `chars`: how long `text` is.

`--outline` prints the headings:

```
Garden Guide  [line 8, #garden-guide, 14 chars]
  Tools  [line 10, #tools, 47 chars]
  Planting  [line 14, #planting, 11 chars]
    Tomatoes  [line 16, #tomatoes, 151 chars]
```

When you run it in a terminal it ends with one short line about the paid doc2md. `--quiet` turns it off, and it never shows when output is piped or redirected.

## How it splits

1. Each heading starts a new section. A chunk never mixes two sections, so every chunk has one clear heading path.
2. A small section becomes one chunk. Its text is copied straight from your file, so the line numbers match.
3. A big section is split at blank lines. Lists, tables and code blocks stay whole when they fit.
4. A table that is too big is split by rows, and each part gets the header row again.
5. A code block that is too big is split by lines, and each part gets its own ``` fence again, with the same language.
6. A very long line is cut at the end of a sentence, then at a space if it has to be.
7. A heading with no text of its own (just more headings under it) does not get its own chunk, but it still shows in the `heading_path` of the chunks under it.

It knows `#` headings and underlined headings (`===` and `---`). It skips headings inside code blocks and YAML front matter (the `---` block at the very top).

Options:

- `--max-chars N`: biggest chunk, in characters (default 1500, smallest 200). About 4 characters make 1 token in English.
- `--overlap-chars N`: when a section is split, start each part with up to N characters from the end of the part before it (default 0). It is never added inside a code block or table, and never between two different sections.
- `--prefix-path`: start each chunk's text with its heading path, like `Garden Guide > Planting > Tomatoes`. This often helps search. It counts toward `--max-chars`.
- `--json`: print one JSON object for scripts and AI agents instead of saving a file.

## Known limits

- **Sizes are characters, not tokens.** It does not load a tokenizer.
- **Markdown and plain text only.** PDF, Word and HTML are not read. The paid doc2md turns those into chunks (with page numbers for PDFs).
- **No folders.** Give it files (your shell can expand `docs/*.md`). The paid doc2md walks whole folders.
- **Not a full Markdown parser.** A heading inside an HTML block, or an underlined heading that spans more than one line, may be handled wrong.
- **Overlap uses whole words** from the part before, so it can be a little shorter than you asked for.

## Lite vs paid

| | md-chunk-lite (free) | [doc2md](https://tidybyte.gumroad.com/l/frlkv) (paid) |
|---|---|---|
| Reads | Markdown and text files | PDF, Word (.docx) and HTML |
| Chunks with the heading path | yes | yes |
| Line numbers and anchors | yes | no (page numbers for PDFs instead) |
| Rough token count on each chunk | no | yes |
| Whole folders, sub-folders too | no | yes |
| MCP server | yes | no |

## Other good free tools

Pick what fits you. If you already use LangChain, its `MarkdownHeaderTextSplitter` also splits by heading. [Chonkie](https://github.com/feyninc/chonkie) and [semchunk](https://github.com/isaacus-dev/semchunk) split any text by token count. md-chunk-lite is small, MIT, has no AI or tokenizer parts, gives you line numbers and anchors, and has an MCP server built in.

## Use it from Claude Desktop or Cursor (MCP)

There is a small free MCP server built in. It needs [uv](https://docs.astral.sh/uv/).

Run it by hand to check it starts (it waits quietly for an app to talk to it):

```
uvx md-chunk-lite mcp
```

Claude Desktop (`claude_desktop_config.json`) or Cursor (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "md-chunk-lite": {
      "command": "uvx",
      "args": ["md-chunk-lite", "mcp"]
    }
  }
}
```

`uvx --from md-chunk-lite md-chunk-lite-mcp` starts the same server.

Tools (each one takes a file `path` or Markdown `text`):

| Tool | What it does | Changes files? |
|---|---|---|
| `chunk_markdown` | Splits into chunks. Returns 100 at a time; use `start` for more. | No |
| `outline_markdown` | Lists the headings with line numbers and anchors. | No |
| `get_section` | Gets one section by heading or anchor. | No |
| `save_chunks_jsonl` | Saves the chunks to a `.jsonl` file. | Writes one `.jsonl` file (replaces it if it is there) |

None of them use the internet.

## For AI agents

- **Use when:** you have a Markdown or text file (docs, notes, a README) and need chunks with heading paths and line numbers for search, embeddings or citing sources. Use `outline_markdown` and `get_section` to read just one part of a long file.
- **Don't use when:** the file is PDF, Word or HTML (convert it first), or you need token-exact sizes.
- **Input:** a file path or Markdown text, plus `max_chars` (default 1500), `overlap_chars` (default 0) and `prefix_path` (default false).
- **Output:** chunks with `id`, `source`, `index`, `heading_path`, `heading_level`, `anchor`, `start_line`, `end_line`, `part`, `parts`, `chars`, `text`.
- CLI exit code is 0 on success and 1 on error (message on stderr, or `{"ok": false, "error": ...}` with `--json`). See also [`llms.txt`](https://github.com/tidybytetools/md-chunk-lite/blob/main/llms.txt).

## Python

```python
from md_chunk_lite import chunk_file, chunk_markdown, outline, get_section

chunks = chunk_file("guide.md", max_chars=1000)
for c in chunks:
    print(c["heading_path"], c["start_line"], c["end_line"])

install = get_section(open("README.md").read(), heading="Install")
```

The chunker file uses only Python's standard library. Installing with pip also adds the `mcp` package for the MCP server.

## Tests

```
pip install "mcp>=1.10,<2"
python3 -m unittest discover -s tests
```

The MCP tests are skipped if `mcp` is not installed.

## License

MIT. See `LICENSE`.
