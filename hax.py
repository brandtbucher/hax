__version__ = "0.1.1"


from sys import implementation, version_info


if version_info < (3, 6, 2):
    raise RuntimeError("HAX only supports Python 3.6.2+!")


if implementation.name != "cpython":
    raise RuntimeError("HAX only supports CPython!")


from dis import (
    HAVE_ARGUMENT,
    Instruction,
    cmp_op,
    get_instructions,
    hascompare,
    hasconst,
    hasfree,
    hasjabs,
    hasjrel,
    haslocal,
    hasname,
    opmap,
    stack_effect,
)
from types import CodeType, FunctionType
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    NoReturn,
)


_F = TypeVar("_F", bound=Callable[..., Any])


_USAGE_MESSAGE = "HAX inline bytecode functions are not meant to be used directly; you must decorate any functions that use them with @hax."


_CALL_FUNCTION = opmap["CALL_FUNCTION"]
_EXTENDED_ARG = opmap["EXTENDED_ARG"]
_LOAD_CONST = opmap["LOAD_CONST"]
_NOP = opmap["NOP"]
_POP_TOP = opmap["POP_TOP"]


_HASCOMPARE = frozenset(hascompare)
_HASCONST = frozenset(hasconst)
_HASFREE = frozenset(hasfree)
_HASJABS = frozenset(hasjabs)
_HASJREL = frozenset(hasjrel)
_HASJUMP = _HASJABS | _HASJREL
_HASLOCAL = frozenset(haslocal)
_HASNAME = frozenset(hasname)


class HaxCompileError(SyntaxError):
    pass


class HaxUsageError(RuntimeError):
    pass


def _error(message: str, filename: str, line: int) -> NoReturn:
    source: Optional[str] = None

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


def _instructions_with_lines(code: CodeType) -> Iterator[Tuple[Instruction, int]]:
    line = code.co_firstlineno
    for instruction in get_instructions(code):
        line = instruction.starts_line or line
        yield instruction, line


def _backfill(
    arg: int, line: int, min_size: int, new_op: int, filename: str, **_: object
) -> Iterator[int]:

    assert min_size in {2, 4, 6, 8}, "Invalid min_size!"

    if (1 << 32) - 1 < arg:
        _error(
            f"Args greater than {(1 << 32) - 1:,} aren't supported (got {arg:,})!",
            filename,
            line,
        )

    if arg < 0:

        _error(f"Args less than 0 aren't supported (got {arg:,})!", filename, line)
    if 1 << 24 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 24 & 255
    elif 8 == min_size:
        yield _NOP
        yield 0

    if 1 << 16 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 16 & 255
    elif 6 <= min_size:
        yield _NOP
        yield 0

    if 1 << 8 <= arg:
        yield _EXTENDED_ARG
        yield arg >> 8 & 255
    elif 4 <= min_size:
        yield _NOP
        yield 0

    yield new_op
    yield arg & 255


def hax(target: _F) -> _F:

    if isinstance(target, FunctionType):

        new = FunctionType(
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


def _hax(bytecode: CodeType) -> CodeType:

    ops = _instructions_with_lines(bytecode)

    code: List[int] = []
    last_line = bytecode.co_firstlineno
    lnotab: List[int] = []
    consts: List[object] = [bytecode.co_consts[0]]
    names: Dict[str, int] = {}
    stacksize = 0
    jumps: Dict[int, List[Dict[str, Any]]] = {}
    deferred: Dict[int, int] = {}
    varnames: Dict[str, int] = {
        name: index
        for index, name in enumerate(
            bytecode.co_varnames[
                : bytecode.co_argcount
                + bytecode.co_kwonlyargcount
                + getattr(bytecode, "co_posonlyargcount", 0)
            ]
        )
    }

    labels: Dict[Hashable, int] = {}
    deferred_labels: Dict[Hashable, List[Dict[str, Any]]] = {}

    while True:

        extended: List[int] = []

        for op, line in ops:

            if op.is_jump_target:
                deferred[op.offset] = len(code)
                offset = len(code)
                for info in jumps.get(op.offset, ()):
                    info["arg"] = offset - info["arg"]
                    code[info["start"] : info["start"] + info["min_size"]] = _backfill(
                        **info
                    )
                    assert len(code) == offset, "Code changed size!"

            if op.opcode < HAVE_ARGUMENT:
                stacksize += max(0, stack_effect(op.opcode))
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

        if op.argval not in opmap and op.argval != "LABEL":

            info = dict(
                arg=op.argval or 0,
                start=len(code),
                line=line,
                following=op,
                min_size=len(extended) + 2,
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
                stack_effect(
                    op.opcode, info["arg"] if HAVE_ARGUMENT <= op.opcode else None
                ),
            )
            new_code = [*_backfill(**info)]
            lnotab += 1, line - last_line, len(new_code) - 1, 0
            code += new_code
            last_line = line
            continue

        if op.opname not in {"LOAD_FAST", "LOAD_GLOBAL", "LOAD_NAME"}:

            _error("Ops must consist of a simple call.", bytecode.co_filename, line)
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

            _error("Ops must consist of a simple call.", bytecode.co_filename, line)
        if following.opcode != _CALL_FUNCTION:

            _error("Ops must consist of a simple call.", bytecode.co_filename, line)
        following, _ = next(ops)

        if following.opcode != _POP_TOP:

            _error("Ops must be standalone statements.", bytecode.co_filename, line)
        line = following.starts_line or line

        if op.argval == "LABEL":
            if arg in labels:
                _error(f"Label {arg!r} already exists!", bytecode.co_filename, line)
            offset = len(code)
            labels[arg] = offset
            for info in deferred_labels.pop(arg, ()):
                info["arg"] = offset - info["arg"]
                code[info["start"] : info["start"] + info["min_size"]] = _backfill(
                    **info
                )
                assert len(code) == offset, "Code changed size!"
            last_line = line
            continue

        new_op = opmap[op.argval]

        has_arg = HAVE_ARGUMENT <= new_op

        if args != has_arg:
            _error(
                f"Number of arguments is wrong (expected {int(has_arg)}, got {args}).",
                bytecode.co_filename,
                line,
            )

        info = dict(
            arg=arg,
            start=0,
            line=line,
            following=following,
            min_size=2,
            new_op=new_op,
            filename=bytecode.co_filename,
        )

        if new_op in _HASLOCAL:
            if not isinstance(arg, str):
                _error(f"Expected a string (got {arg!r}).", bytecode.co_filename, line)
            info["arg"] = varnames.setdefault(arg, len(varnames))
        elif new_op in _HASNAME:
            if not isinstance(arg, str):
                _error(f"Expected a string (got {arg!r}).", bytecode.co_filename, line)
            info["arg"] = names.setdefault(arg, len(names))
        elif new_op in _HASCONST:
            try:
                info["arg"] = consts.index(arg)
            except ValueError:
                consts.append(arg)
                info["arg"] = len(consts) - 1
        elif new_op in _HASCOMPARE:
            if not isinstance(arg, str):
                _error(f"Expected a string (got {arg!r}).", bytecode.co_filename, line)
            try:
                info["arg"] = cmp_op.index(arg)
            except ValueError:
                _error(
                    f"Bad comparision operator {arg!r}; expected one of {' / '.join(map(repr, cmp_op))}!",
                    bytecode.co_filename,
                    line,
                )
        elif new_op in _HASFREE:
            if not isinstance(arg, str):
                _error(f"Expected a string (got {arg!r}).", bytecode.co_filename, line)
            try:
                info["arg"] = (bytecode.co_cellvars + bytecode.co_freevars).index(arg)
            except ValueError:
                _error(
                    f'No free/cell variable {arg!r}; maybe use "nonlocal" in the inner scope to compile correctly?',
                    bytecode.co_filename,
                    line,
                )
        elif new_op in _HASJUMP:
            if arg in labels:
                if new_op in _HASJREL:
                    _error(
                        "Relative jumps must be forwards, not backwards!",
                        bytecode.co_filename,
                        line,
                    )
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
                info["min_size"] = padding + 2
                deferred_labels.setdefault(arg, []).append(info)
        elif not isinstance(arg, int):
            _error(
                f"Expected integer argument, got {arg!r}.", bytecode.co_filename, line
            )

        stacksize += max(0, stack_effect(new_op, info["arg"] if has_arg else None))
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

    return CodeType(  # type: ignore
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


def LABEL(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BEFORE_ASYNC_WITH() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= version_info:

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


if version_info < (3, 8):

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


if (3, 8) <= version_info:

    def CALL_FINALLY(arg: Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_EX(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_KW(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= version_info:

    def CALL_METHOD(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def COMPARE_OP(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if version_info < (3, 8):

    def CONTINUE_LOOP(arg: Hashable) -> None:
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


if (3, 8) <= version_info:

    def END_ASYNC_FOR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def END_FINALLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def EXTENDED_ARG(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FORMAT_VALUE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FOR_ITER(arg: Hashable) -> None:
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


def JUMP_ABSOLUTE(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_FORWARD(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_FALSE_OR_POP(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_TRUE_OR_POP(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LIST_APPEND(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= version_info:

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


def LOAD_CONST(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_DEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_FAST(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_GLOBAL(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= version_info:

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


if (3, 8) <= version_info:

    def POP_FINALLY(arg: bool) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_FALSE(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_TRUE(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_TOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def PRINT_EXPR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def RAISE_VARARGS(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def RETURN_VALUE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= version_info:

    def ROT_FOUR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def ROT_THREE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def ROT_TWO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ANNOTATIONS() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ASYNC_WITH(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if version_info < (3, 8):

    def SETUP_EXCEPT(arg: Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_FINALLY(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if version_info < (3, 8):

    def SETUP_LOOP(arg: Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_WITH(arg: Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SET_ADD(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_ATTR(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if version_info < (3, 7):

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
