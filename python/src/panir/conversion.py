"""The pandoc conversion a filter runs in.

A filter function that takes a ``Context`` finds it in ``ctx.conversion``:
the output format, and, when known, the input and output formats with
extensions, the reader's options and the conversion's options. To parse a
fragment (a table cell, an attribute) the way the document was read, pass
it to libpandoc, whose realm calling pandoc is:

    import libpandoc

    @f.on(CodeBlock)
    def table(code, ctx):
        cells = libpandoc.read_many(texts, ctx.conversion)  # in parallel

How much is known depends on who runs the filter:

- **in process, with libpandoc** (``libpandoc.convert(..., filters=[f])``,
  ``pandocpy -F``): everything, including the input format pandoc decided
  on and the conversion's options;
- **as a JSON filter** under libpandoc (``libpandoc.convert(filters=
  ["f.py"])``): the formats too, from the environment
  (``$PANDOC_INPUT_FORMAT``);
- **as a JSON filter** under pandoc (``pandoc --filter``): the output
  format's name and the reader's options only, until pandoc also sets
  ``$PANDOC_INPUT_FORMAT`` (proposed: jgm/pandoc#11016).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["Conversion"]


class Conversion:
    """What a filter knows of the pandoc run it is part of.

    ``format`` is the output format's name, as pandoc passes it to a JSON
    filter (``"html5"``). ``input_format`` and ``output_format`` are the
    formats with extensions (``"commonmark_x-smart"``), when known.
    ``reader_options`` are the reader's options (pandoc's
    ``PANDOC_READER_OPTIONS``), and ``options`` the conversion's options, in
    pandoc's defaults-file keys, when known.
    """

    __slots__ = ("format", "input_format", "options", "output_format", "reader_options")

    def __init__(
        self,
        format: str | None = None,
        *,
        input_format: str | None = None,
        output_format: str | None = None,
        reader_options: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self.format = format
        self.input_format = input_format
        self.output_format = output_format
        self.reader_options = reader_options
        self.options = options

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

    def __repr__(self) -> str:
        known = {
            k: getattr(self, k)
            for k in ("format", "input_format", "output_format")
            if getattr(self, k) is not None
        }
        return f"Conversion({', '.join(f'{k}={v!r}' for k, v in known.items())})"
