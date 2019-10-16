<div align=center>

HAX
===

[![latest version](https://img.shields.io/github/release-pre/brandtbucher/hax.svg?style=for-the-badge&label=latest)![latest release date](https://img.shields.io/github/release-date-pre/brandtbucher/hax.svg?style=for-the-badge&label=released)](https://github.com/brandtbucher/hax/releases)[![build status](https://img.shields.io/travis/com/brandtbucher/hax/master.svg?style=for-the-badge)](https://travis-ci.com/brandtbucher/hax/branches)[![issues](https://img.shields.io/github/issues-raw/brandtbucher/hax.svg?label=issues&style=for-the-badge)](https://github.com/brandtbucher/hax/issues)

<br>

</div>

<div align=justify>

HAX lets you write compiled bytecode inline with standard Python syntax.

Installation
------------

HAX supports CPython 3.6–3.9.

To install, just run:

```sh
$ pip install hax
```

Example
-------

Consider the following function; it accepts a sequence of items, and returns a 
list with each item repeated twice:

```py
from typing import List, Sequence, TypeVar

T = TypeVar("T")

def double(items: Sequence[T]) -> List[T]:
    out = []
    for item in items:
        out += item, item
    return out            
```

For example, `(0, 1, 2)` becomes `[0, 0, 1, 1, 2, 2]`.

We can make this function faster by keeping `out` on the stack (instead of in a 
local variable) and using the `LIST_APPEND` op to build it. HAX makes it 
simple to inline these instructions:

```py
from hax import *

@hax 
def double(items: Sequence[T]) -> List[T]:
    
    BUILD_LIST(0)

    for item in items:

        LOAD_FAST("item")
        DUP_TOP()
        LIST_APPEND(3)
        LIST_APPEND(2)

    RETURN_VALUE()
```

If you're up to the challenge of computing jump targets, the function can be 
further sped up by rewriting the for-loop in bytecode, removing _all_ temporary 
variables, and operating **entirely on the stack**:

```py
@hax 
def double(items: Sequence[T]) -> List[T]:

    BUILD_LIST(0)

    LOAD_FAST("items")
    GET_ITER()
    FOR_ITER(34)  # When done, jump forward to RETURN_VALUE().

    DUP_TOP()
    LIST_APPEND(3)
    LIST_APPEND(2)
    JUMP_ABSOLUTE(28)  # Jump back to FOR_ITER(34).

    RETURN_VALUE()
```

It's important to realize that the functions HAX provides (`BUILD_LIST`,
`LOAD_FAST`, ...) aren't just "emulating" their respective bytecode
instructions; the `@hax` decorator detects them, and completely recompiles
`double`'s code to use the _actual_ ops that we've specified here!

These performance improvements are impossible to get from CPython's compiler and 
optimizer alone.

</div>
