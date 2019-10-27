from dis import HAVE_ARGUMENT, get_instructions, hasjabs, hasjrel, opmap
from distutils.sysconfig import get_python_lib
from inspect import signature
from importlib import import_module
from itertools import chain
from os import walk
from os.path import splitext
from re import findall
from types import CodeType, FunctionType, LambdaType
from typing import Any, Dict, Iterator, Sequence, List

from hypothesis import given
from hypothesis.strategies import builds, lists
from pytest import mark, param, raises

import hax


def get_stdlib_functions() -> List[FunctionType]:

    stdlib = []

    _, packages, modules = next(walk(get_python_lib(standard_lib=True)))

    for package in packages:
        if not package.isidentifier():
            continue
        try:
            stdlib.append(import_module(package))
        except ImportError:
            pass

    for name, extension in map(splitext, modules):  # type: ignore
        assert isinstance(name, str)
        if extension != ".py" or not name.isidentifier() or name == "antigravity":
            continue
        try:
            stdlib.append(import_module(name))
        except ImportError:
            pass

    return list(
        {
            function.__code__: function
            for name, function in sorted(
                {
                    f"{function.__module__}.{function.__qualname__}": function
                    for module in stdlib
                    for attribute in vars(module).values()
                    for function in (
                        vars(attribute).values()  # type: ignore
                        if isinstance(attribute, type)
                        else (attribute,)
                    )
                    if isinstance(function, FunctionType)
                    and not any(
                        isinstance(const, (CodeType, frozenset))
                        for const in function.__code__.co_consts  # pylint: disable = no-member
                    )
                }.items()
            )
        }.values()
    )


def get_examples() -> Iterator[str]:

    with open("README.md") as readme:
        examples = findall(r"\n```py(\n[^`]+\n)```\n", readme.read())

    for i, example in enumerate(examples):
        yield param(example, id=f"{i}")


@mark.parametrize("code", get_examples())  # type: ignore
@given(items=lists(builds(object)))
def test_readme(code: str, items: Sequence[object]) -> None:

    namespace: Dict[str, Any] = {"__name__": "__main__"}
    exec(code, namespace)  # pylint: disable = exec-used

    actual = namespace["doubled"](items)
    expected = [*chain.from_iterable(zip(items, items))]

    assert actual == expected


@mark.parametrize("opname, opcode", opmap.items())  # type: ignore
def test_opcode(opname: str, opcode: int) -> None:

    arg = HAVE_ARGUMENT <= opcode

    assert hasattr(hax, opname)

    with raises(hax.HaxUsageError if arg else TypeError):
        getattr(hax, opname)(...)

    with raises(TypeError if arg else hax.HaxUsageError):
        getattr(hax, opname)()


tested = set()


@mark.parametrize(  # type: ignore
    "test",
    get_stdlib_functions(),
    ids=lambda test: f"{test.__module__}.{test.__qualname__}",
)
def test_stdlib(test: Any) -> None:
    name = test.__name__ if not isinstance(test, LambdaType) else "_lambda"
    definition = f"@hax\ndef {name}({', '.join(signature(test, follow_wrapped=False).parameters)}):\n"
    if test.__code__.co_freevars:
        definition = f"def _wrapper():\n  {' = '.join(test.__code__.co_freevars)} = ...\n  @hax\n  def {name}({', '.join(signature(test, follow_wrapped=False).parameters)}):\n    nonlocal {', '.join(test.__code__.co_freevars)}\n"
    ops = [
        op for op in get_instructions(test) if op.opname not in {"NOP", "EXTENDED_ARG"}
    ]
    for op in get_instructions(test):
        if op.opname == "LOAD_CONST":
            arg = repr(op.argval).replace("Ellipsis", "...")
        elif op.opname == "FORMAT_VALUE":
            arg = str(op.arg)
        elif HAVE_ARGUMENT <= op.opcode:
            arg = repr(op.argval)
        else:
            arg = ""
        if op.is_jump_target:
            definition += f"    LABEL({op.offset})\n"
        definition += f"    {op.opname}({arg})\n"
    if test.__code__.co_freevars:
        definition += f"  return {name}\n{name} = _wrapper()"
    namespace: Dict[str, Any] = {"hax": hax.hax}
    print(definition)
    exec(definition, namespace)  # pylint: disable = exec-used
    copy = namespace[name]
    copy_ops = [
        op for op in get_instructions(copy) if op.opname not in {"NOP", "EXTENDED_ARG"}
    ][
        :-2
    ]  # Last two are LOAD_CONST(None); RETURN_VALUE()
    assert len(ops) == len(copy_ops)
    for op, copy_op in zip(ops, copy_ops):
        assert op.opname == copy_op.opname, (op, copy_op)
        if op.opcode not in {*hasjabs, *hasjrel}:
            assert op.argval == copy_op.argval, (op, copy_op)

        tested.add(op.opname)


def test_opcodes() -> None:
    expected = {*opmap} - {
        "BEFORE_ASYNC_WITH",
        "BINARY_MATRIX_MULTIPLY",
        "BUILD_LIST_UNPACK",
        "BUILD_MAP_UNPACK",
        "BUILD_SET_UNPACK",
        "BUILD_TUPLE_UNPACK",
        "DELETE_DEREF",
        "DELETE_NAME",
        "EXTENDED_ARG",
        "GET_AITER",
        "GET_ANEXT",
        "IMPORT_STAR",
        "INPLACE_MATRIX_MULTIPLY",
        "INPLACE_POWER",
        "LIST_APPEND",
        "LOAD_BUILD_CLASS",
        "LOAD_CLASSDEREF",
        "LOAD_CLOSURE",
        "LOAD_NAME",
        "MAKE_FUNCTION",
        "MAP_ADD",
        "NOP",
        "PRINT_EXPR",
        "SET_ADD",
        "SETUP_ANNOTATIONS",
        "SETUP_ASYNC_WITH",
        "STORE_DEREF",
        "STORE_NAME",
    }
    assert tested == expected
