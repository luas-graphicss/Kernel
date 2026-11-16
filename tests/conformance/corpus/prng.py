MASK = 0xFFFFFFFF
DEFAULT_STATE = 0x9E3779B9


class Generator:
    def __init__(self, seed: int) -> None:
        self.state = (seed & MASK) or DEFAULT_STATE

    def next(self) -> int:
        state = self.state
        state ^= (state << 13) & MASK
        state ^= state >> 17
        state ^= (state << 5) & MASK
        self.state = state
        return state

    def below(self, bound: int) -> int:
        return self.next() % bound

    def pick(self, items: list[int]) -> int:
        return items[self.below(len(items))]
