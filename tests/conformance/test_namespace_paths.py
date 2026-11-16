import pytest

from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    KernelError,
)
from kernel_protocol.services.files import MAX_PATH_BYTES, MAX_PATH_COMPONENTS
from kernel_services.filesystem.namespace.paths import split

RESOLVED = [
    (b"", []),
    (b"/", []),
    (b"a/b", [b"a", b"b"]),
    (b"/a//b/", [b"a", b"b"]),
    (b"./a/./b/.", [b"a", b"b"]),
    (b"a/b/..", [b"a"]),
    (b"a/../b", [b"b"]),
    (b"a/b/../..", []),
    (b"a\xc3\xa7\xc3\xa3o/\xe2\x82\xac", [b"a\xc3\xa7\xc3\xa3o", b"\xe2\x82\xac"]),
]
REFUSED = [
    (b"..", ACCESS_DENIED),
    (b"a/../..", ACCESS_DENIED),
    (b"/../a", ACCESS_DENIED),
    (b"a/b/../../../c", ACCESS_DENIED),
    (b"a/\xff", INVALID_ARGUMENT),
    (b"a/\xc0\xaf/b", INVALID_ARGUMENT),
    (b"a\x00b", INVALID_ARGUMENT),
    (b"n" * 256, INVALID_ARGUMENT),
    (b"/".join([b"c"] * (MAX_PATH_COMPONENTS + 1)), LIMIT_EXCEEDED),
    (b"p" * (MAX_PATH_BYTES + 1), LIMIT_EXCEEDED),
]


@pytest.mark.parametrize(("path", "components"), RESOLVED)
def test_path_resolves_to_names_below_the_root_of_its_namespace(
    path: bytes, components: list[bytes]
) -> None:
    assert split(path) == components


@pytest.mark.parametrize(("path", "code"), REFUSED)
def test_path_that_escapes_or_breaks_a_limit_is_refused(path: bytes, code: int) -> None:
    with pytest.raises(KernelError) as raised:
        split(path)

    assert raised.value.code == code


def test_limits_accept_the_largest_path_and_the_most_components() -> None:
    most = b"/".join([b"c"] * MAX_PATH_COMPONENTS)
    longest = b"/".join([b"n" * 255] * 4)

    assert len(split(most)) == MAX_PATH_COMPONENTS
    assert len(longest) <= MAX_PATH_BYTES
    assert len(split(longest)) == 4


def test_components_dropped_by_dot_dot_do_not_count_against_the_limit() -> None:
    climbing = b"/".join([b"a", b".."] * MAX_PATH_COMPONENTS + [b"kept"])

    assert split(climbing) == [b"kept"]
