from kernel_tool.images.device_tree import (
    BEGIN_NODE,
    END,
    END_NODE,
    PROPERTY,
    PROPERTY_TOKEN,
    TOKEN,
    DeviceTree,
    serialize,
)

VERSION = 17
LAST_COMPATIBLE_VERSION = 16
ALIGNMENT = 4
CELL_BYTES = 4
NO_RESERVATIONS = bytes(16)
MEMORY_BASE = 0x8000_0000
MEMORY_BYTES = 0x1000_0000
SERIAL_BASE = 0x1000_0000
SERIAL_BYTES = 0x100
SERIAL_INTERRUPT = 10
TRANSPORT_BASE = 0x1000_1000
TRANSPORT_BYTES = 0x1000
TRANSPORT_INTERRUPT = 1
CONTROLLER_BASE = 0x0C00_0000
CONTROLLER_BYTES = 0x60_0000
CONTROLLER_SOURCES = 95
TIMEBASE_FREQUENCY = 10_000_000


class TreeBuilder:
    def __init__(self) -> None:
        self._structure = bytearray()
        self._strings = bytearray()
        self._offsets: dict[str, int] = {}

    def begin(self, name: str) -> None:
        self._structure += TOKEN.pack(BEGIN_NODE) + _padded(name.encode("ascii") + b"\x00")

    def end(self) -> None:
        self._structure += TOKEN.pack(END_NODE)

    def value(self, name: str, value: bytes) -> None:
        offset = self._offsets.get(name)
        if offset is None:
            offset = len(self._strings)
            self._offsets[name] = offset
            self._strings += name.encode("ascii") + b"\x00"
        self._structure += TOKEN.pack(PROPERTY_TOKEN) + PROPERTY.pack(len(value), offset)
        self._structure += _padded(value)

    def cells(self, name: str, *cells: int) -> None:
        self.value(name, b"".join(cell.to_bytes(CELL_BYTES, "big") for cell in cells))

    def text(self, name: str, text: str) -> None:
        self.value(name, text.encode("ascii") + b"\x00")

    def build(self) -> bytes:
        structure = bytes(self._structure) + TOKEN.pack(END)
        tree = DeviceTree(
            version=VERSION,
            last_compatible_version=LAST_COMPATIBLE_VERSION,
            boot_cpu=0,
            reservations=NO_RESERVATIONS,
            structure=structure,
            strings=bytes(self._strings),
        )
        return serialize(tree)


def reference_tree() -> bytes:
    builder = TreeBuilder()
    builder.begin("")
    builder.cells("#address-cells", 2)
    builder.cells("#size-cells", 2)
    builder.begin("chosen")
    builder.text("bootargs", "init=kernel_services.init.main")
    builder.text("stdout-path", f"/soc/serial@{SERIAL_BASE:x}")
    builder.end()
    builder.begin(f"memory@{MEMORY_BASE:x}")
    builder.text("device_type", "memory")
    builder.cells("reg", 0, MEMORY_BASE, 0, MEMORY_BYTES)
    builder.end()
    builder.begin("cpus")
    builder.cells("timebase-frequency", TIMEBASE_FREQUENCY)
    builder.end()
    builder.begin("soc")
    builder.cells("#address-cells", 2)
    builder.cells("#size-cells", 2)
    builder.value("ranges", b"")
    builder.begin(f"serial@{SERIAL_BASE:x}")
    builder.text("compatible", "ns16550a")
    builder.cells("reg", 0, SERIAL_BASE, 0, SERIAL_BYTES)
    builder.cells("interrupts", SERIAL_INTERRUPT)
    builder.end()
    builder.begin(f"plic@{CONTROLLER_BASE:x}")
    builder.text("compatible", "riscv,plic0")
    builder.cells("reg", 0, CONTROLLER_BASE, 0, CONTROLLER_BYTES)
    builder.cells("riscv,ndev", CONTROLLER_SOURCES)
    builder.end()
    builder.begin(f"virtio_mmio@{TRANSPORT_BASE:x}")
    builder.text("compatible", "virtio,mmio")
    builder.cells("reg", 0, TRANSPORT_BASE, 0, TRANSPORT_BYTES)
    builder.cells("interrupts", TRANSPORT_INTERRUPT)
    builder.end()
    builder.end()
    builder.end()
    return builder.build()


def _padded(content: bytes) -> bytes:
    return content + bytes(-len(content) % ALIGNMENT)
