class CheckError(Exception):
    pass


class Checks:
    def __init__(self) -> None:
        self.passed = 0

    def require(self, condition: bool, description: str) -> None:
        if not condition:
            raise CheckError(description)
        self.passed += 1
