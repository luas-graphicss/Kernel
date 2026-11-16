from pathlib import Path

import pytest

from kernel_tool.network import isolation


class SealedSwitch:
    def read_text(self, encoding: str) -> str:
        return "1\n"

    def write_text(self, text: str, encoding: str) -> int:
        raise PermissionError("read-only")


def test_forwarding_inherited_from_the_host_is_turned_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    switch = tmp_path / "ip_forward"
    switch.write_text("1\n", encoding="ascii")
    monkeypatch.setattr(isolation, "FORWARDING_SWITCH", switch)
    isolation.refuse_forwarding()
    assert switch.read_text(encoding="ascii") == "0"


def test_forwarding_that_is_already_off_is_left_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    switch = tmp_path / "ip_forward"
    switch.write_text("0\n", encoding="ascii")
    monkeypatch.setattr(isolation, "FORWARDING_SWITCH", switch)
    isolation.refuse_forwarding()
    assert switch.read_text(encoding="ascii") == "0\n"


def test_forwarding_that_cannot_be_turned_off_stops_the_station(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(isolation, "FORWARDING_SWITCH", SealedSwitch())
    with pytest.raises(PermissionError):
        isolation.refuse_forwarding()
