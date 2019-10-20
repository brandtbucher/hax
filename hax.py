import dis
import os
import sys
import types
import typing


__version__ = "0.1.0"


if sys.version_info < (3, 6, 2):
    raise RuntimeError("HAX only supports Python 3.6.2+!")


if sys.implementation.name != "cpython":
    raise RuntimeError("HAX only supports CPython!")


_F = typing.TypeVar("_F", bound=typing.Callable[..., typing.Any])


_USAGE_MESSAGE = "HAX inline bytecode functions are not meant to be used directly; you must decorate any functions that use them with @hax."


_CALL_FUNCTION = dis.opmap["CALL_FUNCTION"]
_EXTENDED_ARG = dis.opmap["EXTENDED_ARG"]
_LOAD_CONST = dis.opmap["LOAD_CONST"]
_NOP = dis.opmap["NOP"]
_POP_TOP = dis.opmap["POP_TOP"]


class HaxCompileError(SyntaxError):
    pass


class HaxUsageError(RuntimeError):
    pass


def _raise_hax_error(
    message: str, filename: str, line: int, op: dis.Instruction
) -> typing.NoReturn:

    if os.path.isfile(filename):
        with open(filename) as file:
            for line_number, text in enumerate(file, 1):
                if line_number != line:
                    continue
                source: typing.Optional[str] = text
                if op.starts_line:
                    column: typing.Optional[int] = text.find(str(op.argval))
                    if column == -1:
                        column = None
                break
    else:
        source = column = None

    raise HaxCompileError(message, (filename, line, column, source))


def _instructions_with_lines(
    code: types.CodeType
) -> typing.Iterator[typing.Tuple[dis.Instruction, int]]:
    line = code.co_firstlineno
    for instruction in dis.get_instructions(code):
        line = instruction.starts_line or line
        yield instruction, line


def _backfill(
    arg: int,
    start: int,
    line: int,
    following: dis.Instruction,
    offset: int,
    new_op: int,
    filename: str,
) -> typing.Iterator[int]:

    size = ((offset - start) >> 1) + 1

    assert 1 <= size < 5

    if (1 << 32) - 1 < arg:
        message = f"Args greater than {(1 << 32) - 1:,} aren't supported (got {arg:,})!"
        _raise_hax_error(message, filename, line, following)

    if arg < 0:
        message = f"Args less than 0 aren't supported (got {arg:,})!"
        _raise_hax_error(message, filename, line, following)

    if 1 << 24 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 24 & 255
    elif 4 <= size:
        yield _NOP
        yield 0

    if 1 << 16 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 16 & 255
    elif 3 <= size:
        yield _NOP
        yield 0

    if 1 << 8 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 8 & 255
    elif 2 <= size:
        yield _NOP
        yield 0

    yield new_op
    yield arg & 255


def hax(function: _F) -> _F:

    ops = _instructions_with_lines(function.__code__)

    code = bytearray(function.__code__.co_code)
    names = list(function.__code__.co_names)
    stacksize = function.__code__.co_stacksize
    varnames = list(function.__code__.co_varnames)

    labels: typing.Dict[typing.Hashable, int] = {}
    deferred_labels: typing.Dict[
        typing.Hashable, typing.List[typing.Dict[str, typing.Any]]
    ] = {}

    start = 0

    for _ in range((len(code) >> 1) + 1):

        for op, line in ops:
            if op.opcode != _EXTENDED_ARG:
                break
        else:
            break

        if op.argval not in dis.opmap and op.argval != "LABEL":
            start = op.offset + 2
            continue

        if op.opname not in {
            # "LOAD_CLASSDEREF",
            # "LOAD_CLOSURE",
            # "LOAD_DEREF",
            "LOAD_FAST",
            "LOAD_GLOBAL",
            "LOAD_NAME",
        }:
            message = "Ops must consist of a simple call."
            _raise_hax_error(message, function.__code__.co_filename, line, op)

        args = 0
        arg = 0

        for following, _ in ops:

            if following.opcode == _EXTENDED_ARG:
                continue

            if following.opcode == _LOAD_CONST:
                arg = following.argval
                args += 1
                continue

            break

        else:
            message = "Ops must consist of a simple call."
            _raise_hax_error(message, function.__code__.co_filename, line, op)

        if following.opcode != _CALL_FUNCTION:
            message = "Ops must consist of a simple call."
            _raise_hax_error(message, function.__code__.co_filename, line, op)

        following, _ = next(ops)

        if following.opcode != _POP_TOP:
            message = "Ops must be standalone statements."
            _raise_hax_error(message, function.__code__.co_filename, line, op)

        line = following.starts_line or line

        if op.argval == "LABEL":
            code[start : following.offset + 2] = _backfill(
                arg=0,
                start=start,
                line=line,
                following=following,
                offset=following.offset,
                new_op=_NOP,
                filename=function.__code__.co_filename,
            )
            offset = following.offset
            labels[arg] = offset
            for info in deferred_labels.pop(arg, ()):
                info["arg"] = offset - info["arg"]
                code[info["start"] : info["offset"] + 2] = _backfill(**info)
            start = following.offset + 2
            continue

        new_op = dis.opmap[op.argval]

        has_arg = dis.HAVE_ARGUMENT <= new_op

        if args != has_arg:
            message = (
                f"Number of arguments is wrong (expected {int(has_arg)}, got {args})."
            )
            _raise_hax_error(message, function.__code__.co_filename, line, op)

        if new_op in dis.hasname:
            assert isinstance(arg, str)
            try:
                arg = names.index(arg)
            except ValueError:
                names.append(arg)
                arg = len(names) - 1
        elif new_op in dis.hasconst:
            arg = function.__code__.co_consts.index(arg)
        elif new_op in dis.hascompare:
            try:
                arg = dis.cmp_op.index(arg)
            except ValueError:
                message = f"Bad comparision operator {arg!r}; expected one of {' / '.join(map(repr, dis.cmp_op))}!"
                _raise_hax_error(
                    message, function.__code__.co_filename, line, following
                )
        elif new_op in dis.haslocal:
            assert isinstance(arg, str)
            try:
                arg = varnames.index(arg)
            except ValueError:
                varnames.append(arg)
                arg = len(varnames) - 1
        elif new_op in dis.hasfree:
            try:
                arg = (
                    function.__code__.co_cellvars + function.__code__.co_freevars
                ).index(arg)
            except ValueError:
                message = f'No free/cell variable {arg!r}; maybe use "nonlocal" in the inner scope to compile correctly?'
                _raise_hax_error(
                    message, function.__code__.co_filename, line, following
                )
        elif new_op in dis.hasjabs:
            if arg in labels:
                arg = labels[arg]
            else:
                deferred_labels.setdefault(arg, []).append(
                    dict(
                        arg=0,
                        start=start,
                        line=line,
                        following=following,
                        offset=following.offset,
                        new_op=new_op,
                        filename=function.__code__.co_filename,
                    )
                )
                start = following.offset + 2
                continue
        elif new_op in dis.hasjrel:
            if arg in labels:
                arg = following.offset + 2 - labels[arg]
            else:
                deferred_labels.setdefault(arg, []).append(
                    dict(
                        arg=following.offset + 2,
                        start=start,
                        line=line,
                        following=following,
                        offset=following.offset,
                        new_op=new_op,
                        filename=function.__code__.co_filename,
                    )
                )
                start = following.offset + 2
                continue
        elif not isinstance(arg, int):
            message = f"Expected integer argument, got {arg!r}."
            _raise_hax_error(message, function.__code__.co_filename, line, following)

        code[start : following.offset + 2] = _backfill(
            arg=arg,
            start=start,
            line=line,
            following=following,
            offset=following.offset,
            new_op=new_op,
            filename=function.__code__.co_filename,
        )

        start = following.offset + 2

        # This is the worst-case stack size... but we can probably be more exact.
        stacksize = max(
            stacksize, stacksize + dis.stack_effect(new_op, arg if has_arg else None)
        )

    else:

        assert False, "Main loop exited prematurely!"

    if deferred_labels:
        raise HaxUsageError(
            f"The following labels don't exist: {', '.join(map(repr, deferred_labels))}"
        )

    assert len(function.__code__.co_code) == len(code), "Code changed size!"

    new = types.FunctionType(
        types.CodeType(  # type: ignore
            function.__code__.co_argcount,
            *(
                (function.__code__.co_posonlyargcount,)  # type: ignore
                if hasattr(function.__code__, "co_posonlyargcount")
                else ()
            ),
            function.__code__.co_kwonlyargcount,
            len(varnames),
            stacksize,
            function.__code__.co_flags,
            bytes(code),
            function.__code__.co_consts,
            tuple(names),
            tuple(varnames),
            function.__code__.co_filename,
            function.__code__.co_name,
            function.__code__.co_firstlineno,
            function.__code__.co_lnotab,
            function.__code__.co_freevars,
            function.__code__.co_cellvars,
        ),
        function.__globals__,  # type: ignore
        function.__name__,
        function.__defaults__,  # type: ignore
        function.__closure__,  # type: ignore
    )

    new.__annotations__ = function.__annotations__.copy()
    new.__kwdefaults__ = (function.__kwdefaults__ or {}).copy() or None  # type: ignore
    new.__dict__ = function.__dict__.copy()

    return new  # type: ignore


def LABEL(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BEFORE_ASYNC_WITH() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= sys.version_info:

    def BEGIN_FINALLY() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_ADD() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_AND() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_FLOOR_DIVIDE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_LSHIFT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_MATRIX_MULTIPLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_MODULO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_MULTIPLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_OR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_POWER() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_RSHIFT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_SUBSCR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_SUBTRACT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_TRUE_DIVIDE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BINARY_XOR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if sys.version_info < (3, 8):

    def BREAK_LOOP() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_CONST_KEY_MAP(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_LIST(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_LIST_UNPACK(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_MAP(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_MAP_UNPACK(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_MAP_UNPACK_WITH_CALL(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_SET(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_SET_UNPACK(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_SLICE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_STRING(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_TUPLE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_TUPLE_UNPACK(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BUILD_TUPLE_UNPACK_WITH_CALL(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= sys.version_info:

    def CALL_FINALLY(arg: typing.Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_EX(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_KW(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= sys.version_info:

    def CALL_METHOD(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def COMPARE_OP(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if sys.version_info < (3, 8):

    def CONTINUE_LOOP(arg: typing.Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_ATTR(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_DEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_FAST(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_GLOBAL(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_NAME(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DELETE_SUBSCR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DUP_TOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DUP_TOP_TWO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= sys.version_info:

    def END_ASYNC_FOR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def END_FINALLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def EXTENDED_ARG(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FORMAT_VALUE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FOR_ITER(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def GET_AITER() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def GET_ANEXT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def GET_AWAITABLE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def GET_ITER() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def GET_YIELD_FROM_ITER() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def IMPORT_FROM(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def IMPORT_NAME(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def IMPORT_STAR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_ADD() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_AND() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_FLOOR_DIVIDE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_LSHIFT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_MATRIX_MULTIPLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_MODULO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_MULTIPLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_OR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_POWER() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_RSHIFT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_SUBTRACT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_TRUE_DIVIDE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def INPLACE_XOR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_ABSOLUTE(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_FORWARD(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_FALSE_OR_POP(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_TRUE_OR_POP(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LIST_APPEND(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= sys.version_info:

    def LOAD_ASSERTION_ERROR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_ATTR(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_BUILD_CLASS() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_CLASSDEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_CLOSURE(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_CONST(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_DEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_FAST(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_GLOBAL(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= sys.version_info:

    def LOAD_METHOD(arg: str) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_NAME(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def MAKE_FUNCTION(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def MAP_ADD(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def NOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_BLOCK() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_EXCEPT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= sys.version_info:

    def POP_FINALLY(arg: bool) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_FALSE(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_TRUE(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_TOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def PRINT_EXPR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def RAISE_VARARGS(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def RETURN_VALUE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= sys.version_info:

    def ROT_FOUR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def ROT_THREE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def ROT_TWO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ANNOTATIONS() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ASYNC_WITH(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if sys.version_info < (3, 8):

    def SETUP_EXCEPT(arg: typing.Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_FINALLY(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if sys.version_info < (3, 8):

    def SETUP_LOOP(arg: typing.Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_WITH(arg: typing.Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SET_ADD(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_ATTR(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if sys.version_info < (3, 7):

    def STORE_ANNOTATION(arg: str) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def STORE_DEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_FAST(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_GLOBAL(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_NAME(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_SUBSCR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNARY_INVERT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNARY_NEGATIVE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNARY_NOT() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNARY_POSITIVE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNPACK_EX(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def UNPACK_SEQUENCE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def WITH_CLEANUP_FINISH() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def WITH_CLEANUP_START() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def YIELD_FROM() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def YIELD_VALUE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)
