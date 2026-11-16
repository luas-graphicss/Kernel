class BufferBudget:
    def __init__(self, limit_bytes: int) -> None:
        self._limit = limit_bytes
        self.used_bytes = 0

    def reserve(self, amount: int) -> bool:
        if self.used_bytes + amount > self._limit:
            return False
        self.used_bytes += amount
        return True

    def reserve_up_to(self, amount: int) -> int:
        room = self._limit - self.used_bytes
        if amount > room:
            amount = room
        self.used_bytes += amount
        return amount

    def release(self, amount: int) -> None:
        self.used_bytes -= amount
