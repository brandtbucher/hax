import dis
import itertools
import re
import typing

import hypothesis
import pytest

import hax


def get_examples() -> typing.Iterator[str]:

    with open("README.md") as readme:
        examples = re.findall(r"\n```py(\n[^`]+\n)```\n", readme.read())

    for i, example in enumerate(itertools.accumulate(examples)):
        yield pytest.param(example, id=f"{i}")


@hypothesis.given(items=hypothesis.infer)
@pytest.mark.parametrize("code", get_examples())
def test_readme(code: str, items: typing.Sequence[object]) -> None:

    namespace: typing.Dict[str, typing.Any] = {"__name__": "__main__"}
    exec(code, namespace)

    actual = namespace["double"](items)
    expected = [*itertools.chain.from_iterable(zip(items, items))]

    assert actual == expected


@pytest.mark.parametrize("opname, opcode", dis.opmap.items())
def test_opcodes(opname: str, opcode: int) -> None:

    arg = dis.HAVE_ARGUMENT <= opcode

    assert hasattr(hax, opname)

    with pytest.raises(hax.HaxUsageError if arg else TypeError):
        getattr(hax, opname)(...)

    with pytest.raises(TypeError if arg else hax.HaxUsageError):
        getattr(hax, opname)()
