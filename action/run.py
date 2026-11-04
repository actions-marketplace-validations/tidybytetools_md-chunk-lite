#!/usr/bin/env python3
"""Runner for the MD Chunk Lite GitHub Action (Tidy Byte Tools, MIT).

Reads its settings from INPUT_* environment variables set by action.yml,
chunks the matching Markdown files with md_chunk_lite.py from this same
tag, writes one JSONL file, and reports to the job summary.
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import md_chunk_lite as mcl  # noqa: E402


def env(name, default=""):
    return os.environ.get("INPUT_" + name, default).strip()


def flag(name, default="false"):
    v = env(name, default).lower()
    if v not in ("true", "false"):
        raise ValueError(f"{name.lower().replace('_', '-')} must be true or false (got '{v}')")
    return v == "true"


def number(name, default, low):
    raw = env(name, str(default))
    try:
        n = int(raw)
    except ValueError:
        raise ValueError(f"{name.lower().replace('_', '-')} must be a whole number (got '{raw}')")
    if n < low:
        raise ValueError(f"{name.lower().replace('_', '-')} must be {low} or more (got {n})")
    return n


def patterns(raw):
    out = []
    for line in raw.replace(",", "\n").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def find_files(include, exclude):
    skip = set()
    for p in exclude:
        skip.update(os.path.normpath(x) for x in glob.glob(p, recursive=True))
    found = []
    for p in include:
        for x in sorted(glob.glob(p, recursive=True)):
            n = os.path.normpath(x)
            if os.path.isfile(n) and n not in skip and not any(n.startswith(s + os.sep) for s in skip) and n not in found:
                found.append(n)
    return found


def esc_prop(s):
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C")


def esc_msg(s):
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(kind, msg, file=None, line=None, title=None):
    props = []
    if file:
        props.append(f"file={esc_prop(file.replace(os.sep, '/'))}")
    if line:
        props.append(f"line={line}")
    if title:
        props.append(f"title={esc_prop(title)}")
    print(f"::{kind} {','.join(props)}::{esc_msg(msg)}" if props else f"::{kind}::{esc_msg(msg)}")


def write_outputs(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for k, v in values.items():
            fh.write(f"{k}={v}\n")


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def main():
    try:
        include = patterns(env("FILES", "**/*.md"))
        exclude = patterns(env("EXCLUDE", ""))
        max_chars = number("MAX_CHARS", mcl.DEFAULT_MAX, 200)
        overlap = number("OVERLAP_CHARS", 0, 0)
        prefix = flag("PREFIX_PATH")
        fail_on_split = flag("FAIL_ON_SPLIT")
        fail_if_none = flag("FAIL_IF_NO_FILES", "true")
        output = env("OUTPUT", "md-chunks.jsonl")
        if not include:
            raise ValueError("files is empty. Give at least one pattern, like docs/**/*.md")
        if not output:
            raise ValueError("output is empty. Give a file name, like md-chunks.jsonl")
    except ValueError as e:
        annotate("error", str(e), title="MD Chunk Lite")
        return 1

    files = find_files(include, exclude + [output])
    if not files:
        msg = f"No files matched: {', '.join(include)}"
        write_outputs({"files": 0, "chunks": 0, "biggest": 0, "split-sections": 0, "output": ""})
        write_summary(f"### MD Chunk Lite\n\n{msg}\n")
        if fail_if_none:
            annotate("error", msg + ". Check the files input, or set fail-if-no-files to false.", title="MD Chunk Lite")
            return 1
        annotate("warning", msg, title="MD Chunk Lite")
        return 0

    all_chunks, rows, split, errors = [], [], [], []
    for f in files:
        try:
            text = mcl.read_text(f)
        except (OSError, ValueError) as e:
            errors.append(f"{f}: {e}")
            annotate("error", f"Could not read this file: {e}", file=f, title="MD Chunk Lite")
            continue
        chunks = mcl.chunk_markdown(text, max_chars, overlap, f.replace(os.sep, "/"), prefix)
        all_chunks.extend(chunks)
        seen = set()
        n_split = 0
        for c in chunks:
            if c["parts"] > 1 and c["part"] == 1:
                key = (c["start_line"], tuple(c["heading_path"]))
                if key in seen:
                    continue
                seen.add(key)
                n_split += 1
                name = " > ".join(c["heading_path"]) or "(text before the first heading)"
                split.append((f, c["start_line"], name, c["parts"]))
                annotate("error" if fail_on_split else "warning",
                         f'The section "{name}" is too big for one chunk of {max_chars} characters, '
                         f"so it was split into {c['parts']} parts. A subheading can keep each part on one topic.",
                         file=f, line=c["start_line"], title="Section split into parts")
        rows.append((f, len(chunks), max((c["chars"] for c in chunks), default=0), n_split))

    out_dir = os.path.dirname(output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mcl.to_jsonl(all_chunks))

    biggest = max((c["chars"] for c in all_chunks), default=0)
    write_outputs({"files": len(rows), "chunks": len(all_chunks), "biggest": biggest,
                   "split-sections": len(split), "output": output.replace(os.sep, "/")})

    lines = ["### MD Chunk Lite", "",
             f"**{len(rows)}** file(s), **{len(all_chunks)}** chunk(s), biggest **{biggest}** characters "
             f"(limit {max_chars}). Saved to `{output}`.", "",
             "| File | Chunks | Biggest | Split sections |", "|---|---:|---:|---:|"]
    for f, n, big, s in rows[:200]:
        lines.append(f"| `{cell(f)}` | {n} | {big} | {s} |")
    if len(rows) > 200:
        lines.append(f"| ...and {len(rows) - 200} more | | | |")
    if split:
        lines += ["", "**Sections split into parts** (each is bigger than one chunk):", ""]
        for f, line, name, parts in split[:100]:
            lines.append(f"- `{cell(f)}` line {line}: {cell(name)} ({parts} parts)")
        if len(split) > 100:
            lines.append(f"- ...and {len(split) - 100} more")
    else:
        lines += ["", "Every section fits in one chunk."]
    write_summary("\n".join(lines) + "\n\n")

    print(f"Saved: {output}  ({len(all_chunks)} chunks from {len(rows)} file(s), biggest {biggest} chars, "
          f"{len(split)} section(s) split)")
    if errors:
        return 1
    if split and fail_on_split:
        annotate("error", f"{len(split)} section(s) are bigger than {max_chars} characters.", title="MD Chunk Lite")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
