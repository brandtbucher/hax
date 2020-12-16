from sys import version_info as _version_info
from typing import Hashable as _Hashable


_USAGE_MESSAGE = "HAX inline bytecode functions are not meant to be used directly; you must decorate any functions that use them with @hax."


class HaxUsageError(RuntimeError):
    pass


def LABEL(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def BEFORE_ASYNC_WITH() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= _version_info:  # pragma: no cover

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


if _version_info < (3, 8):  # pragma: no cover

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


if (3, 8) <= _version_info:  # pragma: no cover

    def CALL_FINALLY(arg: _Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_EX(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def CALL_FUNCTION_KW(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= _version_info:  # pragma: no cover

    def CALL_METHOD(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def COMPARE_OP(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= _version_info:  # pragma: no cover

    def CONTAINS_OP(invert: bool) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


if _version_info < (3, 8):  # pragma: no cover

    def CONTINUE_LOOP(arg: _Hashable) -> None:
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


if (3, 9) <= _version_info:  # pragma: no cover

    def DICT_MERGE(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)

    def DICT_UPDATE(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def DUP_TOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def DUP_TOP_TWO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= _version_info:  # pragma: no cover

    def END_ASYNC_FOR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def END_FINALLY() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def EXTENDED_ARG(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FORMAT_VALUE(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def FOR_ITER(arg: _Hashable) -> None:
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


if (3, 9) <= _version_info:  # pragma: no cover

    def IS_OP(invert: bool) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_ABSOLUTE(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_FORWARD(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_FALSE_OR_POP(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= _version_info:  # pragma: no cover

    def JUMP_IF_NOT_EXC_MATCH(arg: _Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def JUMP_IF_TRUE_OR_POP(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LIST_APPEND(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= _version_info:  # pragma: no cover

    def LIST_EXTEND(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)

    def LIST_TO_TUPLE() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)

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


def LOAD_CONST(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_DEREF(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_FAST(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def LOAD_GLOBAL(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 7) <= _version_info:  # pragma: no cover

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


if (3, 8) <= _version_info:  # pragma: no cover

    def POP_FINALLY(arg: bool) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_FALSE(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_JUMP_IF_TRUE(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def POP_TOP() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def PRINT_EXPR() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def RAISE_VARARGS(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= _version_info:  # pragma: no cover

    def RERAISE() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def RETURN_VALUE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 8) <= _version_info:  # pragma: no cover

    def ROT_FOUR() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def ROT_THREE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def ROT_TWO() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if (3, 9) <= _version_info:  # pragma: no cover

    def SET_UPDATE(arg: int) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ANNOTATIONS() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_ASYNC_WITH(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if _version_info < (3, 8):  # pragma: no cover

    def SETUP_EXCEPT(arg: _Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_FINALLY(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if _version_info < (3, 8):  # pragma: no cover

    def SETUP_LOOP(arg: _Hashable) -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def SETUP_WITH(arg: _Hashable) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def SET_ADD(arg: int) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def STORE_ATTR(arg: str) -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


if _version_info < (3, 7):  # pragma: no cover

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


if (3, 9) <= _version_info:  # pragma: no cover

    def WITH_EXCEPT_START() -> None:
        raise HaxUsageError(_USAGE_MESSAGE)


def YIELD_FROM() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)


def YIELD_VALUE() -> None:
    raise HaxUsageError(_USAGE_MESSAGE)
