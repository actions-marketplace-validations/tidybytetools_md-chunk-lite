"""Free MCP server for md-chunk-lite (stdio).

Run:  uvx md-chunk-lite mcp
  or: uvx --from md-chunk-lite md-chunk-lite-mcp
"""
import os
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import md_chunk_lite as lite

MAX_BYTES = 10_000_000  # 10 MB

mcp = FastMCP("md-chunk-lite")

READ_ONLY = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

Path = Annotated[str, Field(description="Full path to a local Markdown or text file (UTF-8, up to 10 MB). Leave empty if you pass text.")]
Text = Annotated[str, Field(description="Markdown text to use instead of a file. Leave empty if you pass path.")]
MaxChars = Annotated[int, Field(ge=200, le=100_000, description="Biggest chunk size in characters (not tokens). Default 1500.")]
Overlap = Annotated[int, Field(ge=0, description="Characters repeated from the end of one part at the start of the next, only when a section is split. Must be at most half of max_chars. Default 0.")]
Prefix = Annotated[bool, Field(description='If true, each chunk text starts with its heading path, like "Guide > Install".')]


def _load(path, text):
    if bool(path) == bool(text):
        raise ValueError("give exactly one of path or text")
    if path:
        p = os.path.expanduser(path)
        return lite.read_text(p, MAX_BYTES), p
    return text, ""


@mcp.tool(title="Split Markdown into chunks", annotations=ToolAnnotations(title="Split Markdown into chunks", **READ_ONLY))
def chunk_markdown(
    path: Path = "",
    text: Text = "",
    max_chars: MaxChars = lite.DEFAULT_MAX,
    overlap_chars: Overlap = 0,
    prefix_path: Prefix = False,
    start: Annotated[int, Field(ge=1, description="First chunk number to return (1 = the first). Use next_start from the last call to get more.")] = 1,
    limit: Annotated[int, Field(ge=1, le=500, description="Most chunks to return in one call. Default 100.")] = 100,
) -> dict:
    """Split a Markdown file or Markdown text into chunks by heading, for search, embeddings or RAG.

    Use this when you need a long Markdown document (docs, notes, a README) broken
    into pieces that each know where they came from. A chunk never mixes two
    sections. Each chunk has heading_path (like ["Guide", "Install"]), anchor
    (the GitHub-style #link), start_line and end_line (1-based, in the file), part
    and parts (when a big section had to be split), chars and text. Code blocks and
    tables are kept whole when they fit; when they don't, each piece gets the fence
    or table header again. Plain code, not AI: same input, same chunks.

    Do not use it for PDF or Word files (convert them to Markdown first), to just
    see the headings (use outline_markdown), or to read one section (use
    get_section). Sizes are characters, not tokens.

    Returns {"source", "total", "start", "chunks": [...], "next_start"}. next_start
    is null when there are no more chunks.
    """
    body, src = _load(path, text)
    chunks = lite.chunk_markdown(body, max_chars, overlap_chars, src, prefix_path)
    page = chunks[start - 1:start - 1 + limit]
    nxt = start + len(page)
    return {"source": src, "total": len(chunks), "start": start, "chunks": page,
            "next_start": nxt if nxt <= len(chunks) else None}


@mcp.tool(title="List Markdown headings", annotations=ToolAnnotations(title="List Markdown headings", **READ_ONLY))
def outline_markdown(path: Path = "", text: Text = "") -> dict:
    """List every heading in a Markdown file or text, with its level, path, anchor, line number and size.

    Use this when you want a quick map of a long document before you read or chunk
    it, or to find the exact heading or anchor to pass to get_section. Headings
    inside code blocks and YAML front matter are ignored. Both "# Title" and
    underlined (=== / ---) headings are found.

    Do not use it to get the text itself (use get_section or chunk_markdown).

    Returns {"source", "count", "headings": [{"level", "title", "path", "anchor",
    "line", "end_line", "chars"}]}. chars is the size of that heading's own text,
    not counting the sections under it.
    """
    body, src = _load(path, text)
    heads = lite.outline(body)
    return {"source": src, "count": len(heads), "headings": heads}


@mcp.tool(title="Get one Markdown section", annotations=ToolAnnotations(title="Get one Markdown section", **READ_ONLY))
def get_section(
    path: Path = "",
    text: Text = "",
    heading: Annotated[str, Field(description='Heading title to find, like "Install". Not case sensitive. Leave empty if you pass anchor.')] = "",
    anchor: Annotated[str, Field(description='Anchor to find, like "install" or "install-1" for the second "Install". Wins over heading.')] = "",
    include_subsections: Annotated[bool, Field(description="If true (default), include the smaller headings under it.")] = True,
) -> dict:
    """Return the text of one section of a Markdown file or text, found by heading title or anchor.

    Use this when you only need one part of a long document, like the "Install"
    section of a README, so you don't have to read the whole file. If two headings
    have the same title, the first one is returned and "matches" tells you how many
    there are; use the anchor (from outline_markdown) to pick another.

    Do not use it to split the whole document (use chunk_markdown).

    Returns {"title", "heading_path", "level", "anchor", "start_line", "end_line",
    "chars", "matches", "text"}. If nothing matches, the error lists the headings.
    """
    body, _ = _load(path, text)
    return lite.get_section(body, heading, anchor, include_subsections)


@mcp.tool(
    title="Save chunks to a JSONL file",
    annotations=ToolAnnotations(
        title="Save chunks to a JSONL file",
        readOnlyHint=False,     # writes one .jsonl file
        destructiveHint=True,   # replaces that file if it is already there
        idempotentHint=True,    # same input writes the same file
        openWorldHint=False,
    ),
)
def save_chunks_jsonl(
    path: Annotated[str, Field(description="Full path to the local Markdown file to split (UTF-8, up to 10 MB).")],
    output_path: Annotated[str, Field(description="Where to save. Must end in .jsonl. Default: next to the input, as NAME.chunks.jsonl.")] = "",
    max_chars: MaxChars = lite.DEFAULT_MAX,
    overlap_chars: Overlap = 0,
    prefix_path: Prefix = False,
) -> dict:
    """Split a Markdown file into chunks and save them as a JSONL file (one chunk per line).

    Use this when the chunks are going into a search index, vector database or
    another program, and you want a file instead of a long chat reply. The chunks
    are the same as chunk_markdown gives. It writes only the one .jsonl file and
    replaces it if it is already there. It never changes the Markdown file.

    Do not use it to look at chunks in the chat (use chunk_markdown).

    Returns {"output_path", "chunks", "bytes", "biggest_chunk_chars"}.
    """
    src = os.path.abspath(os.path.expanduser(path))
    body = lite.read_text(src, MAX_BYTES)
    out = os.path.abspath(os.path.expanduser(output_path)) if output_path else lite.default_output(src)
    if not out.lower().endswith(".jsonl"):
        raise ValueError("output_path must end in .jsonl")
    if os.path.exists(out) and os.path.samefile(out, src):
        raise ValueError("output_path cannot be the input file")
    if not os.path.isdir(os.path.dirname(out)):
        raise ValueError(f"folder not found: {os.path.dirname(out)}")
    chunks = lite.chunk_markdown(body, max_chars, overlap_chars, src, prefix_path)
    data = lite.to_jsonl(chunks).encode("utf-8")
    with open(out, "wb") as f:
        f.write(data)
    return {"output_path": out, "chunks": len(chunks), "bytes": len(data),
            "biggest_chunk_chars": max((c["chars"] for c in chunks), default=0)}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
