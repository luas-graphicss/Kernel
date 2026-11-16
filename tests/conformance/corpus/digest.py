MASK = 0xFFFFFFFF
LOW_SEED = 0x811C9DC5
HIGH_SEED = 0x9747B28C
LOW_PRIME = 16777619
HIGH_MULTIPLIER = 40503
HIGH_INCREMENT = 0x7F4A7C15


class Digest:
    def __init__(self) -> None:
        self.low = LOW_SEED
        self.high = HIGH_SEED

    def add(self, number: int) -> None:
        self.low = ((self.low ^ (number & MASK)) * LOW_PRIME) & MASK
        mixed = self.high ^ (number >> 32) ^ self.low
        self.high = (mixed * HIGH_MULTIPLIER + HIGH_INCREMENT) & MASK

    def add_bytes(self, data: bytes) -> None:
        for byte in data:
            self.add(byte)

    def hexdigest(self) -> str:
        return f"{self.high:08x}{self.low:08x}"
