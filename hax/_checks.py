from sys import implementation, version_info


if implementation.name != "cpython":
    raise RuntimeError("HAX only supports CPython!")


if version_info < (3, 6):
    raise RuntimeError("HAX only supports Python 3.6+!")
