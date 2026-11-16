from dataclasses import dataclass

from kernel_protocol.errors.codes import KernelError
from kernel_services.filesystem.recovery.digest import tree_digest
from kernel_services.filesystem.recovery.mount import PREVIOUS_ROOT_DAMAGED, mount
from kernel_services.filesystem.volume import Volume
from kernel_tool.faults.device_log import RecordingStore
from kernel_tool.storage.image_store import ImageStore

EVENTS_UNTIL_CONFIRMED = 1


@dataclass(frozen=True, slots=True)
class Commit:
    generation: int
    digest: int
    confirmed_after: int


@dataclass(frozen=True, slots=True)
class Recovery:
    generation: int | None
    failure: str | None


class History:
    def __init__(self, generation: int, digest: int) -> None:
        self.commits = [Commit(generation, digest, 0)]

    def record(self, generation: int, digest: int, confirmed_after: int) -> None:
        self.commits.append(Commit(generation, digest, confirmed_after))

    def digest_of(self, generation: int) -> int | None:
        for commit in self.commits:
            if commit.generation == generation:
                return commit.digest
        return None

    def confirmed(self, executed: int) -> int:
        return max(
            commit.generation for commit in self.commits if commit.confirmed_after <= executed
        )


class RecordedVolume:
    def __init__(self, image: bytes) -> None:
        self.base = image
        self.store = RecordingStore(image)
        self.volume = Volume(self.store)
        self.history = History(self.volume.generation(), tree_digest(self.volume))
        self.store.on_publish = self._published

    def _published(self, generation: int) -> None:
        confirmed_after = len(self.store.events) + EVENTS_UNTIL_CONFIRMED
        self.history.record(generation, tree_digest(self.volume), confirmed_after)


def recover(image: bytes, history: History, executed: int) -> Recovery:
    store = ImageStore(image)
    try:
        mounted = mount(store, True)
    except KernelError as error:
        return Recovery(None, f"the image does not mount: {error.detail}")
    generation = mounted.superblock.generation
    if mounted.read_only or mounted.reason == PREVIOUS_ROOT_DAMAGED:
        return Recovery(generation, f"a protected root was damaged: {mounted.reason}")
    confirmed = history.confirmed(executed)
    if generation < confirmed:
        return Recovery(
            generation, f"generation {confirmed} was confirmed but generation {generation} mounts"
        )
    expected = history.digest_of(generation)
    if expected is None:
        return Recovery(generation, f"generation {generation} was never committed")
    digest = tree_digest(Volume(store, mounted))
    if digest != expected:
        return Recovery(
            generation,
            f"generation {generation} holds digest {digest:08x} instead of {expected:08x}",
        )
    return Recovery(generation, None)
