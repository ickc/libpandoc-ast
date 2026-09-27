"""Conversion: what a filter knows of its pandoc run, and ctx.read."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pandom as A
import pytest
from pandom import CodeBlock, Conversion, Filter, Pandoc, Para, Str


def fake_pandoc(calls: list):
    """A pandoc that records its options and reads every text as one Str."""

    def run(text, options):
        calls.append(dict(options))
        return A.dumps(Pandoc(Para(Str(text))))

    return run


def test_read_options_from_the_conversions_options():
    c = Conversion(
        "html",
        options={
            "from": "markdown-smart",
            "to": "html",
            "tab-stop": 8,
            "filters": ["a.lua"],
            "template": "t.html",
            "metadata": {"title": "T"},
            "resource-path": ["img"],
        },
    )
    assert c.read_options() == {
        "from": "markdown-smart",
        "to": "json",
        "tab-stop": 8,
        "resource-path": ["img"],
    }


def test_read_options_prefer_the_input_format_pandoc_decided():
    c = Conversion(input_format="commonmark_x-smart", options={"input-files": ["a.md"]})
    assert c.read_options()["from"] == "commonmark_x-smart"
    assert c.read_options("rst")["from"] == "rst"


def test_read_options_from_reader_options_alone():
    c = Conversion(
        "html",
        reader_options={"tab-stop": 2, "track-changes": "reject-changes", "columns": 72},
    )
    assert c.read_options() == {
        "from": "markdown",
        "to": "json",
        "tab-stop": 2,
        "track-changes": "reject",
    }


def test_from_environment(monkeypatch):
    monkeypatch.delenv("PANDOC_INPUT_FORMAT", raising=False)
    monkeypatch.delenv("PANDOC_OUTPUT_FORMAT", raising=False)
    monkeypatch.setenv("PANDOC_READER_OPTIONS", json.dumps({"tab-stop": 3}))
    c = Conversion.from_environment(["html5"])
    assert c.format == "html5"
    assert c.reader_options == {"tab-stop": 3}
    assert c.input_format is None


def test_from_environment_with_the_formats(monkeypatch):
    """As libpandoc (and, proposed, pandoc) tells JSON filters."""
    monkeypatch.setenv("PANDOC_INPUT_FORMAT", "commonmark_x-smart")
    monkeypatch.setenv("PANDOC_OUTPUT_FORMAT", "html5+smart")
    c = Conversion.from_environment(["html5"])
    assert (c.input_format, c.output_format) == ("commonmark_x-smart", "html5+smart")
    assert c.read_options()["from"] == "commonmark_x-smart"


def test_from_context():
    c = Conversion.from_context(
        {
            "format": "html5",
            "input-format": "commonmark_x",
            "output-format": "html5+smart",
            "reader-options": {"tab-stop": 4},
        },
        options={"to": "html5+smart"},
    )
    assert (c.format, c.input_format, c.output_format) == ("html5", "commonmark_x", "html5+smart")
    assert c.options == {"to": "html5+smart"}
    assert "commonmark_x" in repr(c)


def test_ctx_read_in_a_filter():
    calls: list = []
    f = Filter()

    @f.on(CodeBlock)
    def table(code, ctx):
        return ctx.read(code.text)

    doc = Pandoc(CodeBlock("cell"))
    conv = Conversion("html", input_format="gfm", pandoc=fake_pandoc(calls))
    out = f(doc, conversion=conv)
    assert out == Pandoc(Para(Str("cell")))
    assert calls == [{"from": "gfm", "to": "json"}]


def test_ctx_conversion_and_format():
    seen = []
    f = Filter()

    @f.on(Str)
    def s(x, ctx):
        seen.append((ctx.format, ctx.conversion.output_format))

    f(Pandoc(Para(Str("a"))), conversion=Conversion("html", output_format="html+smart"))
    f(Pandoc(Para(Str("a"))), "latex")
    assert seen == [("html", "html+smart"), ("latex", None)]


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="needs pandoc")
def test_read_as_a_json_filter(tmp_path: Path):
    """Under pandoc --filter: ctx.read parses a code block's text as blocks."""
    src = Path(__file__).resolve().parents[1] / "src"
    script = tmp_path / "cells.py"
    script.write_text(
        textwrap.dedent(
            f"""\
            import sys
            sys.path.insert(0, {str(src)!r})
            from pandom import CodeBlock, Filter

            f = Filter()

            @f.on(CodeBlock)
            def cell(code, ctx):
                return ctx.read(code.text)

            f.main()
            """
        )
    )
    md = "```\n*inner* text\n```\n"
    out = subprocess.run(
        ["pandoc", "-t", "html", "--filter", str(script)],
        input=md.encode(),
        capture_output=True,
        check=True,
    ).stdout.decode()
    assert out.strip() == "<p><em>inner</em> text</p>"
