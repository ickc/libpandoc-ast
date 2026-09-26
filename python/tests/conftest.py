import json
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[2] / "corpus"


def jsonl(name: str) -> list:
    # split on "\n" only: strings may hold other line separators
    text = (CORPUS / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.split("\n") if line]


@pytest.fixture(scope="session")
def valid_docs() -> list:
    return jsonl("arbitrary.jsonl") + jsonl("pandoc.jsonl")
