<div align=center>

HAX
===

[![latest version](https://img.shields.io/github/release-pre/brandtbucher/hax.svg?style=for-the-badge&label=latest)![latest release date](https://img.shields.io/github/release-date-pre/brandtbucher/hax.svg?style=for-the-badge&label=released)](https://github.com/brandtbucher/hax/releases)[![build status](https://img.shields.io/github/workflow/status/brandtbucher/hax/CI/master.svg?style=for-the-badge)](https://github.com/brandtbucher/hax/actions)[![issues](https://img.shields.io/github/issues-raw/brandtbucher/hax.svg?label=issues&style=for-the-badge)](https://github.com/brandtbucher/hax/issues)

<br>

</div>

<div align=justify>

HAX lets you write compiled bytecode inline with pure Python. It was originally
built for exploring new improvements to CPython's compiler and peephole
optimizer.

Installation
------------

HAX supports CPython 3.6+ on all platforms.

To install, just run:

```sh
$ pip install hax
```

Example
-------

Consider the following function; it accepts a sequence of items, and returns a
list with each item repeated twice:

```py
def doubled(items):
    out = []
    for item in items:
        out += item, item
    return out
```

For example, `doubled((0, 1, 2))` returns `[0, 0, 1, 1, 2, 2]`.

We can make this function faster by keeping `out` on the stack (instead of in a
local variable) and using the `LIST_APPEND` op to build it. HAX makes it
simple to inline these instructions:

```py
from hax import *

@hax
def doubled(items):

    BUILD_LIST(0)

    for item in items:

        LOAD_FAST("item")
        DUP_TOP()
        LIST_APPEND(3)
        LIST_APPEND(2)

    RETURN_VALUE()
```

With the help of labeled jump targets, the function can be further sped up by
rewriting the for-loop in bytecode, removing _all_ temporary variables, and
operating **entirely on the stack**:

```py
from hax import *

@hax
def doubled(items):

    BUILD_LIST(0)

    LOAD_FAST("items")
    GET_ITER()
    LABEL("loop")
    FOR_ITER("return")

    DUP_TOP()
    LIST_APPEND(3)
    LIST_APPEND(2)
    JUMP_ABSOLUTE("loop")

    LABEL("return")
    RETURN_VALUE()
```

It's important to realize that the functions HAX provides (`BUILD_LIST`,
`LOAD_FAST`, ...) aren't just "emulating" their respective bytecode
instructions; the `@hax` decorator detects them, and completely recompiles
`double`'s code to use the _actual_ ops that we've specified here!

These performance improvements are impossible to get from CPython's compiler and
optimizer alone.

</div>
