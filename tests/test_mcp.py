"""Starts the MCP server over stdio (both ways it can start), lists tools, and calls each one."""
import asyncio, json, os, shutil, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUIDE = os.path.join(HERE, "fixtures", "guide.md")

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITES = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False}


def data(res):
    if res.structuredContent is not None:
        return res.structuredContent
    return json.loads(res.content[0].text)


def run(args, fn):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=args, cwd=ROOT)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await fn(s)
    return asyncio.run(go())


SERVER = [os.path.join(ROOT, "md_chunk_lite_mcp.py")]


@unittest.skipIf(ClientSession is None, "mcp not installed")
class MCP(unittest.TestCase):
    def test_tools_and_annotations(self):
        async def fn(s):
            return (await s.list_tools()).tools
        tools = {t.name: t for t in run(SERVER, fn)}
        self.assertEqual(sorted(tools), ["chunk_markdown", "get_section", "outline_markdown", "save_chunks_jsonl"])
        for name, t in tools.items():
            self.assertTrue(t.title)
            self.assertIn("Use this when", t.description)
            self.assertIn("Do not use", t.description)
            want = WRITES if name == "save_chunks_jsonl" else READ_ONLY
            for k, v in want.items():
                self.assertIs(getattr(t.annotations, k), v, f"{name} {k}")
            for prop, schema in t.inputSchema["properties"].items():
                self.assertTrue(schema.get("description"), f"{name}.{prop} has no description")

    def test_read_tools(self):
        async def fn(s):
            a = await s.call_tool("chunk_markdown", {"path": GUIDE, "limit": 3})
            b = await s.call_tool("chunk_markdown", {"path": GUIDE, "start": 4})
            c = await s.call_tool("chunk_markdown", {"text": "# Hi\n\nthere"})
            d = await s.call_tool("outline_markdown", {"path": GUIDE})
            e = await s.call_tool("get_section", {"path": GUIDE, "anchor": "planting-1"})
            both = await s.call_tool("chunk_markdown", {"path": GUIDE, "text": "x"})
            neither = await s.call_tool("outline_markdown", {})
            missing = await s.call_tool("get_section", {"path": GUIDE, "heading": "Roses"})
            return a, b, c, d, e, both, neither, missing
        a, b, c, d, e, both, neither, missing = run(SERVER, fn)
        a, b = data(a), data(b)
        self.assertEqual((a["total"], len(a["chunks"]), a["next_start"]), (7, 3, 4))
        self.assertEqual((len(b["chunks"]), b["next_start"]), (4, None))
        self.assertEqual(b["chunks"][0]["index"], 4)
        self.assertEqual(data(c)["chunks"][0]["heading_path"], ["Hi"])
        self.assertEqual(data(d)["headings"][1]["anchor"], "tools")
        self.assertEqual(data(e)["start_line"], 34)
        for res in (both, neither, missing):
            self.assertTrue(res.isError)
        self.assertIn("Tools", missing.content[0].text)

    def test_save_chunks_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "guide.md")
            shutil.copy(GUIDE, src)

            async def fn(s):
                ok = await s.call_tool("save_chunks_jsonl", {"path": src})
                bad = await s.call_tool("save_chunks_jsonl", {"path": src, "output_path": os.path.join(d, "x.md")})
                return ok, bad
            ok, bad = run(SERVER, fn)
            out = data(ok)
            self.assertEqual(out["output_path"], os.path.join(d, "guide.chunks.jsonl"))
            self.assertEqual(out["chunks"], 7)
            with open(out["output_path"], encoding="utf-8") as f:
                self.assertEqual(len(f.read().splitlines()), 7)
            self.assertTrue(bad.isError)
            with open(src, encoding="utf-8") as f, open(GUIDE, encoding="utf-8") as g:
                self.assertEqual(f.read(), g.read())  # the Markdown file is never changed

    def test_cli_mcp_subcommand_starts_server(self):
        async def fn(s):
            return [t.name for t in (await s.list_tools()).tools]
        self.assertIn("chunk_markdown", run([os.path.join(ROOT, "md_chunk_lite.py"), "mcp"], fn))


if __name__ == "__main__":
    unittest.main()
