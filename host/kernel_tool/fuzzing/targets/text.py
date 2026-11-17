GUEST_TEXT_ENCODING = "latin-1"


def guest_text(data: bytes) -> str:
    return data.decode(GUEST_TEXT_ENCODING)
