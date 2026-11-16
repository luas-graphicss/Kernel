import pytest

from kernel_core.memory.budget import PROFILE_FIELDS, ResourceProfile, check_profile
from kernel_protocol.errors.codes import INVALID_ARGUMENT, LIMIT_EXCEEDED, KernelError

MIB = 1 << 20
MACHINE_BYTES = 256 * MIB
REGION_BYTES = 8 * MIB
REFERENCE = (MACHINE_BYTES, 16, 8 * MIB, 4 * MIB, 128, MIB, 16 * MIB)


def profile_with(index: int, value: int) -> ResourceProfile:
    values = list(REFERENCE)
    values[index] = value
    return ResourceProfile(tuple(values))


def test_reference_profile_fits_the_reference_machine() -> None:
    profile = ResourceProfile(REFERENCE)

    check_profile(profile, MACHINE_BYTES, REGION_BYTES)

    assert profile.memory_bytes == MACHINE_BYTES
    assert profile.processes == 16
    assert profile.supervisor_heap_bytes == 8 * MIB
    assert profile.process_heap_bytes == 4 * MIB
    assert profile.capabilities_per_process == 128
    assert profile.ipc_pending_bytes_per_process == MIB
    assert profile.ipc_pending_bytes_global == 16 * MIB


@pytest.mark.parametrize("values", [REFERENCE[:-1], (*REFERENCE, 1), ()])
def test_profile_needs_every_limit(values: tuple[int, ...]) -> None:
    with pytest.raises(KernelError) as raised:
        ResourceProfile(values)

    assert raised.value.code == INVALID_ARGUMENT


@pytest.mark.parametrize("index", range(PROFILE_FIELDS))
@pytest.mark.parametrize("value", [0, -1])
def test_limits_must_be_positive(index: int, value: int) -> None:
    with pytest.raises(KernelError) as raised:
        profile_with(index, value)

    assert raised.value.code == INVALID_ARGUMENT


@pytest.mark.parametrize(
    ("profile", "machine_bytes", "region_bytes", "code"),
    [
        (ResourceProfile(REFERENCE), MACHINE_BYTES - 1, REGION_BYTES, LIMIT_EXCEEDED),
        (profile_with(2, MACHINE_BYTES), MACHINE_BYTES, REGION_BYTES, LIMIT_EXCEEDED),
        (profile_with(3, REGION_BYTES + 1), MACHINE_BYTES, REGION_BYTES, INVALID_ARGUMENT),
        (profile_with(5, 16 * MIB + 1), MACHINE_BYTES, REGION_BYTES, INVALID_ARGUMENT),
    ],
)
def test_inconsistent_profiles_are_rejected(
    profile: ResourceProfile, machine_bytes: int, region_bytes: int, code: int
) -> None:
    with pytest.raises(KernelError) as raised:
        check_profile(profile, machine_bytes, region_bytes)

    assert raised.value.code == code


def test_limits_at_their_boundaries_are_accepted() -> None:
    check_profile(profile_with(3, REGION_BYTES), MACHINE_BYTES, REGION_BYTES)
    check_profile(profile_with(5, 16 * MIB), MACHINE_BYTES, REGION_BYTES)
    check_profile(profile_with(2, MACHINE_BYTES - REGION_BYTES), MACHINE_BYTES, REGION_BYTES)
