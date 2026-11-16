import json
from dataclasses import dataclass
from pathlib import Path

FLUSH_FAILURE_ERRNO = 5

type BlockNode = dict[str, object]


@dataclass(frozen=True, slots=True)
class FileDrive:
    identity: str
    image: Path
    read_only: bool = False

    def nodes(self, name: str) -> tuple[BlockNode, ...]:
        return (
            {
                "driver": "raw",
                "node-name": name,
                "read-only": self.read_only,
                "file": file_node(self.image),
            },
        )


@dataclass(frozen=True, slots=True)
class FlushFailingDrive:
    identity: str
    image: Path

    def nodes(self, name: str) -> tuple[BlockNode, ...]:
        failing: BlockNode = {
            "driver": "blkdebug",
            "image": file_node(self.image),
            "inject-error": [
                {"event": "flush_to_os", "iotype": "flush", "errno": FLUSH_FAILURE_ERRNO}
            ],
        }
        return ({"driver": "raw", "node-name": name, "file": failing},)


@dataclass(frozen=True, slots=True)
class TracedDrive:
    identity: str
    image: Path
    write_log: Path

    def nodes(self, name: str) -> tuple[BlockNode, ...]:
        log = f"{name}-log"
        return (
            {"driver": "file", "node-name": log, "filename": str(self.write_log)},
            {
                "driver": "blklogwrites",
                "node-name": name,
                "file": file_node(self.image),
                "log": log,
            },
        )


@dataclass(frozen=True, slots=True)
class StalledDrive:
    identity: str
    size_bytes: int
    latency_nanoseconds: int

    def nodes(self, name: str) -> tuple[BlockNode, ...]:
        return (
            {
                "driver": "null-co",
                "node-name": name,
                "size": self.size_bytes,
                "latency-ns": self.latency_nanoseconds,
                "read-zeroes": True,
            },
        )


type Drive = FileDrive | FlushFailingDrive | TracedDrive | StalledDrive


def file_node(image: Path) -> BlockNode:
    return {"driver": "file", "filename": str(image)}


def drive_arguments(drive: Drive) -> list[str]:
    name = f"disk-{drive.identity}"
    arguments = []
    for node in drive.nodes(name):
        arguments.extend(["-blockdev", json.dumps(node, sort_keys=True)])
    arguments.extend(["-device", f"virtio-blk-device,drive={name},serial={drive.identity}"])
    return arguments
