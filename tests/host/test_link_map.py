from pathlib import Path

from kernel_tool.images.link_map import classify_origins, contributing_inputs

BUILD = Path("/work/build/qemu-riscv64")
COMPILER = Path("/tools/gcc")
LIBGCC = "/tools/gcc/lib/gcc/riscv-none-elf/15.2.0/rv64imac_zaamo_zalrsc/lp64/libgcc.a"

LINK_MAP = f"""
Archive member included to satisfy reference by file (symbol)

{LIBGCC}(_clzdi2.o)
                              {BUILD}/runtime/supervisor/libruntime.a(mpz.o) (__clzdi2)

Discarded input sections

 .text.unused   0x0000000000000000       0x10 /elsewhere/discarded.o

Linker script and memory map

LOAD {BUILD}/native/arch/riscv64/boot/entry.o
LOAD {LIBGCC}

.text           0x0000000080200000    0x13000
 .text.entry    0x0000000080200000       0x3a {BUILD}/native/arch/riscv64/boot/entry.o
 *fill*         0x000000008020003a        0x2
 .text.mp_obj_new_int_from_ull
                0x0000000080200040       0x24 {BUILD}/runtime/supervisor/libruntime.a(objint.o)
                0x0000000080200040                mp_obj_new_int_from_ull
 .text.__clzdi2
                0x0000000080200064       0x40 {LIBGCC}(_clzdi2.o)
 .text.memcpy   0x00000000802000a4       0x60 /opt/newlib/libc.a(memcpy.o)
 .text.start    0x0000000080200104       0x08 /somewhere/else/start.o

.data           0x0000000080214000        0x0 load address 0x0000000080214000
OUTPUT({BUILD}/kernel.elf elf64-littleriscv)
"""


def test_only_inputs_placed_in_the_memory_map_are_listed() -> None:
    assert contributing_inputs(LINK_MAP) == [
        "/opt/newlib/libc.a(memcpy.o)",
        "/somewhere/else/start.o",
        f"{LIBGCC}(_clzdi2.o)",
        f"{BUILD}/native/arch/riscv64/boot/entry.o",
        f"{BUILD}/runtime/supervisor/libruntime.a(objint.o)",
    ]


def test_map_without_memory_map_lists_nothing() -> None:
    assert contributing_inputs("Discarded input sections\n .text 0x0 0x10 /a/b.o\n") == []


def test_origins_outside_the_build_are_foreign_except_the_compiler_library() -> None:
    origins = classify_origins(contributing_inputs(LINK_MAP), BUILD, COMPILER)

    assert origins.compiler_library_members == ("_clzdi2.o",)
    assert origins.foreign == ("/opt/newlib/libc.a(memcpy.o)", "/somewhere/else/start.o")


def test_compiler_library_must_come_from_the_pinned_compiler() -> None:
    inputs = ["/usr/lib/gcc/libgcc.a(_clzdi2.o)", "/tools/gcc/lib/libc.a(memcpy.o)"]

    origins = classify_origins(inputs, BUILD, COMPILER)

    assert origins.compiler_library_members == ()
    assert origins.foreign == tuple(inputs)
