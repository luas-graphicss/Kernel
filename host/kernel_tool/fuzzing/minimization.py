from collections.abc import Callable


def minimize(data: bytes, still_fails: Callable[[bytes], bool], attempts: int) -> bytes:
    smallest = data
    chunk = len(smallest) // 2
    while chunk > 0 and attempts > 0:
        start = 0
        while start < len(smallest) and attempts > 0:
            candidate = smallest[:start] + smallest[start + chunk :]
            attempts -= 1
            if still_fails(candidate):
                smallest = candidate
            else:
                start += chunk
        chunk //= 2
    return smallest
