"""Type checkers read the generated declarations."""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

SAMPLE = textwrap.dedent("""
    from pandom import Header, Para, Str

    h = Header(1, Str("x"))
    h.level = "2"
    Para(Header(1))
    reveal_type(h.content)
""")


@pytest.mark.skipif(shutil.which("pyright") is None, reason="needs pyright")
def test_pyright_sees_field_and_argument_types(tmp_path):
    (tmp_path / "sample.py").write_text(SAMPLE)
    (tmp_path / "pyrightconfig.json").write_text(
        json.dumps({"extraPaths": [str(SRC)], "pythonVersion": "3.10"})
    )
    out = subprocess.run(
        [
            "pyright",
            "--outputjson",
            "-p",
            str(tmp_path / "pyrightconfig.json"),
            str(tmp_path / "sample.py"),
        ],
        capture_output=True,
        text=True,
    ).stdout
    found = [
        (d["range"]["start"]["line"], d["severity"], d["message"].splitlines()[0])
        for d in json.loads(out)["generalDiagnostics"]
    ]
    assert found == [
        (4, "error", 'Cannot assign to attribute "level" for class "Header"'),
        (
            5,
            "error",
            'Argument of type "Header" cannot be assigned to parameter "content" '
            'of type "Inline | str" in function "__init__"',
        ),
        (6, "information", 'Type of "h.content" is "list[Inline]"'),
    ]
