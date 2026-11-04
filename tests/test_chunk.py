"""Tests for the chunker, outline, get_section and the command line."""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import md_chunk_lite as m

GUIDE = os.path.join(HERE, "fixtures", "guide.md")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def big_doc():
    para = " ".join(f"Sentence number {k} is here." for k in range(60))
    lines = ["# Big", "", "## Long", ""]
    lines += [para[:300], "", para[300:600], "", para[600:900], ""]
    lines += ["| Name | Size |", "| --- | ---: |"] + [f"| row{k} | {k * 3} |" for k in range(60)] + [""]
    lines += ["```python"] + [f"x{k} = {k}" for k in range(80)] + ["```", ""]
    lines += [para * 3]
    return "\n".join(lines)


class Parsing(unittest.TestCase):
    def setUp(self):
        self.chunks = m.chunk_markdown(read(GUIDE), source="guide.md")
        self.by_anchor = {c["anchor"]: c for c in self.chunks}

    def test_front_matter_skipped_and_intro_kept(self):
        first = self.chunks[0]
        self.assertEqual(first["heading_path"], [])
        self.assertEqual(first["heading_level"], 0)
        self.assertEqual(first["start_line"], 6)
        self.assertNotIn("title:", "".join(c["text"] for c in self.chunks))

    def test_heading_paths(self):
        self.assertEqual(self.by_anchor["tomatoes"]["heading_path"], ["Garden Guide", "Planting", "Tomatoes"])
        self.assertEqual(self.by_anchor["tools"]["heading_level"], 2)

    def test_heading_inside_code_fence_is_not_a_heading(self):
        tom = self.by_anchor["tomatoes"]
        self.assertIn("# This is not a heading", tom["text"])
        self.assertEqual(tom["parts"], 1)

    def test_setext_heading(self):
        w = self.by_anchor["watering"]
        self.assertEqual(w["heading_path"], ["Garden Guide", "Watering"])
        self.assertEqual(w["heading_level"], 2)

    def test_duplicate_anchor_and_heading_only_sections(self):
        self.assertIn("planting-1", self.by_anchor)
        self.assertNotIn("planting", self.by_anchor)          # heading with no text of its own
        self.assertNotIn("empty-heading-only", self.by_anchor)
        self.assertEqual(self.by_anchor["child-of-empty"]["heading_path"],
                         ["Garden Guide", "Empty heading only", "Child of empty"])

    def test_text_is_exact_slice_of_the_file(self):
        lines = read(GUIDE).splitlines()
        for c in self.chunks:
            self.assertEqual(c["text"], "\n".join(lines[c["start_line"] - 1:c["end_line"]]), c["id"])
            self.assertEqual(c["chars"], len(c["text"]))

    def test_ids_and_index(self):
        self.assertEqual([c["index"] for c in self.chunks], list(range(1, len(self.chunks) + 1)))
        self.assertEqual(self.chunks[1]["id"], "guide.md#2")
        self.assertEqual(m.chunk_markdown("hi")[0]["id"], "text#1")

    def test_atx_details(self):
        text = "# Title ##\n\nA\n\n#hashtag is not a heading\n\n## **Bold** and [link](http://x) `code`\n\nB"
        cs = m.chunk_markdown(text)
        self.assertEqual(cs[0]["heading_path"], ["Title"])
        self.assertIn("#hashtag", cs[0]["text"])
        self.assertEqual(cs[1]["heading_path"], ["Title", "Bold and link code"])
        self.assertEqual(cs[1]["anchor"], "bold-and-link-code")

    def test_windows_line_endings(self):
        cs = m.chunk_markdown("# A\r\n\r\none\r\n\r\n## B\r\n\r\ntwo\r\n")
        self.assertEqual([c["heading_path"] for c in cs], [["A"], ["A", "B"]])
        self.assertEqual(cs[1]["start_line"], 5)

    def test_unclosed_fence_runs_to_end(self):
        cs = m.chunk_markdown("# A\n\n```\n# not a heading\n\nstill code")
        self.assertEqual(len(cs), 1)
        self.assertIn("still code", cs[0]["text"])

    def test_tilde_fence_and_longer_backtick_fence(self):
        text = "# A\n\n~~~\n# no\n```\n# no\n~~~\n\n````md\n```\n# no\n```\n````\n\n## B\n\nyes"
        self.assertEqual([c["anchor"] for c in m.chunk_markdown(text)], ["a", "b"])

    def test_dash_line_after_blank_is_not_a_heading(self):
        cs = m.chunk_markdown("# A\n\nText\n\n---\n\nMore")
        self.assertEqual(len(cs), 1)

    def test_empty_input(self):
        self.assertEqual(m.chunk_markdown(""), [])
        self.assertEqual(m.chunk_markdown("# Only a heading\n\n## And another"), [])


class Splitting(unittest.TestCase):
    def test_every_chunk_fits(self):
        text = big_doc()
        for size in (200, 400, 900):
            for ov in (0, 80):
                for pp in (False, True):
                    cs = m.chunk_markdown(text, max_chars=size, overlap_chars=ov, prefix_path=pp)
                    self.assertTrue(cs)
                    for c in cs:
                        self.assertLessEqual(c["chars"], size, (size, ov, pp, c["id"]))
                        self.assertLessEqual(c["start_line"], c["end_line"])

    def test_parts_are_numbered(self):
        cs = [c for c in m.chunk_markdown(big_doc(), max_chars=400) if c["anchor"] == "long"]
        self.assertGreater(len(cs), 3)
        self.assertEqual([c["part"] for c in cs], list(range(1, len(cs) + 1)))
        self.assertTrue(all(c["parts"] == len(cs) for c in cs))
        self.assertTrue(cs[0]["text"].startswith("## Long"))

    def test_table_header_repeats(self):
        cs = [c for c in m.chunk_markdown(big_doc(), max_chars=400) if "| row" in c["text"]]
        self.assertGreater(len(cs), 1)
        for c in cs:
            self.assertTrue(c["text"].startswith("| Name | Size |\n| --- | ---: |"), c["text"][:40])
        # the rows are not lost or repeated
        rows = [l for c in cs for l in c["text"].splitlines() if l.startswith("| row")]
        self.assertEqual(rows, [f"| row{k} | {k * 3} |" for k in range(60)])

    def test_code_fence_closes_and_reopens(self):
        code = [c for c in m.chunk_markdown(big_doc(), max_chars=300) if c["text"].startswith("```python")]
        self.assertGreater(len(code), 1)
        for c in code:
            self.assertTrue(c["text"].endswith("```"))
        got = [l for c in code for l in c["text"].splitlines() if l.startswith("x")]
        self.assertEqual(got, [f"x{k} = {k}" for k in range(80)])

    def test_overlap_never_pushes_a_chunk_over_the_limit(self):
        text = "x" * 650 + "\n\nend line\n"
        for ov in (0, 50, 100):
            cs = m.chunk_markdown(text, max_chars=200, overlap_chars=ov)
            self.assertTrue(all(c["chars"] <= 200 for c in cs), [c["chars"] for c in cs])

    def test_heading_stays_with_a_big_code_block(self):
        text = "# Top\n\n## Setup\n\n```bash\n" + "\n".join(f"echo step {k}" for k in range(100)) + "\n```\n"
        cs = m.chunk_markdown(text, max_chars=300)
        self.assertTrue(cs[0]["text"].startswith("## Setup\n\n```bash\necho step 0"), cs[0]["text"][:40])
        self.assertTrue(all(c["chars"] <= 300 for c in cs))

    def test_line_numbers_point_at_the_source(self):
        text = big_doc()
        lines = text.splitlines()
        for c in m.chunk_markdown(text, max_chars=400):
            first = c["text"].splitlines()[0]
            if not first.startswith(("```", "| Name", "| ---")):
                self.assertIn(first[:30], lines[c["start_line"] - 1], c["id"])
            last = c["text"].splitlines()[-1]
            if last != "```":
                self.assertIn(last[-30:], lines[c["end_line"] - 1], c["id"])

    def test_long_line_is_cut_at_sentence_ends(self):
        line = " ".join(f"This is sentence {k}." for k in range(100))
        cs = m.chunk_markdown(line, max_chars=200)
        self.assertGreater(len(cs), 5)
        for c in cs:
            self.assertTrue(c["text"].endswith("."), c["text"])
            self.assertEqual((c["start_line"], c["end_line"]), (1, 1))
        self.assertEqual(" ".join(c["text"] for c in cs), line)

    def test_word_longer_than_max_is_cut(self):
        cs = m.chunk_markdown("x" * 1000, max_chars=300)
        self.assertEqual("".join(c["text"] for c in cs), "x" * 1000)

    def test_overlap(self):
        text = "# A\n\n" + "\n\n".join(f"Paragraph {k} has some words in it." for k in range(40))
        plain = m.chunk_markdown(text, max_chars=300)
        lapped = m.chunk_markdown(text, max_chars=300, overlap_chars=60)
        self.assertGreater(len(plain), 2)
        for prev, cur in zip(lapped, lapped[1:]):
            tail = prev["text"].splitlines()[-1]
            self.assertTrue(cur["text"].startswith(tail[-20:]) or tail in cur["text"], (prev["text"][-60:], cur["text"][:80]))
            self.assertLessEqual(cur["start_line"], prev["end_line"])
        # no overlap between different sections
        two = m.chunk_markdown("# A\n\none\n\n# B\n\ntwo", overlap_chars=50)
        self.assertEqual(two[1]["text"], "# B\n\ntwo")

    def test_prefix_path(self):
        cs = m.chunk_markdown(read(GUIDE), prefix_path=True)
        tom = [c for c in cs if c["anchor"] == "tomatoes"][0]
        self.assertTrue(tom["text"].startswith("Garden Guide > Planting > Tomatoes\n\n### Tomatoes"))
        self.assertFalse(cs[0]["text"].startswith(">"))  # intro has no path

    def test_bad_settings(self):
        with self.assertRaises(ValueError):
            m.chunk_markdown("x", max_chars=50)
        with self.assertRaises(ValueError):
            m.chunk_markdown("x", max_chars=400, overlap_chars=300)


class OutlineAndSection(unittest.TestCase):
    def test_outline(self):
        heads = m.outline(read(GUIDE))
        self.assertEqual(heads[0]["title"], "Garden Guide")
        self.assertEqual(heads[0]["line"], 8)
        self.assertEqual([h["anchor"] for h in heads].count("planting-1"), 1)
        watering = [h for h in heads if h["anchor"] == "watering"][0]
        self.assertEqual((watering["line"], watering["level"]), (29, 2))

    def test_get_section_by_heading_and_anchor(self):
        text = read(GUIDE)
        s = m.get_section(text, heading="planting")
        self.assertEqual(s["matches"], 2)
        self.assertIn("### Beans", s["text"])
        self.assertNotIn("Watering", s["text"])
        s2 = m.get_section(text, anchor="#planting-1")
        self.assertIn("same name", s2["text"])
        self.assertEqual(s2["start_line"], 34)
        s3 = m.get_section(text, heading="Planting", include_subsections=False)
        self.assertEqual(s3["text"], "## Planting")

    def test_get_section_not_found_lists_headings(self):
        with self.assertRaises(ValueError) as e:
            m.get_section(read(GUIDE), heading="Roses")
        self.assertIn('"Tools" (#tools)', str(e.exception))


class CommandLine(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "md_chunk_lite.py"), *args],
                           input=stdin, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_writes_jsonl_next_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "guide.md")
            shutil.copy(GUIDE, src)
            code, out, err = self.run_cli(src)
            self.assertEqual(code, 0, err)
            self.assertIn("Saved:", out)
            self.assertNotIn("Tip:", err)  # no tip when not in a terminal
            rows = [json.loads(l) for l in read(os.path.join(d, "guide.chunks.jsonl")).splitlines()]
            self.assertEqual(len(rows), 7)
            self.assertEqual(set(rows[0]), {"id", "source", "index", "heading_path", "heading_level", "anchor",
                                            "start_line", "end_line", "part", "parts", "chars", "text"})

    def test_stdout_and_stdin(self):
        code, out, _ = self.run_cli("-", stdin="# Hi\n\nthere\n")
        self.assertEqual(code, 0)
        row = json.loads(out)
        self.assertEqual((row["id"], row["heading_path"]), ("text#1", ["Hi"]))
        code, out, _ = self.run_cli(GUIDE, "-o", "-", "--max-chars", "300")
        self.assertEqual(len(out.splitlines()), 7)

    def test_json_and_outline(self):
        code, out, _ = self.run_cli(GUIDE, "--json")
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 7)
        code, out, _ = self.run_cli(GUIDE, "--outline")
        self.assertIn("    Tomatoes  [line 16, #tomatoes", out)
        code, out, _ = self.run_cli(GUIDE, "--outline", "--json")
        self.assertEqual(json.loads(out)["headings"][0]["title"], "Garden Guide")

    def test_errors(self):
        code, out, _ = self.run_cli("/nope/missing.md", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["ok"])
        code, _, err = self.run_cli(GUIDE, "--max-chars", "10")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)

    def test_version(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual(out.strip(), f"md-chunk-lite {m.__version__}")

    def test_default_output_name(self):
        self.assertEqual(m.default_output("a/b/notes.md"), "a/b/notes.chunks.jsonl")
        self.assertEqual(m.default_output("README"), "README.chunks.jsonl")


if __name__ == "__main__":
    unittest.main()
