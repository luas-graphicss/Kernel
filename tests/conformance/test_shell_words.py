import pytest

from kernel_apps.shell.words import MAX_WORDS, parse_number, split_words
from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.services.launch import (
    HAS_FILES,
    HAS_NETWORK,
    MAX_COMMAND_BYTES,
    decode_launch,
    encode_launch,
)


def refused(operation, *arguments) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


@pytest.mark.parametrize(
    ("line", "words"),
    [
        ("", []),
        ("   ", []),
        ("ls", ["ls"]),
        ("  ls   boot  ", ["ls", "boot"]),
        ('write data/note "two  words" end', ["write", "data/note", "two  words", "end"]),
        ('write data/empty ""', ["write", "data/empty", ""]),
        ('run a"b c"d', ["run", "ab cd"]),
    ],
)
def test_a_line_is_split_at_spaces_outside_quotes(line: str, words: list[str]) -> None:
    assert split_words(line) == words


def test_an_open_quote_or_too_many_words_refuse_the_line() -> None:
    assert refused(split_words, 'write data/note "never closed') == INVALID_ARGUMENT
    assert refused(split_words, " ".join(["word"] * (MAX_WORDS + 1))) == INVALID_ARGUMENT
    assert len(split_words(" ".join(["word"] * MAX_WORDS))) == MAX_WORDS


@pytest.mark.parametrize(("text", "value"), [("0", 0), ("7", 7), ("3600", 3600), ("007", 7)])
def test_a_number_is_decimal_digits_within_its_range(text: str, value: int) -> None:
    assert parse_number(text, 3600) == value


@pytest.mark.parametrize("text", ["", "-1", "+1", "1.5", "0x10", "ten", "3601", "1234567890"])
def test_text_that_is_no_number_in_range_is_refused(text: str) -> None:
    assert refused(parse_number, text, 3600) == INVALID_ARGUMENT


def test_a_launch_carries_its_resources_and_its_words() -> None:
    argument = encode_launch(HAS_FILES | HAS_NETWORK, b"boot/apps/fetch.py 10.0.2.2  17 data/out")

    assert decode_launch(argument) == (
        HAS_FILES | HAS_NETWORK,
        ["boot/apps/fetch.py", "10.0.2.2", "17", "data/out"],
    )
    assert decode_launch(encode_launch(0, b"boot/apps/sysinfo.py")) == (0, ["boot/apps/sysinfo.py"])


def test_a_launch_without_a_program_or_with_unknown_resources_is_refused() -> None:
    assert refused(encode_launch, HAS_FILES, b"") == INVALID_ARGUMENT
    assert refused(encode_launch, 0x80, b"program") == INVALID_ARGUMENT
    assert refused(encode_launch, 0, b"x" * (MAX_COMMAND_BYTES + 1)) == INVALID_ARGUMENT
    assert refused(decode_launch, b"") == INVALID_ARGUMENT
    assert refused(decode_launch, bytes((HAS_FILES,))) == INVALID_ARGUMENT
    assert refused(decode_launch, bytes((HAS_FILES,)) + b"   ") == INVALID_ARGUMENT
    assert refused(decode_launch, bytes((0x40,)) + b"program") == INVALID_ARGUMENT
