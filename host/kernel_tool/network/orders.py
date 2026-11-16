from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Call:
    port: int
    seed: int
    length: int

    def to_command(self) -> dict[str, object]:
        return {"command": "call", "port": self.port, "seed": self.seed, "bytes": self.length}


@dataclass(frozen=True, slots=True)
class Inject:
    frames: tuple[bytes, ...]

    def to_command(self) -> dict[str, object]:
        return {"command": "inject", "frames": [frame.hex() for frame in self.frames]}


@dataclass(frozen=True, slots=True)
class Darken:
    milliseconds: int

    def to_command(self) -> dict[str, object]:
        return {"command": "darken", "milliseconds": self.milliseconds}


type Order = Call | Inject | Darken
