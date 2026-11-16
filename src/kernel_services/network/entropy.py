from kernel_client import entropy

REFILL_BYTES = 64


class EntropyPool:
    def __init__(self, endpoint: int) -> None:
        self._endpoint = endpoint
        self._pool = b""

    def take(self, count: int) -> bytes:
        while len(self._pool) < count:
            self._pool += entropy.read(self._endpoint, REFILL_BYTES)
        taken = self._pool[:count]
        self._pool = self._pool[count:]
        return taken
