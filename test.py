from dis import HAVE_ARGUMENT, opmap
from itertools import chain
from re import findall
from typing import Any, Dict, Iterator, Sequence

from hypothesis import given
from hypothesis.strategies import builds, lists
from pytest import mark, param, raises

import hax


def get_examples() -> Iterator[str]:

    with open("README.md") as readme:
        examples = findall(r"\n```py(\n[^`]+\n)```\n", readme.read())

    for i, example in enumerate(examples):
        yield param(example, id=f"{i}")


@mark.parametrize("code", get_examples())
@given(items=lists(builds(object)))
def test_readme(code: str, items: Sequence[object]) -> None:

    namespace: Dict[str, Any] = {"__name__": "__main__"}
    exec(code, namespace)

    actual = namespace["doubled"](items)
    expected = [*chain.from_iterable(zip(items, items))]

    assert actual == expected


@mark.parametrize("opname, opcode", opmap.items())
def test_opcodes(opname: str, opcode: int) -> None:

    arg = HAVE_ARGUMENT <= opcode

    assert hasattr(hax, opname)

    with raises(hax.HaxUsageError if arg else TypeError):
        getattr(hax, opname)(...)

    with raises(TypeError if arg else hax.HaxUsageError):
        getattr(hax, opname)()
