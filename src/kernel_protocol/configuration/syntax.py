from kernel_protocol.configuration.errors import DUPLICATE, SYNTAX, TOO_LARGE, ConfigurationError

MAX_DOCUMENT_BYTES = 16384
MAX_LINES = 256
MAX_LINE_BYTES = 256
MAX_SECTIONS = 32
MAX_KEYS = 16
MAX_ITEMS = 16
MAX_TEXT_BYTES = 128
MAX_NUMBER_DIGITS = 18
LINE_BREAK = "\n"
CARRIAGE_RETURN = "\r"
COMMENT = "#"
SECTION_OPENS = "["
SECTION_CLOSES = "]"
ASSIGNS = "="
QUOTE = '"'
ESCAPE = "\\"
LIST_SEPARATOR = ","
TRUE = "true"
FALSE = "false"
LOWER_LETTERS = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
KEY_CHARACTERS = LOWER_LETTERS + DIGITS + "_"
SECTION_CHARACTERS = KEY_CHARACTERS + ".-"
FIRST_PRINTABLE = 0x20
LAST_PRINTABLE = 0x7E


def describe_line(number: int) -> str:
    return f"line-{number}"


def is_named_with(name: str, characters: str) -> bool:
    if not name or name[0] not in LOWER_LETTERS:
        return False
    return all(character in characters for character in name)


def is_printable(text: str) -> bool:
    for character in text:
        code = ord(character)
        if code < FIRST_PRINTABLE or code > LAST_PRINTABLE:
            return False
    return True


def parse_text(value: str, where: str) -> str:
    if len(value) < 2 or value[0] != QUOTE or value[-1] != QUOTE:
        raise ConfigurationError(SYNTAX, where)
    text = value[1:-1]
    if QUOTE in text or ESCAPE in text:
        raise ConfigurationError(SYNTAX, where)
    if len(text) > MAX_TEXT_BYTES:
        raise ConfigurationError(TOO_LARGE, where)
    return text


def parse_number(value: str, where: str) -> int:
    if len(value) > MAX_NUMBER_DIGITS:
        raise ConfigurationError(TOO_LARGE, where)
    for character in value:
        if character not in DIGITS:
            raise ConfigurationError(SYNTAX, where)
    if len(value) > 1 and value[0] == "0":
        raise ConfigurationError(SYNTAX, where)
    return int(value)


def parse_list(value: str, where: str) -> list[str]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    for item in inner.split(LIST_SEPARATOR):
        if len(items) == MAX_ITEMS:
            raise ConfigurationError(TOO_LARGE, where)
        items.append(parse_text(item.strip(), where))
    return items


def parse_value(value: str, where: str) -> object:
    if value == TRUE:
        return True
    if value == FALSE:
        return False
    if not value:
        raise ConfigurationError(SYNTAX, where)
    if value[0] == QUOTE:
        return parse_text(value, where)
    if value[0] == SECTION_OPENS:
        if value[-1] != SECTION_CLOSES:
            raise ConfigurationError(SYNTAX, where)
        return parse_list(value, where)
    return parse_number(value, where)


def open_section(line: str, document: dict[str, dict[str, object]], where: str) -> str:
    if line[-1] != SECTION_CLOSES:
        raise ConfigurationError(SYNTAX, where)
    name = line[1:-1]
    if not is_named_with(name, SECTION_CHARACTERS):
        raise ConfigurationError(SYNTAX, where)
    if name in document:
        raise ConfigurationError(DUPLICATE, name)
    if len(document) == MAX_SECTIONS:
        raise ConfigurationError(TOO_LARGE, where)
    document[name] = {}
    return name


def assign(line: str, section: dict[str, object], where: str) -> None:
    separator = line.find(ASSIGNS)
    if separator < 0:
        raise ConfigurationError(SYNTAX, where)
    key = line[:separator].strip()
    if not is_named_with(key, KEY_CHARACTERS):
        raise ConfigurationError(SYNTAX, where)
    if key in section:
        raise ConfigurationError(DUPLICATE, key)
    if len(section) == MAX_KEYS:
        raise ConfigurationError(TOO_LARGE, where)
    section[key] = parse_value(line[separator + 1 :].strip(), where)


def parse_document(text: str) -> dict[str, dict[str, object]]:
    if len(text) > MAX_DOCUMENT_BYTES:
        raise ConfigurationError(TOO_LARGE, "document")
    lines = text.split(LINE_BREAK)
    if len(lines) > MAX_LINES:
        raise ConfigurationError(TOO_LARGE, "lines")
    document: dict[str, dict[str, object]] = {}
    current = ""
    number = 0
    for raw in lines:
        number += 1
        where = describe_line(number)
        if raw.endswith(CARRIAGE_RETURN):
            raw = raw[:-1]
        if len(raw) > MAX_LINE_BYTES:
            raise ConfigurationError(TOO_LARGE, where)
        if not is_printable(raw):
            raise ConfigurationError(SYNTAX, where)
        line = raw.strip()
        if not line or line[0] == COMMENT:
            continue
        if line[0] == SECTION_OPENS:
            current = open_section(line, document, where)
        elif not current:
            raise ConfigurationError(SYNTAX, where)
        else:
            assign(line, document[current], where)
    return document
