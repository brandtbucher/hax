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
from typing import Any, Dict, Hashable, Iterator, List, Tuple, TypeVar


T = TypeVar("T")

CALL_FUNCTION = opmap["CALL_FUNCTION"]
EXTENDED_ARG = opmap["EXTENDED_ARG"]
LOAD_CONST = opmap["LOAD_CONST"]
NOP = opmap["NOP"]
POP_TOP = opmap["POP_TOP"]


HASCOMPARE = frozenset(hascompare)
HASCONST = frozenset(hasconst)
HASFREE = frozenset(hasfree)
HASJABS = frozenset(hasjabs)
HASJREL = frozenset(hasjrel)
HASJUMP = HASJABS | HASJREL
HASLOCAL = frozenset(haslocal)
HASNAME = frozenset(hasname)


class HaxCompileError(SyntaxError):
    pass


def instructions_with_lines(code: CodeType) -> Iterator[Tuple[Instruction, int]]:
    line = code.co_firstlineno
    for instruction in get_instructions(code):
        line = instruction.starts_line or line
        yield instruction, line


def backfill(
    arg: int, line: int, min_size: int, new_op: int, filename: str, **_: object
) -> Iterator[int]:

    assert min_size in {2, 4, 6, 8}, "Invalid min_size!"

    if (1 << 32) - 1 < arg:
        raise HaxCompileError(
            f"Args greater than {(1 << 32) - 1:,} aren't supported (got {arg:,})!",
            (filename, line, None, None),
        )

    if arg < 0:
        raise HaxCompileError(
            f"Args less than 0 aren't supported (got {arg:,})!",
            (filename, line, None, None),
        )

    if 1 << 24 <= arg:
        yield EXTENDED_ARG
        yield arg >> 24 & 255
    elif 8 == min_size:
        yield NOP
        yield 0

    if 1 << 16 <= arg:
        yield EXTENDED_ARG
        yield arg >> 16 & 255
    elif 6 <= min_size:
        yield NOP
        yield 0

    if 1 << 8 <= arg:
        yield EXTENDED_ARG
        yield arg >> 8 & 255
    elif 4 <= min_size:
        yield NOP
        yield 0

    yield new_op
    yield arg & 255


def hax(target: T) -> T:

    if isinstance(target, CodeType):
        return _hax(target)  # type: ignore

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

        return new  # type: ignore

    raise TypeError(f"HAX doesn't support this! Got type {type(target)!r}.")


def _hax(bytecode: CodeType) -> CodeType:

    ops = instructions_with_lines(bytecode)

    used = False

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
                    code[info["start"] : info["start"] + info["min_size"]] = backfill(
                        **info
                    )
                    assert len(code) == offset, "Code changed size!"

            if op.opcode < HAVE_ARGUMENT:
                stacksize += max(0, stack_effect(op.opcode))
                lnotab += 1, line - last_line
                code += op.opcode, 0
                last_line = line
                continue

            if op.opcode != EXTENDED_ARG:
                break

            assert isinstance(op.arg, int), "Non-integer argument!"
            extended += EXTENDED_ARG, op.arg

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

            if op.opcode in HASLOCAL:
                info["arg"] = varnames.setdefault(op.argval, len(varnames))
            elif op.opcode in HASNAME:
                info["arg"] = names.setdefault(op.argval, len(names))
            elif op.opcode in HASCONST:
                try:
                    info["arg"] = consts.index(op.argval)
                except ValueError:
                    consts.append(op.argval)
                    info["arg"] = len(consts) - 1
            elif op.opcode in HASJABS:
                if op.argval <= op.offset:
                    info["arg"] = deferred[op.argval]
                else:
                    info["arg"] = 0
                    jumps.setdefault(op.argval, []).append(info)
            elif op.opcode in HASJREL:
                info["arg"] = len(code) + len(extended) + 2
                jumps.setdefault(op.argval, []).append(info)

            stacksize += max(
                0,
                stack_effect(
                    op.opcode, info["arg"] if HAVE_ARGUMENT <= op.opcode else None
                ),
            )
            new_code = [*backfill(**info)]
            lnotab += 1, line - last_line, len(new_code) - 1, 0
            code += new_code
            last_line = line
            continue

        used = True

        if op.opname not in {"LOAD_FAST", "LOAD_GLOBAL", "LOAD_NAME"}:
            raise HaxCompileError(
                "Ops must consist of a simple call.",
                (bytecode.co_filename, line, None, None),
            )

        args = 0
        arg = 0

        for following, _ in ops:

            if following.opcode == EXTENDED_ARG:
                continue

            if following.opcode == LOAD_CONST:
                arg = following.argval
                args += 1
                continue

            break

        else:
            raise HaxCompileError(
                "Ops must consist of a simple call.",
                (bytecode.co_filename, line, None, None),
            )

        if following.opcode != CALL_FUNCTION:
            raise HaxCompileError(
                "Ops must consist of a simple call.",
                (bytecode.co_filename, line, None, None),
            )

        following, _ = next(ops)

        if following.opcode != POP_TOP:
            raise HaxCompileError(
                "Ops must be standalone statements.",
                (bytecode.co_filename, line, None, None),
            )

        line = following.starts_line or line

        if op.argval == "LABEL":
            if arg in labels:
                raise HaxCompileError(
                    f"Label {arg!r} already exists!",
                    (bytecode.co_filename, line, None, None),
                )
            offset = len(code)
            labels[arg] = offset
            for info in deferred_labels.pop(arg, ()):
                info["arg"] = offset - info["arg"]
                code[info["start"] : info["start"] + info["min_size"]] = backfill(
                    **info
                )
                assert len(code) == offset, "Code changed size!"
            last_line = line
            continue

        new_op = opmap[op.argval]

        has_arg = HAVE_ARGUMENT <= new_op

        if args != has_arg:
            raise HaxCompileError(
                f"Number of arguments is wrong (expected {int(has_arg)}, got {args}).",
                (bytecode.co_filename, line, None, None),
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

        if new_op in HASLOCAL:
            if not isinstance(arg, str):
                raise HaxCompileError(
                    f"Expected a string (got {arg!r}).",
                    (bytecode.co_filename, line, None, None),
                )
            info["arg"] = varnames.setdefault(arg, len(varnames))
        elif new_op in HASNAME:
            if not isinstance(arg, str):
                raise HaxCompileError(
                    f"Expected a string (got {arg!r}).",
                    (bytecode.co_filename, line, None, None),
                )
            info["arg"] = names.setdefault(arg, len(names))
        elif new_op in HASCONST:
            try:
                info["arg"] = consts.index(arg)
            except ValueError:
                consts.append(arg)
                info["arg"] = len(consts) - 1
        elif new_op in HASCOMPARE:
            if not isinstance(arg, str):
                raise HaxCompileError(
                    f"Expected a string (got {arg!r}).",
                    (bytecode.co_filename, line, None, None),
                )
            try:
                info["arg"] = cmp_op.index(arg)
            except ValueError:
                raise HaxCompileError(
                    f"Bad comparision operator {arg!r}; expected one of {' / '.join(map(repr, cmp_op))}!",
                    (bytecode.co_filename, line, None, None),
                ) from None
        elif new_op in HASFREE:
            if not isinstance(arg, str):
                raise HaxCompileError(
                    f"Expected a string (got {arg!r}).",
                    (bytecode.co_filename, line, None, None),
                )
            try:
                info["arg"] = (bytecode.co_cellvars + bytecode.co_freevars).index(arg)
            except ValueError:
                raise HaxCompileError(
                    f'No free/cell variable {arg!r}; maybe use "nonlocal" in the inner scope to compile correctly?',
                    (bytecode.co_filename, line, None, None),
                ) from None
        elif new_op in HASJUMP:
            if arg in labels:
                if new_op in HASJREL:
                    raise HaxCompileError(
                        "Relative jumps must be forwards, not backwards!",
                        (bytecode.co_filename, line, None, None),
                    )
                info["arg"] = labels[arg]
            else:
                max_jump = (
                    len(bytecode.co_code)
                    - 1
                    - ((len(code) + 2) if new_op in HASJREL else 0)
                )
                if 1 << 24 <= max_jump:
                    padding = 6
                elif 1 << 16 <= max_jump:
                    padding = 4
                elif 1 << 8 <= max_jump:
                    padding = 2
                else:
                    padding = 0
                info["arg"] = (len(code) + padding + 2) if new_op in HASJREL else 0
                info["start"] = len(code)
                info["min_size"] = padding + 2
                deferred_labels.setdefault(arg, []).append(info)
        elif not isinstance(arg, int):
            raise HaxCompileError(
                f"Expected integer argument, got {arg!r}.",
                (bytecode.co_filename, line, None, None),
            )
        if new_op != EXTENDED_ARG:
            stacksize += max(0, stack_effect(new_op, info["arg"] if has_arg else None))
        new_code = [*backfill(**info)]
        lnotab += 1, line - last_line, len(new_code) - 1, 0
        code += new_code
        last_line = line

    if not used:
        return bytecode

    if deferred_labels:
        raise HaxCompileError(
            f"The following labels don't exist: {', '.join(map(repr, deferred_labels))}"
        )

    maybe_posonlyargcount = (
        (bytecode.co_posonlyargcount,)
        if hasattr(bytecode, "co_posonlyargcount")
        else ()
    )

    return CodeType(  # type: ignore
        bytecode.co_argcount,
        *maybe_posonlyargcount,  # type: ignore
        bytecode.co_kwonlyargcount,
        len(varnames),
        stacksize,
        bytecode.co_flags,
        bytes(code),
        tuple(consts),
        tuple(names),
        tuple(varnames),
        bytecode.co_filename,
        bytecode.co_name,
        bytecode.co_firstlineno,
        bytes(lnotab),
        bytecode.co_freevars,
        bytecode.co_cellvars,
    )
