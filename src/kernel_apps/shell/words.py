from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError

MAX_WORDS = 16
QUOTE = '"'
SPACE = " "


def split_words(line: str) -> list[str]:
    words: list[str] = []
    current = ""
    is_quoted = False
    has_word = False
    for character in line:
        if character == QUOTE:
            is_quoted = not is_quoted
            has_word = True
        elif character == SPACE and not is_quoted:
            if has_word:
                words.append(current)
            current = ""
            has_word = False
        else:
            current += character
            has_word = True
    if is_quoted:
        raise KernelError(INVALID_ARGUMENT, "a quoted word is not closed")
    if has_word:
        words.append(current)
    if len(words) > MAX_WORDS:
        raise KernelError(INVALID_ARGUMENT, "the line holds too many words")
    return words


def parse_number(text: str, highest: int) -> int:
    if not text or len(text) > 9:
        raise KernelError(INVALID_ARGUMENT, "a number was expected")
    for character in text:
        if character not in "0123456789":
            raise KernelError(INVALID_ARGUMENT, "a number was expected")
    value = int(text)
    if value > highest:
        raise KernelError(INVALID_ARGUMENT, "the number is out of range")
    return value
