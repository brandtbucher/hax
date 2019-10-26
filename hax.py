import dis
import os
import sys
import types
import typing


__version__ = "0.1.1"


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


_HASCOMPARE = frozenset(dis.hascompare)
_HASCONST = frozenset(dis.hasconst)
_HASFREE = frozenset(dis.hasfree)
_HASJABS = frozenset(dis.hasjabs)
_HASJREL = frozenset(dis.hasjrel)
_HASJUMP = _HASJABS | _HASJREL
_HASLOCAL = frozenset(dis.haslocal)
_HASNAME = frozenset(dis.hasname)


class HaxCompileError(SyntaxError):
    pass


class HaxUsageError(RuntimeError):
    pass


def _raise_hax_error(message: str, filename: str, line: int) -> typing.NoReturn:

    source: typing.Optional[str] = None

    try:

        with open(filename) as file:
            for line_number, text in enumerate(file, 1):
                if line_number < line:
                    continue
                source = text
                break

    except OSError:
        pass

    raise HaxCompileError(message, (filename, line, None, source))


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

    assert 1 <= size < 5, "Invalid size!"

    if (1 << 32) - 1 < arg:
        message = f"Args greater than {(1 << 32) - 1:,} aren't supported (got {arg:,})!"
        _raise_hax_error(message, filename, line)

    if arg < 0:
        message = f"Args less than 0 aren't supported (got {arg:,})!"
        _raise_hax_error(message, filename, line)

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


def hax(target: _F) -> _F:

    if isinstance(target, types.FunctionType):

        new = types.FunctionType(
            _hax(target.__code__),
            target.__globals__,
            target.__name__,
            target.__defaults__,
            target.__closure__,
        )

        if target.__annotations__:
            new.__annotations__ = target.__annotations__.copy()

        if target.__kwdefaults__ is not None:
            new.__kwdefaults__ = target.__kwdefaults__.copy()

        if target.__dict__:
            new.__dict__ = target.__dict__.copy()

    else:

        raise TypeError(f"HAX doesn't support this! Got type {type(target)!r}.")

    return new  # type: ignore


def _hax(bytecode: types.CodeType) -> types.CodeType:

    ops = _instructions_with_lines(bytecode)

    code: typing.List[int] = []
    last_line = bytecode.co_firstlineno
    lnotab: typing.List[int] = []
    consts: typing.List[object] = [bytecode.co_consts[0]]
    names: typing.Dict[str, int] = {}
    stacksize = 0
    jumps: typing.Dict[int, typing.List[typing.Dict[str, typing.Any]]] = {}
    deferred: typing.Dict[int, int] = {}
    varnames: typing.Dict[str, int] = {
        name: index
        for index, name in enumerate(
            bytecode.co_varnames[
                : bytecode.co_argcount
                + bytecode.co_kwonlyargcount
                + getattr(bytecode, "co_posonlyargcount", 0)
            ]
        )
    }

    labels: typing.Dict[typing.Hashable, int] = {}
    deferred_labels: typing.Dict[
        typing.Hashable, typing.List[typing.Dict[str, typing.Any]]
    ] = {}

    while True:

        extended: typing.List[int] = []

        for op, line in ops:

            if op.is_jump_target:
                deferred[op.offset] = len(code)
                offset = len(code)
                for info in jumps.get(op.offset, ()):
                    info["arg"] = offset - info["arg"]
                    code[info["start"] : info["offset"] + 2] = _backfill(**info)
                    assert len(code) == offset, "Code changed size!"

            if op.opcode < dis.HAVE_ARGUMENT:
                stacksize += max(0, dis.stack_effect(op.opcode))
                lnotab += 1, line - last_line
                code += op.opcode, 0
                last_line = line
                continue

            if op.opcode != _EXTENDED_ARG:
                break

            assert isinstance(op.arg, int), "Non-integer argument!"
            extended += _EXTENDED_ARG, op.arg

        else:
            break

        if op.argval not in dis.opmap and op.argval != "LABEL":

            info = dict(
                arg=op.argval or 0,
                start=len(code),
                line=line,
                following=op,
                offset=len(code) + len(extended),
                new_op=op.opcode,
                filename=bytecode.co_filename,
            )

            if op.opcode in _HASLOCAL:
                info["arg"] = varnames.setdefault(op.argval, len(varnames))
            elif op.opcode in _HASNAME:
                info["arg"] = names.setdefault(op.argval, len(names))
            elif op.opcode in _HASCONST:
                try:
                    info["arg"] = consts.index(op.argval)
                except ValueError:
                    consts.append(op.argval)
                    info["arg"] = len(consts) - 1
            elif op.opcode in _HASJABS:
                if op.argval <= op.offset:
                    info["arg"] = deferred[op.argval]
                else:
                    info["arg"] = 0
                    jumps.setdefault(op.argval, []).append(info)
            elif op.opcode in _HASJREL:
                info["arg"] = len(code) + len(extended) + 2
                jumps.setdefault(op.argval, []).append(info)

            stacksize += max(
                0,
                dis.stack_effect(
                    op.opcode, info["arg"] if dis.HAVE_ARGUMENT <= op.opcode else None
                ),
            )
            new_code = [*_backfill(**info)]
            lnotab += 1, line - last_line, len(new_code) - 1, 0
            code += new_code
            last_line = line
            continue

        if op.opname not in {"LOAD_FAST", "LOAD_GLOBAL", "LOAD_NAME"}:
            message = "Ops must consist of a simple call."
            _raise_hax_error(message, bytecode.co_filename, line)

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
            _raise_hax_error(message, bytecode.co_filename, line)

        if following.opcode != _CALL_FUNCTION:
            message = "Ops must consist of a simple call."
            _raise_hax_error(message, bytecode.co_filename, line)

        following, _ = next(ops)

        if following.opcode != _POP_TOP:
            message = "Ops must be standalone statements."
            _raise_hax_error(message, bytecode.co_filename, line)

        line = following.starts_line or line

        if op.argval == "LABEL":
            if arg in labels:
                message = f"Label {arg!r} already exists!"
                _raise_hax_error(message, bytecode.co_filename, line)
            offset = len(code)
            labels[arg] = offset
            for info in deferred_labels.pop(arg, ()):
                info["arg"] = offset - info["arg"]
                code[info["start"] : info["offset"] + 2] = _backfill(**info)
                assert len(code) == offset, "Code changed size!"
            last_line = line
            continue

        new_op = dis.opmap[op.argval]

        has_arg = dis.HAVE_ARGUMENT <= new_op

        if args != has_arg:
            message = (
                f"Number of arguments is wrong (expected {int(has_arg)}, got {args})."
            )
            _raise_hax_error(message, bytecode.co_filename, line)

        info = dict(
            arg=arg,
            start=0,
            line=line,
            following=following,
            offset=0,
            new_op=new_op,
            filename=bytecode.co_filename,
        )
        if new_op in _HASLOCAL:
            if not isinstance(arg, str):
                message = f"Expected a string (got {arg!r})."
                _raise_hax_error(message, bytecode.co_filename, line)
            info["arg"] = varnames.setdefault(arg, len(varnames))
        elif new_op in _HASNAME:
            if not isinstance(arg, str):
                message = f"Expected a string (got {arg!r})."
                _raise_hax_error(message, bytecode.co_filename, line)
            info["arg"] = names.setdefault(arg, len(names))
        elif new_op in _HASCONST:
            try:
                info["arg"] = consts.index(arg)
            except ValueError:
                consts.append(arg)
                info["arg"] = len(consts) - 1
        elif new_op in _HASCOMPARE:
            if not isinstance(arg, str):
                message = f"Expected a string (got {arg!r})."
                _raise_hax_error(message, bytecode.co_filename, line)
            try:
                info["arg"] = dis.cmp_op.index(arg)
            except ValueError:
                message = f"Bad comparision operator {arg!r}; expected one of {' / '.join(map(repr, dis.cmp_op))}!"
                _raise_hax_error(message, bytecode.co_filename, line)
        elif new_op in _HASFREE:
            if not isinstance(arg, str):
                message = f"Expected a string (got {arg!r})."
                _raise_hax_error(message, bytecode.co_filename, line)
            try:
                info["arg"] = (bytecode.co_cellvars + bytecode.co_freevars).index(arg)
            except ValueError:
                message = f'No free/cell variable {arg!r}; maybe use "nonlocal" in the inner scope to compile correctly?'
                _raise_hax_error(message, bytecode.co_filename, line)
        elif new_op in _HASJUMP:
            if arg in labels:
                if new_op in _HASJREL:
                    message = "Relative jumps must be forwards, not backwards!"
                    _raise_hax_error(message, bytecode.co_filename, line)
                info["arg"] = labels[arg]
            else:
                max_jump = (
                    len(bytecode.co_code)
                    - 1
                    - ((len(code) + 2) if new_op in _HASJREL else 0)
                )
                if 1 << 24 <= max_jump:
                    padding = 6
                elif 1 << 16 <= max_jump:
                    padding = 4
                elif 1 << 8 <= max_jump:
                    padding = 2
                else:
                    padding = 0
                info["arg"] = (len(code) + padding + 2) if new_op in _HASJREL else 0
                info["start"] = len(code)
                info["offset"] = len(code) + padding
                deferred_labels.setdefault(arg, []).append(info)
        elif not isinstance(arg, int):
            message = f"Expected integer argument, got {arg!r}."
            _raise_hax_error(message, bytecode.co_filename, line)

        stacksize += max(0, dis.stack_effect(new_op, info["arg"] if has_arg else None))
        new_code = [*_backfill(**info)]
        lnotab += 1, line - last_line, len(new_code) - 1, 0
        code += new_code
        last_line = line

    if deferred_labels:
        raise HaxUsageError(
            f"The following labels don't exist: {', '.join(map(repr, deferred_labels))}"
        )

    maybe_posonlyargcount = (
        (bytecode.co_posonlyargcount,)  # type: ignore
        if hasattr(bytecode, "co_posonlyargcount")
        else ()
    )

    return types.CodeType(  # type: ignore
        bytecode.co_argcount,
        *maybe_posonlyargcount,
        bytecode.co_kwonlyargcount,
        len(varnames),
        stacksize,  # TODO: Fix this up?
        bytecode.co_flags,
        bytes(code),
        tuple(consts),
        tuple(names),
        tuple(varnames),
        bytecode.co_filename,
        bytecode.co_name,
        bytecode.co_firstlineno,
        bytes(lnotab),  # TODO: Fix this up!
        bytecode.co_freevars,
        bytecode.co_cellvars,
    )


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
