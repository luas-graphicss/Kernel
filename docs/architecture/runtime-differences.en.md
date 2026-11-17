# Differences between CPython and the guest runtime

[Português](runtime-differences.md)

The code in `src/` and the corpus in `tests/conformance/corpus/` run on two interpreters: CPython 3.13 on the host, which serves as the reference, and MicroPython 1.29.0 in the guest. This document lists the accepted differences between the two and the rule the shared code follows so as not to depend on them.

## What cannot differ

The result of the shared contracts. The `runtime-selftest` scenario runs in the guest the 10,000 transitions of the corpus, with the same seed, and `kernel-tool` compares each result line with the one CPython produces when running `python -m corpus`. Any difference fails the scenario. No difference in result is accepted.

## Accepted differences

| Topic | In the guest | Rule for the shared code |
| --- | --- | --- |
| Floating point | Off (`MICROPY_FLOAT_IMPL_NONE`) | Integers only, with `//` division |
| Integers | Arbitrary precision with MPZ, as in CPython | No restriction. The self-test covers arithmetic, shifts and conversion to text and to bytes beyond 64 bits |
| Standard library | Minimal. The self-test uses `builtins`, `sys` and `gc` | `src/` imports only project modules and the native modules: `_supervisor` in the policies and `_process` in the client library. No `typing`, `dataclasses`, `enum`, `struct` or `asyncio` |
| Type annotations | Discarded by `mpy-cross`, never evaluated | The annotations use built-in types and project classes. Without `typing`, there is no `Protocol`, `TypeVar` or generics of their own |
| External code | No loading of `.mpy`, and `sys.path` holds only `.frozen`: no module is imported from a file. `compile`, `open` and `input` do not exist. The `supervisor` profile has no compiler. The `user` profile has one, with `exec` and `eval`, and it is with it that the runner executes the file of an application | Every guest module enters frozen at build time. An application program is a single file and imports only frozen modules |
| f-strings | Supported in the `user` profile, by the compiler of the process. The frozen modules are compiled at build time by `mpy-cross` | No restriction |
| Formatting with `%` | `str` has no `%` operator: `'F%05d' % 7` raises `TypeError`. `'{:05d}'.format(7)` and `f'{7:05d}'` return `00007` | Format with f-strings or with `str.format` |
| Exceptions | The same built-in types in the cases covered by the self-test; messages and traceback have another format | Compare the type and the type's own fields, such as the code of `KernelError`. Never the text of the message |
| Deep recursion | `RuntimeError`, from the stack check. There is no `RecursionError` | Catch `RuntimeError` when the limit matters |
| Memory collection | Mark and sweep, without reference counting; finalizers off | Do not depend on `__del__` or on the moment memory is released |
| Output | `print` writes to the serial console. In the `user` profile it uses the `debug write` call, which accepts up to 256 bytes at a time | Short diagnostic lines |
| `sys` | `sys.platform` is `kernel`; `sys.argv` and `sys.exit` do not exist | The entry point is the `main()` of the module and the value returned sets the status |

## How a new difference gets in here

A module in `src/` is only accepted when the pinned `mpy-cross` compiles it and the scenario that exercises it passes on QEMU. Passing `mypy` and the tests on CPython is not enough. If a behavior diverges, the fix is to rewrite the code in the common subset. A difference only enters this table when it does not change the result of any shared contract.

The pure cases of the self-test also run on CPython, in `tests/conformance/test_guest_programs.py`, so that the same verification exists on both interpreters. The Python supervisor, the client library and the services run on CPython against doubles of the native modules, in `tests/conformance/doubles/`.
