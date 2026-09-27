"""The pandoc conversion a filter runs in, and calling pandoc from a filter.

A filter function that takes a ``Context`` finds it in ``ctx.conversion``;
``ctx.read(text)`` parses a fragment (a table cell, an attribute) the way
the document was read:

    @f.on(CodeBlock)
    def table(code, ctx):
        ...
        cell = ctx.read(text)  # a list of blocks

How much is known depends on who runs the filter:

- **in process, with libpandoc** (``libpandoc.convert(..., filters=[f])``,
  ``pandocpy -F``): everything, including the input format pandoc decided
  on and the conversion's options;
- **as a JSON filter** under libpandoc (``libpandoc.convert(filters=
  ["f.py"])``): the same, from the environment (``$PANDOC_INPUT_FORMAT``);
- **as a JSON filter** under pandoc (``pandoc --filter``): the output
  format's name and the reader's options only, until pandoc also sets
  ``$PANDOC_INPUT_FORMAT`` (proposed: jgm/pandoc#11016); ``read`` assumes
  markdown unless given a format.

``read`` calls pandoc through libpandoc when it is installed, else the
``pandoc`` executable (or ``$PANDOC``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ._types import Block, Pandoc

__all__ = ["Conversion"]

# Runs pandoc: (text, options in defaults-file keys) -> output text.
PandocFunction = Callable[[str, Mapping[str, Any]], str]

# The conversion's options that also apply to reading a fragment of it.
_READ_OPTIONS = frozenset(
    {
        "abbreviations",
        "data-dir",
        "default-image-extension",
        "indented-code-classes",
        "preserve-tabs",
        "resource-path",
        "sandbox",
        "strip-comments",
        "tab-stop",
        "track-changes",
    }
)

# Reader options (as pandoc gives filters) that have a defaults-file key.
_READER_OPTIONS = {
    "default-image-extension": "default-image-extension",
    "indented-code-classes": "indented-code-classes",
    "strip-comments": "strip-comments",
    "tab-stop": "tab-stop",
}
_TRACK_CHANGES = {"accept-changes": "accept", "reject-changes": "reject", "all-changes": "all"}


class Conversion:
    """What a filter knows of the pandoc run it is part of.

    ``format`` is the output format's name, as pandoc passes it to a JSON
    filter (``"html5"``). ``input_format`` and ``output_format`` are the
    formats with extensions (``"commonmark_x-smart"``), when known.
    ``reader_options`` are the reader's options (pandoc's
    ``PANDOC_READER_OPTIONS``), and ``options`` the conversion's options, in
    pandoc's defaults-file keys, when known. ``pandoc`` runs pandoc for
    ``read``; the default uses libpandoc if installed, else the executable.
    """

    __slots__ = ("_pandoc", "format", "input_format", "options", "output_format", "reader_options")

    def __init__(
        self,
        format: str | None = None,
        *,
        input_format: str | None = None,
        output_format: str | None = None,
        reader_options: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        pandoc: PandocFunction | None = None,
    ) -> None:
        self.format = format
        self.input_format = input_format
        self.output_format = output_format
        self.reader_options = reader_options
        self.options = options
        self._pandoc = pandoc

    @classmethod
    def from_environment(cls, argv: Sequence[str] | None = None) -> Conversion:
        """The conversion of a JSON filter that pandoc is running.

        pandoc passes the output format as the first argument and the
        reader's options in ``$PANDOC_READER_OPTIONS``. libpandoc also passes
        the formats with extensions, ``$PANDOC_INPUT_FORMAT`` and
        ``$PANDOC_OUTPUT_FORMAT`` (proposed to pandoc: jgm/pandoc#11016).
        """
        argv = sys.argv[1:] if argv is None else argv
        env = os.environ.get("PANDOC_READER_OPTIONS")
        return cls(
            argv[0] if argv else None,
            input_format=os.environ.get("PANDOC_INPUT_FORMAT") or None,
            output_format=os.environ.get("PANDOC_OUTPUT_FORMAT") or None,
            reader_options=json.loads(env) if env else None,
        )

    @classmethod
    def from_context(
        cls,
        context: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
        pandoc: PandocFunction | None = None,
    ) -> Conversion:
        """The conversion libpandoc describes to an in-process filter."""
        return cls(
            context.get("format"),
            input_format=context.get("input-format"),
            output_format=context.get("output-format"),
            reader_options=context.get("reader-options"),
            options=options,
            pandoc=pandoc,
        )

    def read_options(self, format: str | None = None) -> dict[str, Any]:
        """Options to read a fragment as this conversion reads its input.

        The input format (``format`` overrides it) and the options that
        affect reading; not filters, templates, metadata or the output.
        """
        opts: dict[str, Any] = {}
        if self.options is not None:
            opts.update((k, v) for k, v in self.options.items() if k in _READ_OPTIONS)
        elif self.reader_options is not None:
            for k, key in _READER_OPTIONS.items():
                if k in self.reader_options:
                    opts[key] = self.reader_options[k]
            tc = _TRACK_CHANGES.get(self.reader_options.get("track-changes", ""))
            if tc:
                opts["track-changes"] = tc
        given = self.options or {}
        opts["from"] = (
            format or self.input_format or given.get("from") or given.get("reader") or "markdown"
        )
        opts["to"] = "json"
        return opts

    def read(self, text: str, format: str | None = None) -> list[Block]:
        """Parse ``text`` as this conversion reads its input: its blocks."""
        out = self.pandoc(text, self.read_options(format))
        return list(Pandoc.from_json(json.loads(out)).blocks)

    def pandoc(self, text: str, options: Mapping[str, Any]) -> str:
        """Run pandoc on ``text`` with ``options`` (defaults-file keys)."""
        return (self._pandoc or default_pandoc)(text, options)

    def __repr__(self) -> str:
        known = {
            k: getattr(self, k)
            for k in ("format", "input_format", "output_format")
            if getattr(self, k) is not None
        }
        return f"Conversion({', '.join(f'{k}={v!r}' for k, v in known.items())})"


def default_pandoc(text: str, options: Mapping[str, Any]) -> str:
    """Run pandoc: through libpandoc if installed, else the executable."""
    try:
        import libpandoc  # type: ignore[import-not-found]
    except ImportError:
        return _pandoc_executable(text, options)
    out = libpandoc.convert(text, options=dict(options))
    return out if isinstance(out, str) else out.decode("utf-8")


def _pandoc_executable(text: str, options: Mapping[str, Any]) -> str:
    exe = os.environ.get("PANDOC", "pandoc")
    with tempfile.TemporaryDirectory() as tmp:
        # JSON is YAML, so the options are a defaults file as they are
        defaults = os.path.join(tmp, "defaults.yaml")
        with open(defaults, "w", encoding="utf-8") as f:
            json.dump(dict(options), f)
        proc = subprocess.run(
            [exe, "--defaults", defaults], input=text.encode("utf-8"), capture_output=True
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{exe} failed ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout.decode("utf-8")
