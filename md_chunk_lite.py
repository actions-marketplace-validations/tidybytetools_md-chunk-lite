#!/usr/bin/env python3
"""md-chunk-lite (MIT): split Markdown into chunks by heading.

Every chunk keeps its heading path (like ["Guide", "Install", "Windows"]) and the
first and last line numbers it came from, so you can always find it again.
This file uses only the Python standard library. The MCP server
(md_chunk_lite_mcp.py) needs the mcp package.
"""
import argparse, json, os, re, sys, unicodedata

__version__ = "1.1.0"
PRO_URL = "https://tidybyte.gumroad.com/l/frlkv"
PRO_LINE = f"Tip: need PDF, Word or HTML files turned into chunks, or whole folders? doc2md (paid): {PRO_URL}"

DEFAULT_MAX = 1500
MIN_ROOM = 40  # smallest space we will pack text into

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_NOT_SETEXT_TEXT = re.compile(r"^ {0,3}([-*+>|#]|\d+[.)]\s|```|~~~)")


# ---------------------------------------------------------------- reading the page

def _front_matter_end(lines):
    """Index of the first line after YAML front matter (0 if there is none)."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return i + 1
    return 0


def _clean_title(raw):
    """Heading text without closing #s, link targets, or * and ` marks."""
    t = re.sub(r"[ \t]+#+[ \t]*$", "", " " + raw).strip()
    if re.fullmatch(r"#+", t):
        t = ""
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)   # [text](url) -> text
    t = re.sub(r"<[^>]+>", "", t)                        # inline html tags
    t = t.replace("`", "").replace("**", "").replace("__", "")
    t = re.sub(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)", r"\1", t)
    return " ".join(t.split())


def slugify(title):
    """GitHub-style anchor: lower case, keep letters, numbers, - and _, spaces become -."""
    s = unicodedata.normalize("NFKC", title).lower()
    s = "".join(ch for ch in s if ch.isalnum() or ch in " -_")
    return s.replace(" ", "-")


def scan(text):
    """Find headings and code fences.

    Returns (lines, body_start, headings, fences). Each heading is a dict with
    level, title, line (0-based index of its first line) and size (1 or 2 lines).
    fences is a dict {open line index: end index (exclusive)} for each code fence.
    """
    lines = text.splitlines()
    start = _front_matter_end(lines)
    headings, fences = [], {}
    fence = None  # (char, length, open index)
    i = start
    while i < len(lines):
        line = lines[i]
        if fence:
            m = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fences[fence[2]] = i + 1
                fence = None
            i += 1
            continue
        m = _FENCE_OPEN.match(line)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)), i)
            i += 1
            continue
        m = _ATX.match(line)
        if m:
            headings.append({"level": len(m.group(1)), "title": _clean_title(m.group(2) or ""), "line": i, "size": 1})
            i += 1
            continue
        if (i + 1 < len(lines) and line.strip() and not _NOT_SETEXT_TEXT.match(line)
                and not line.startswith(("    ", "\t"))
                and (i == start or not lines[i - 1].strip() or (headings and headings[-1]["line"] + headings[-1]["size"] == i))
                and _SETEXT.match(lines[i + 1])):
            level = 1 if lines[i + 1].strip()[0] == "=" else 2
            headings.append({"level": level, "title": _clean_title(line), "line": i, "size": 2})
            i += 2
            continue
        i += 1
    if fence:  # never closed: it runs to the end
        fences[fence[2]] = len(lines)
    return lines, start, headings, fences


def sections(text):
    """Split the page into sections. Each heading starts one; text before the first heading is section 0.

    Each section: level, title, path, anchor, start (0-based first line), end (0-based,
    exclusive, before the next heading of any level), heading_size, sub_end (end
    including sub-sections).
    """
    lines, start, heads, fence = scan(text)
    out, stack, seen = [], [], {}
    first = heads[0]["line"] if heads else len(lines)
    if any(l.strip() for l in lines[start:first]):
        out.append({"level": 0, "title": "", "path": [], "anchor": "", "start": start,
                    "end": first, "heading_size": 0, "sub_end": first})
    for n, h in enumerate(heads):
        while stack and stack[-1][0] >= h["level"]:
            stack.pop()
        stack.append((h["level"], h["title"]))
        base = slugify(h["title"])
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count}"
        end = heads[n + 1]["line"] if n + 1 < len(heads) else len(lines)
        sub_end = len(lines)
        for later in heads[n + 1:]:
            if later["level"] <= h["level"]:
                sub_end = later["line"]
                break
        out.append({"level": h["level"], "title": h["title"], "path": [t for _, t in stack],
                    "anchor": anchor, "start": h["line"], "end": end,
                    "heading_size": h["size"], "sub_end": sub_end})
    return lines, out, fence


# ---------------------------------------------------------------- blocks and pieces
# A "unit" is one line (or one cut piece of a long line): (line_no or None, text, tag).
# tag is "line", "cut" (a piece of a longer line), or "wrap" (a fence or table
# header we repeat). line_no is 1-based; None means "added by us, not in the file".

def _blocks(lines, lo, hi, fences):
    """Group lines lo..hi-1 into blocks: (kind, [indexes]). kind is gap, code, table or text."""
    blocks, i = [], lo
    while i < hi:
        if i in fences:
            j = min(fences[i], hi)
            blocks.append(("code", list(range(i, j))))
            i = j
            continue
        if not lines[i].strip():
            blocks.append(("gap", [i]))
            i += 1
            continue
        j = i
        while j < hi and lines[j].strip() and j not in fences:
            j += 1
        idx = list(range(i, j))
        is_table = len(idx) >= 2 and lines[i].lstrip().startswith("|") and _TABLE_SEP.match(lines[i + 1])
        blocks.append(("table" if is_table else "text", idx))
        i = j
    return blocks


def _is_close(line):
    return bool(re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line))


def _cut(text, room):
    """Cut one long line into pieces of at most `room` chars: at sentence ends, then spaces, then anywhere."""
    def pack(parts, sep):
        out, cur = [], ""
        for p in parts:
            cand = p if not cur else cur + sep + p
            if len(cand) <= room:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = p
        if cur:
            out.append(cur)
        return out
    pieces = pack(re.split(r"(?<=[.!?])\s+", text.strip()), " ")
    final = []
    for p in pieces:
        if len(p) <= room:
            final.append(p)
            continue
        for w in pack(p.split(" "), " "):
            if len(w) <= room:
                final.append(w)
            else:
                final.extend(w[k:k + room] for k in range(0, len(w), room))
    return final


def _ulen(units):
    return sum(len(u[1]) for u in units) + _seps(units)


def _seps(units):
    return max(0, len(units) - 1)


def _join(units):
    out = ""
    for k, (ln, t, tag) in enumerate(units):
        if k:
            prev = units[k - 1]
            same_line = tag == "cut" and prev[2] == "cut" and prev[0] == ln and ln is not None
            out += " " if same_line else "\n"
        out += t
    return out


def _line_units(lines, idx, room):
    units = []
    for i in idx:
        t = lines[i]
        if len(t) <= room:
            units.append((i + 1, t, "line"))
        else:
            units.extend((i + 1, p, "cut") for p in _cut(t, room))
    return units


def _pack(units, room):
    """Greedy: fill each group up to `room` chars."""
    groups, cur = [], []
    for u in units:
        if cur and _ulen(cur + [u]) > room:
            groups.append(cur)
            cur = []
        cur.append(u)
    if cur:
        groups.append(cur)
    return groups


def _split_block(kind, lines, idx, room):
    """Split one block that is bigger than `room` into groups of units, each at most `room`."""
    if kind == "code" and len(idx) >= 2:
        open_i = idx[0]
        close_i = idx[-1] if _is_close(lines[idx[-1]]) else None
        inner = idx[1:-1] if close_i is not None else idx[1:]
        opener = lines[open_i]
        closer = lines[close_i] if close_i is not None else re.match(r"^ {0,3}(`{3,}|~{3,})", opener).group(1)
        wrap = len(opener) + len(closer) + 2
        if wrap <= room // 2:
            groups = _pack(_line_units(lines, inner, room - wrap), room - wrap)
            out = []
            for g, grp in enumerate(groups):
                head = (open_i + 1, opener, "line") if g == 0 else (None, opener, "wrap")
                last = g == len(groups) - 1
                tail = (close_i + 1, closer, "line") if (last and close_i is not None) else (None, closer, "wrap")
                out.append([head] + grp + [tail])
            return out
    if kind == "table":
        header = idx[:2]
        hlen = len(lines[header[0]]) + len(lines[header[1]]) + 2
        if hlen <= room // 2:
            groups = _pack(_line_units(lines, idx[2:], room - hlen), room - hlen)
            out = []
            for g, grp in enumerate(groups):
                if g == 0:
                    head = [(i + 1, lines[i], "line") for i in header]
                else:
                    head = [(None, lines[i], "wrap") for i in header]
                out.append(head + grp)
            return out
    return _pack(_line_units(lines, idx, room), room)


def _trim(units):
    while units and units[0][2] == "line" and not units[0][1].strip():
        units = units[1:]
    while units and units[-1][2] == "line" and not units[-1][1].strip():
        units = units[:-1]
    return units


def _section_parts(lines, sec, fence, room):
    """Cut one section into parts (lists of units). Parts never cross into another section."""
    body_lo = sec["start"] + sec["heading_size"]
    blocks = _blocks(lines, body_lo, sec["end"], fence)
    if sec["heading_size"]:
        # the heading line(s) come first and stay glued to what follows
        blocks = [("heading", list(range(sec["start"], body_lo)))] + blocks
    whole = _trim([(i + 1, lines[i], "line") for i in range(sec["start"], sec["end"])])
    if not whole:
        return []
    if _ulen(whole) <= room:
        return [whole]
    parts, cur, gap, only_heading = [], [], [], False
    for kind, idx in blocks:
        if kind == "gap":
            if cur:
                gap.append((idx[0] + 1, "", "line"))
            continue
        units = [(i + 1, lines[i], "line") for i in idx]
        if _ulen(units) > room:
            head = cur + gap if only_heading else []
            if head and room - _ulen(head) - 1 >= MIN_ROOM:
                # keep the heading on top of the first piece instead of alone
                groups = _split_block(kind, lines, idx, room - _ulen(head) - 1)
                groups[0] = head + groups[0]
            else:
                if cur:
                    parts.append(cur)
                groups = _split_block(kind, lines, idx, room)
            only_heading = False
            parts.extend(groups[:-1])
            cur, gap = list(groups[-1]), []
            continue
        if cur and _ulen(cur + gap + units) > room:
            parts.append(cur)
            cur, gap = [], []
        cur = cur + gap + units if cur else units
        gap = []
        only_heading = kind == "heading"
    if cur:
        parts.append(cur)
    return [p for p in (_trim(p) for p in parts) if p]


def _overlap(prev, nxt, n):
    """Up to n chars from the end of prev, as units, to put before nxt. Never inside code or tables."""
    if n <= 0 or not prev or not nxt or prev[-1][2] == "wrap" or nxt[0][2] == "wrap":
        return []
    if _FENCE_OPEN.match(nxt[0][1]) or nxt[0][1].lstrip().startswith("|"):
        return []  # the next part starts a code block or table: keep it clean
    taken, room = [], n - 1  # 1 for the line break or space before nxt
    for u in reversed(prev):
        if u[2] == "wrap" or _FENCE_OPEN.match(u[1]) or u[1].lstrip().startswith("|"):
            break
        need = len(u[1]) + (1 if taken else 0)
        if need <= room:
            taken.insert(0, u)
            room -= need
            continue
        avail = room - (1 if taken else 0)
        tail = u[1][-avail:] if avail > 0 else ""
        sp = tail.find(" ")
        tail = tail[sp + 1:] if sp >= 0 else ""  # start at a whole word
        if tail.strip():
            taken.insert(0, (u[0], tail, "cut"))
        break
    return _trim(taken)


# ---------------------------------------------------------------- public API

def chunk_markdown(text, max_chars=DEFAULT_MAX, overlap_chars=0, source="", prefix_path=False):
    """Split Markdown text into chunks. Returns a list of dicts (see README for the fields)."""
    if not isinstance(max_chars, int) or max_chars < 200:
        raise ValueError("max_chars must be a whole number, 200 or more")
    if not isinstance(overlap_chars, int) or overlap_chars < 0 or overlap_chars > max_chars // 2:
        raise ValueError("overlap_chars must be between 0 and half of max_chars")
    lines, secs, fence = sections(text)
    chunks = []
    name = os.path.basename(source) if source else "text"
    for sec in secs:
        prefix = (" > ".join(sec["path"]) + "\n\n") if (prefix_path and sec["path"]) else ""
        room = max_chars - len(prefix)
        whole = _trim([(i + 1, lines[i], "line") for i in range(sec["start"], sec["end"])])
        if not whole or (sec["heading_size"] and len(whole) <= sec["heading_size"]):
            continue  # empty, or only a heading: it still shows in the paths below it
        if _ulen(whole) > room:
            room -= overlap_chars
        if room < MIN_ROOM:
            raise ValueError("max_chars is too small for this heading path; make it bigger")
        parts = _section_parts(lines, sec, fence, room)
        for k, units in enumerate(parts):
            if k:
                units = _overlap(parts[k - 1], units, overlap_chars) + units
            nums = [u[0] for u in units if u[0] is not None]
            body = prefix + _join(units)
            chunks.append({
                "id": "", "source": source, "index": 0,
                "heading_path": list(sec["path"]), "heading_level": sec["level"],
                "anchor": sec["anchor"], "start_line": min(nums), "end_line": max(nums),
                "part": k + 1, "parts": len(parts), "chars": len(body), "text": body,
            })
    for n, c in enumerate(chunks, 1):
        c["index"] = n
        c["id"] = f"{name}#{n}"
    return chunks


def outline(text):
    """List the headings: level, title, path, anchor, line, end_line and chars (own text, no sub-sections)."""
    lines, secs, _ = sections(text)
    out = []
    for s in secs:
        if not s["level"]:
            continue
        body = _trim([(i + 1, lines[i], "line") for i in range(s["start"], s["end"])])
        out.append({"level": s["level"], "title": s["title"], "path": s["path"], "anchor": s["anchor"],
                    "line": s["start"] + 1, "end_line": body[-1][0] if body else s["start"] + 1,
                    "chars": _ulen(body)})
    return out


def get_section(text, heading="", anchor="", include_subsections=True):
    """Return one section by its anchor (exact) or heading title (not case sensitive)."""
    lines, secs, _ = sections(text)
    heads = [s for s in secs if s["level"]]
    if anchor:
        found = [s for s in heads if s["anchor"] == anchor.lstrip("#").lower()]
    elif heading:
        want = " ".join(_clean_title(heading.lstrip("#").strip()).split()).lower()
        found = [s for s in heads if s["title"].lower() == want]
    else:
        raise ValueError("give a heading or an anchor")
    if not found:
        names = ", ".join(f'"{s["title"]}" (#{s["anchor"]})' for s in heads[:30]) or "none"
        raise ValueError(f"no heading matches. Headings here: {names}")
    s = found[0]
    end = s["sub_end"] if include_subsections else s["end"]
    units = _trim([(i + 1, lines[i], "line") for i in range(s["start"], end)])
    body = _join(units)
    return {"title": s["title"], "heading_path": s["path"], "level": s["level"], "anchor": s["anchor"],
            "start_line": units[0][0], "end_line": units[-1][0], "chars": len(body),
            "matches": len(found), "text": body}


def read_text(path, max_bytes=None):
    """Read a UTF-8 text file (a byte-order mark is fine)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"file not found: {path}")
    if max_bytes and os.path.getsize(path) > max_bytes:
        raise ValueError(f"file is bigger than {max_bytes // 1_000_000} MB")
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not UTF-8 text") from None


def chunk_file(path, max_chars=DEFAULT_MAX, overlap_chars=0, prefix_path=False):
    return chunk_markdown(read_text(path), max_chars, overlap_chars, source=path, prefix_path=prefix_path)


def to_jsonl(chunks):
    return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)


def default_output(path):
    base = path[:-len(os.path.splitext(path)[1])] if os.path.splitext(path)[1] else path
    return base + ".chunks.jsonl"


# ---------------------------------------------------------------- command line

def run_mcp():
    try:
        import md_chunk_lite_mcp
    except ImportError as e:
        print(f"error: the MCP server needs the mcp package ({e}). Run: pip install md-chunk-lite", file=sys.stderr)
        return 1
    md_chunk_lite_mcp.main()
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["mcp"]:
        return run_mcp()
    p = argparse.ArgumentParser(
        prog="md-chunk-lite",
        description="Split Markdown into chunks by heading. Each chunk keeps its heading path and line numbers. "
                    "Run `md-chunk-lite mcp` to start the MCP server (to read a file named mcp, use ./mcp).",
        epilog=PRO_LINE)
    p.add_argument("files", nargs="+", help="Markdown files, or - to read from stdin")
    p.add_argument("-o", "--output", help="where to save the JSONL (default: NAME.chunks.jsonl next to each file; - prints it)")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX, help=f"biggest chunk size in characters (default {DEFAULT_MAX})")
    p.add_argument("--overlap-chars", type=int, default=0, help="repeat this many characters from the end of one part at the start of the next, when a section is split (default 0)")
    p.add_argument("--prefix-path", action="store_true", help='start each chunk text with its heading path, like "Guide > Install"')
    p.add_argument("--outline", action="store_true", help="just list the headings with line numbers")
    p.add_argument("--json", action="store_true", help="print one JSON object for scripts and AI agents (does not save files)")
    p.add_argument("-q", "--quiet", action="store_true", help="no summary or tip line")
    p.add_argument("--version", action="version", version=f"md-chunk-lite {__version__}")
    a = p.parse_args(argv)
    tip = not a.quiet and not a.json and sys.stderr.isatty()
    try:
        results = []
        for f in a.files:
            text = sys.stdin.read() if f == "-" else read_text(f)
            src = "" if f == "-" else f
            if a.outline:
                results.append((f, outline(text)))
            else:
                results.append((f, chunk_markdown(text, a.max_chars, a.overlap_chars, src, a.prefix_path)))
    except (OSError, ValueError) as e:
        if a.json:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"error: {e}", file=sys.stderr)
        return 1

    if a.json:
        key = "headings" if a.outline else "chunks"
        items = [x for _, r in results for x in r]
        out = {"ok": True, "files": [f for f, _ in results], key: items, "count": len(items)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if a.outline:
        for f, heads in results:
            if len(results) > 1:
                print(f"== {f}")
            for h in heads:
                print(f'{"  " * (h["level"] - 1)}{h["title"] or "(empty heading)"}  [line {h["line"]}, #{h["anchor"]}, {h["chars"]} chars]')
        return 0

    if a.output == "-" or (a.files == ["-"] and not a.output):
        sys.stdout.write("".join(to_jsonl(c) for _, c in results))
    elif a.output:
        with open(a.output, "w", encoding="utf-8") as fh:
            fh.write("".join(to_jsonl(c) for _, c in results))
        if not a.quiet:
            n = sum(len(c) for _, c in results)
            print(f"Saved: {a.output}  ({n} chunks from {len(results)} file{'s' if len(results) > 1 else ''})")
    else:
        for f, c in results:
            dest = default_output(f)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(to_jsonl(c))
            if not a.quiet:
                big = max((x["chars"] for x in c), default=0)
                print(f"Saved: {dest}  ({len(c)} chunks, biggest {big} chars)")
    if tip:
        print(PRO_LINE, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
