from dis import HAVE_ARGUMENT, get_instructions, hasjabs, hasjrel, opmap
from sysconfig import get_path
from inspect import (  # pylint: disable = no-name-in-module
    CO_ASYNC_GENERATOR,
    CO_COROUTINE,
    CO_GENERATOR,
    signature,
)
from importlib import import_module, reload
from itertools import chain
from math import ceil
from os import walk
from os.path import splitext
from re import findall
from sys import maxsize, version_info
from types import CodeType, FunctionType
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    Sequence,
    List,
    Tuple,
    cast,
)
from unittest.mock import patch
from warnings import catch_warnings, simplefilter

from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import builds, lists
from pytest import mark, param, raises, skip, warns

import hax
from hax import (
    _checks,
    _helpers,
    BUILD_LIST,
    COMPARE_OP,
    EXTENDED_ARG,
    HAX_LABEL,
    HaxUsageError,
    HaxCompileError,
    JUMP_FORWARD,
    LABEL,
    LOAD_CONST,
    LOAD_DEREF,
    LOAD_FAST,
    LOAD_NAME,
    NOP,
    RETURN_VALUE,
    YIELD_VALUE,
)


def get_stdlib_functions() -> List[FunctionType]:

    stdlib = []

    _, packages, modules = next(walk(get_path("stdlib")))

    for package in packages:
        if not package.isidentifier():
            continue
        try:
            with catch_warnings():
                simplefilter("ignore")
                stdlib.append(import_module(package))
        except ImportError:
            pass
    for name, extension in map(
        cast(Callable[[str], Tuple[str, str]], splitext), modules
    ):
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


def get_examples() -> Generator[object, None, None]:

    with open("README.md", encoding="utf-8") as readme:
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


def test_hax_label() -> None:

    with raises(HaxUsageError):
        hax.HAX_LABEL(...)

    with raises(TypeError):
        hax.HAX_LABEL()  # type: ignore  # pylint: disable = no-value-for-parameter


@mark.parametrize(
    "test",
    get_stdlib_functions(),
    ids=lambda test: f"{test.__module__}.{test.__qualname__}",
)
def test_stdlib(test: Any) -> None:
    name = test.__name__ if test.__name__.isidentifier() else "_"
    if f"{test.__module__}.{test.__qualname__}" not in {
        "dis._get_instructions_bytes",
        "dis._unpack_opargs",
    }:
        assert hax.hax(test).__code__ is test.__code__
        assert hax.hax(test.__code__) is test.__code__
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
        if op.is_jump_target:
            definition += f"    HAX_LABEL({op.offset})\n"
        if op.opname == "EXTENDED_ARG":  # What does it even mean to do this?
            continue
        if op.opname == "LOAD_CONST":
            arg = repr(op.argval).replace("Ellipsis", "...")
        elif op.opname == "FORMAT_VALUE":
            arg = str(op.arg)
        elif HAVE_ARGUMENT <= op.opcode:
            arg = repr(op.argval)
        else:
            arg = ""
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
    if not (
        # This is pretty cool. We're *more* efficient than CPython for this one:
        f"{test.__module__}.{test.__qualname__}" == "textwrap.dedent"
        and (3, 10) <= version_info
    ):
        assert {*test.__code__.co_varnames} <= {*copy.__code__.co_varnames}
    assert len(ops) == len(copy_ops)
    for op, copy_op in zip(ops, copy_ops):
        assert op.opname == copy_op.opname, (op, copy_op)
        if op.opcode not in {*hasjabs, *hasjrel}:
            assert op.argval == copy_op.argval, (op, copy_op)


@mark.parametrize(
    "version",
    [
        (3, 6, 0, "final", 0),
        (3, 7, 0, "final", 0),
        (3, 8, 0, "final", 0),
        (3, 9, 0, "final", 0),
        (3, 10, 0, "final", 0),
    ],
)
def test_version(version: Tuple[int, int, int, str, int]) -> None:

    with patch("sys.version_info", version):

        if version < (3, 7):
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
            EXTENDED_ARG(-1)  # Use a different op here?


def test_bad_arg_large() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            EXTENDED_ARG(1 << 32)  # Use a different op here?


def test_okay_args() -> None:  # This should be refactored to actually test something.
    @hax.hax
    def _() -> None:
        EXTENDED_ARG((1 << 32) - 1)  # Use a different op here?
        EXTENDED_ARG((1 << 24) - 1)  # Use a different op here?
        EXTENDED_ARG((1 << 16) - 1)  # Use a different op here?
        EXTENDED_ARG((1 << 8) - 1)  # Use a different op here?


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
        def _() -> None:  # Use a different op here?
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
        def _() -> None:  # Use a different op here?
            EXTENDED_ARG()  # type: ignore  # pylint: disable = no-value-for-parameter


def test_function_to_generator() -> None:
    @hax.hax
    def _() -> None:
        LOAD_CONST(None)
        YIELD_VALUE()

    assert _.__code__.co_flags & CO_GENERATOR
    assert not _.__code__.co_flags & CO_ASYNC_GENERATOR
    assert not _.__code__.co_flags & CO_COROUTINE


def test_generator_to_generator() -> None:
    @hax.hax
    def _() -> Generator[None, None, None]:
        LOAD_CONST(None)
        YIELD_VALUE()
        yield

    assert _.__code__.co_flags & CO_GENERATOR
    assert not _.__code__.co_flags & CO_ASYNC_GENERATOR
    assert not _.__code__.co_flags & CO_COROUTINE


def test_coroutine_to_async_generator() -> None:
    @hax.hax
    async def _() -> None:
        LOAD_CONST(None)
        YIELD_VALUE()

    assert _.__code__.co_flags & CO_ASYNC_GENERATOR
    assert not _.__code__.co_flags & CO_GENERATOR
    assert not _.__code__.co_flags & CO_COROUTINE


def test_async_generator_to_async_generator() -> None:
    @hax.hax
    async def _() -> AsyncGenerator[None, None]:
        LOAD_CONST(None)
        YIELD_VALUE()
        yield

    assert _.__code__.co_flags & CO_ASYNC_GENERATOR
    assert not _.__code__.co_flags & CO_GENERATOR
    assert not _.__code__.co_flags & CO_COROUTINE


def test_code_type() -> None:
    def _() -> None:
        pass

    assert hax.hax(_.__code__) is _.__code__


def test_bad_usage() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            NOP = ...  # pylint: disable = redefined-outer-name, unused-variable


def test_old_label() -> None:
    with warns(DeprecationWarning):

        @hax.hax
        def _() -> None:
            JUMP_FORWARD(...)
            LABEL(...)


def test_duplicate_label() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            JUMP_FORWARD(...)
            HAX_LABEL(...)
            HAX_LABEL(...)


def test_local_non_string() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_FAST(...)  # type: ignore
            RETURN_VALUE()


def test_name_non_string() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_NAME(...)  # type: ignore
            RETURN_VALUE()


def test_compare_non_string() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_CONST(...)
            LOAD_CONST(...)
            COMPARE_OP(...)  # type: ignore
            RETURN_VALUE()


def test_compare_invalid() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_CONST(...)
            LOAD_CONST(...)
            COMPARE_OP("=")
            RETURN_VALUE()


def test_free_non_string() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_DEREF(...)  # type: ignore
            RETURN_VALUE()


def test_free_invalid() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            LOAD_DEREF("_")
            RETURN_VALUE()


def test_backward_jrel() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            HAX_LABEL(...)
            JUMP_FORWARD(...)


def test_non_int() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            BUILD_LIST(...)  # type: ignore
            RETURN_VALUE()


def test_missing_label() -> None:
    with raises(HaxCompileError):

        @hax.hax
        def _() -> None:
            JUMP_FORWARD(...)


def test_jump_absolute_long() -> None:
    # NOPS * 6 + CODE_SIZE - 2 * IS_JREL - 1 >= 1 << 16
    # NOPS * 6 + 30 - 2 * 0 - 1 >= 65536
    # NOPS * 6 >= 65507
    # NOPS >= 10917.8
    nops = "NOP();" * ceil(10917.8 * (2 if (3, 10) <= version_info else 1))
    definition = (
        f"@hax\ndef _():JUMP_ABSOLUTE(...);x=False;assert x;{nops}HAX_LABEL(...)"
    )
    namespace: Dict[str, Any] = {"hax": hax.hax}
    exec(definition, namespace)  # pylint: disable = exec-used
    assert namespace["_"]() is None


def test_jump_relative_long() -> None:
    # NOPS * 6 + CODE_SIZE - 2 * IS_JREL - 1 >= 1 << 16
    # NOPS * 6 + 30 - 2 * 1 - 1 >= 65536
    # NOPS * 6 >= 65509
    # NOPS >= 10918.2
    nops = "NOP();" * ceil(10918.2 * (2 if (3, 10) <= version_info else 1))
    definition = (
        f"@hax\ndef _():JUMP_FORWARD(...);x=False;assert x;{nops}HAX_LABEL(...)"
    )
    namespace: Dict[str, Any] = {"hax": hax.hax}
    exec(definition, namespace)  # pylint: disable = exec-used
    assert namespace["_"]() is None


def test_jump_absolute_longer() -> None:
    # NOPS * 6 + CODE_SIZE - 2 * IS_JREL - 1 >= 1 << 24
    # NOPS * 6 + 30 - 2 * 0 - 1 >= 16777216
    # NOPS * 6 >= 16777187
    # NOPS >= 2796197.8
    nops = "NOP();" * ceil(2796197.8 * (2 if (3, 10) <= version_info else 1))
    definition = (
        f"@hax\ndef _():JUMP_ABSOLUTE(...);x=False;assert x;{nops}HAX_LABEL(...)"
    )
    namespace: Dict[str, Any] = {"hax": hax.hax}
    exec(definition, namespace)  # pylint: disable = exec-used
    assert namespace["_"]() is None


def test_jump_relative_longer() -> None:
    # NOPS * 6 + CODE_SIZE - 2 * IS_JREL - 1 >= 1 << 24
    # NOPS * 6 + 30 - 2 * 1 - 1 >= 16777216
    # NOPS * 6 >= 16777189
    # NOPS >= 2796198.2
    nops = "NOP();" * ceil(2796198.2 * (2 if (3, 10) <= version_info else 1))
    definition = (
        f"@hax\ndef _():JUMP_FORWARD(...);x=False;assert x;{nops}HAX_LABEL(...)"
    )
    namespace: Dict[str, Any] = {"hax": hax.hax}
    exec(definition, namespace)  # pylint: disable = exec-used
    assert namespace["_"]() is None


def test_ignored_nop() -> None:
    @hax.hax
    @hax.hax
    def _() -> None:
        NOP()

    assert _() is None


def test_removed_opcodes() -> None:
    actual = {helper for helper in dir(_helpers) if helper[0] != "_"}
    actual -= {"HAX_LABEL", "HaxUsageError", "LABEL"}
    expected = set(opmap)
    assert actual == expected
