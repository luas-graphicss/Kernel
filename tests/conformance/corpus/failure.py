class InvariantError(Exception):
    pass


def require(condition: bool, description: str) -> None:
    if not condition:
        raise InvariantError(description)
