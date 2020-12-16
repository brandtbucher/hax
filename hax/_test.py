from dis import HAVE_ARGUMENT, get_instructions, hasjabs, hasjrel, opmap
from distutils.sysconfig import get_python_lib
from inspect import signature
from importlib import import_module, reload
from itertools import chain
from os import walk
from os.path import splitext
from re import findall
from sys import maxsize, version_info
from types import CodeType, FunctionType
from typing import Any, Dict, Iterator, Sequence, List, Tuple
from unittest.mock import patch
from warnings import catch_warnings, simplefilter

from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import builds, lists
from pytest import mark, param, raises, skip

import hax
from hax import _checks, EXTENDED_ARG, HaxUsageError, HaxCompileError, NOP


def get_stdlib_functions() -> List[FunctionType]:

    stdlib = []

    _, packages, modules = next(walk(get_python_lib(standard_lib=True)))

    for package in packages:
        if not package.isidentifier():
            continue
        try:
            with catch_warnings():
                simplefilter("ignore")
                stdlib.append(import_module(package))
        except ImportError:
            pass

    for name, extension in map(splitext, modules):  # type: ignore
        assert isinstance(name, str)
        if extension != ".py" or not name.isidentifier() or name == "antigravity":
            continue
        try:
            with catch_warnings():
                simplefilter("ignore")
                stdlib.append(import_module(name))
        except ImportError:
            pass

    return [
        *{
            function.__code__: function
            for name, function in sorted(
                {
                    f"{function.__module__}.{function.__qualname__}": function
                    for module in stdlib
                    for attribute in vars(module).values()
                    for function in (
                        vars(attribute).values()
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
    ]


def get_examples() -> Iterator[object]:

    with open("README.md") as readme:
        examples = findall(r"\n```py(\n[^`]+\n)```\n", readme.read())

    for i, example in enumerate(examples):
        yield param(example, id=f"{i}")


@mark.parametrize("code", get_examples())
@settings(suppress_health_check=[HealthCheck.too_slow])
@given(items=lists(builds(object), max_size=maxsize // 2))
def test_readme(code: str, items: Sequence[object]) -> None:

    namespace: Dict[str, Any] = {"__name__": "__main__"}
    exec(code, namespace)  # pylint: disable = exec-used

    actual = namespace["doubled"](items)
    expected = [*chain.from_iterable(zip(items, items))]

    assert actual == expected


@mark.parametrize("opname, opcode", opmap.items())
def test_opcode(opname: str, opcode: int) -> None:

    arg = HAVE_ARGUMENT <= opcode

    assert hasattr(hax, opname)

    with raises(HaxUsageError if arg else TypeError):
        getattr(hax, opname)(...)

    with raises(TypeError if arg else HaxUsageError):
        getattr(hax, opname)()


def test_label() -> None:

    with raises(HaxUsageError):
        hax.LABEL(...)

    with raises(TypeError):
        hax.LABEL()  # type: ignore  # pylint: disable = no-value-for-parameter


@mark.parametrize(
    "test",
    get_stdlib_functions(),
    ids=lambda test: f"{test.__module__}.{test.__qualname__}",
)
def test_stdlib(test: Any) -> None:
    name = test.__name__ if test.__name__.isidentifier() else "_"
    if (
        f"{test.__module__}.{test.__qualname__}" == "mimetypes._default_mime_types"
        and version_info < (3, 7)
    ):
        skip()
    definition = f"@hax\ndef {name}({', '.join(signature(test, follow_wrapped=False).parameters)}):\n"
    if test.__code__.co_freevars:
        definition = f"def __():\n  {' = '.join(test.__code__.co_freevars)} = ...\n  @hax\n  def {name}({', '.join(signature(test, follow_wrapped=False).parameters)}):\n    nonlocal {', '.join(test.__code__.co_freevars)}\n"
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
        definition += f"  return {name}\n{name} = __()"
    namespace: Dict[str, Any] = {"hax": hax.hax}
    print(definition)
    exec(definition, namespace)  # pylint: disable = exec-used
    copy = namespace[name]
    copy_ops = [
        op for op in get_instructions(copy) if op.opname not in {"NOP", "EXTENDED_ARG"}
    ][
        :-2
    ]  # Last two are LOAD_CONST(None); RETURN_VALUE()
    # assert test.__code__.co_argcount == copy.__code__.co_argcount
    assert test.__code__.co_cellvars == copy.__code__.co_cellvars
    assert test.__code__.co_freevars == copy.__code__.co_freevars
    # assert test.__code__.co_kwonlyargcount == copy.__code__.co_kwonlyargcount
    assert test.__code__.co_nlocals == test.__code__.co_nlocals
    if not (
        # This is pretty cool. We're *more* efficient than CPython for this one:
        f"{test.__module__}.{test.__qualname__}"
        == "turtle.TurtleScreenBase._createpoly"
        and version_info < (3, 7)
    ):
        assert test.__code__.co_stacksize <= copy.__code__.co_stacksize
    assert {*test.__code__.co_varnames} <= {*copy.__code__.co_varnames}
    assert len(ops) == len(copy_ops)
    for op, copy_op in zip(ops, copy_ops):
        assert op.opname == copy_op.opname, (op, copy_op)
        if op.opcode not in {*hasjabs, *hasjrel}:
            assert op.argval == copy_op.argval, (op, copy_op)


@mark.parametrize(
    "version",
    [
        (3, 5, 0, "final", 0),
        (3, 6, 0, "final", 0),
        (3, 7, 0, "final", 0),
        (3, 8, 0, "final", 0),
        (3, 9, 0, "final", 0),
    ],
)
def test_version(version: Tuple[int, int, int, str, int]) -> None:

    with patch("sys.version_info", version):

        if version < (3, 6):
            with raises(RuntimeError):
                reload(_checks)
        else:
            reload(_checks)


def test_implementation_cpython() -> None:

    with patch("sys.implementation.name", "cpython"):
        reload(_checks)


def test_implementation_other() -> None:

    with patch("sys.implementation.name", "pypy"):
        with raises(RuntimeError):
            reload(_checks)


def test_bad_arg_negative() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            EXTENDED_ARG(-1)


def test_bad_arg_large() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            EXTENDED_ARG(1 << 32)


def test_okay_args() -> None:
    @hax.hax
    def _() -> None:
        EXTENDED_ARG((1 << 32) - 1)
        EXTENDED_ARG((1 << 24) - 1)
        EXTENDED_ARG((1 << 16) - 1)
        EXTENDED_ARG((1 << 8) - 1)


def test_bad_type() -> None:
    with raises(TypeError):
        hax.hax(object())


def test_bad_usage_no_call() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            NOP  # pylint: disable = pointless-statement


def test_bad_usage_non_simple() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            EXTENDED_ARG(_)  # type: ignore  # pylint: disable = too-many-function-args


def test_bad_usage_non_statement() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            NOP(),  # type: ignore  # pylint: disable = expression-not-assigned


def test_bad_usage_arg_when_none_expected() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            NOP(...)  # type: ignore  # pylint: disable = too-many-function-args


def test_bad_usage_none_when_expected() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            EXTENDED_ARG()  # type: ignore  # pylint: disable = no-value-for-parameter
