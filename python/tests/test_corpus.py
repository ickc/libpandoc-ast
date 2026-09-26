"""The shared corpus: what every binding must accept and reject."""

import libpandoc_ast as A
import pytest
from conftest import jsonl

VALID = jsonl("arbitrary.jsonl") + jsonl("pandoc.jsonl")
INVALID = jsonl("invalid.jsonl")


@pytest.mark.parametrize("j", VALID, ids=range(len(VALID)))
def test_round_trip(j):
    assert A.Pandoc.from_json(j).to_json() == j


@pytest.mark.parametrize("case", INVALID, ids=[c["name"] for c in INVALID])
def test_invalid(case):
    with pytest.raises(A.ASTDecodeError) as e:
        A.Pandoc.from_json(case["document"])
    assert list(e.value.path) == case["path"]


@pytest.mark.parametrize("j", VALID[:40], ids=range(40))
def test_repr_evaluates_to_an_equal_document(j):
    doc = A.Pandoc.from_json(j)
    assert eval(repr(doc), vars(A)) == doc


def test_every_constructor_is_in_the_corpus(valid_docs):
    seen = set()

    def note(node):
        seen.add(type(node).__name__)

    for j in valid_docs:
        A.walk(A.Pandoc.from_json(j), lambda n, ctx: note(n))
    classes = {
        n
        for n in A.__all__
        if isinstance(getattr(A, n), type)
        and issubclass(getattr(A, n), A.Node)
        and getattr(A, n) is not A.Node
        and getattr(A, n).__dict__.get("_kind") != "sum"
    }
    assert classes - seen == set()
