from pathlib import Path

from kernel_tool.commands.test import SUITES
from kernel_tool.scenarios.model import DataCheck, DataSource
from kernel_tool.scenarios.release_suites import (
    NEXT_RELEASE,
    NEXT_VERSION,
    RELEASE_JOURNEY,
    RELEASE_SUITES,
)
from kernel_tool.storage.boot_image import release_file, runtime_tag
from kernel_tool.toolchain.lock import load_lock

REPOSITORY = Path(__file__).resolve().parents[2]


def test_the_image_of_the_next_release_differs_only_in_its_version() -> None:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")

    fixture = (REPOSITORY / NEXT_RELEASE).read_bytes()

    assert fixture == release_file(runtime_tag(lock), NEXT_VERSION).content


def test_the_journey_installs_updates_and_rolls_back_over_one_volume() -> None:
    installed, updated, returned, *_recovery = RELEASE_SUITES[RELEASE_JOURNEY]

    assert SUITES[RELEASE_JOURNEY] is RELEASE_SUITES[RELEASE_JOURNEY]
    assert installed.devices.data is not None and updated.devices.data is not None
    assert installed.devices.data.source is DataSource.FORMATTED
    assert updated.devices.data.source is DataSource.KEPT
    assert returned.devices.data is not None and returned.devices.data.source is DataSource.KEPT
    assert updated.boot_overlay and not returned.boot_overlay


def test_a_volume_the_release_cannot_write_is_left_as_it_was() -> None:
    *_journey, damaged, unknown = RELEASE_SUITES[RELEASE_JOURNEY]

    for scenario in (damaged, unknown):
        assert scenario.devices.data is not None
        assert scenario.devices.data.check is DataCheck.UNCHANGED
