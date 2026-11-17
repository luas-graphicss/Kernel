import socket
import sys
import tempfile
from pathlib import Path

import pytest

from kernel_tool.network import link as link_module
from kernel_tool.network.link import StationLink
from kernel_tool.network.plan import NetworkPlan
from kernel_tool.network.sockets import (
    GUEST_SOCKET,
    SOCKET_ADDRESS_BYTES,
    STATION_SOCKET,
    socket_directory,
)
from kernel_tool.outcome import InfrastructureError

FRAME = b"frame"
DEEP_PARTS = ("nested-directory",) * 8
REFUSING_STATION = [sys.executable, "-c", 'print(\'{"event": "refused"}\')']


def emulator_paths(link: StationLink) -> dict[str, str]:
    netdev = link.emulator_arguments()[1]
    return dict(field.split("=", 1) for field in netdev.split(",") if "=" in field)


def test_both_link_sockets_bind_and_carry_a_frame() -> None:
    with socket_directory() as directory:
        station_path = str(Path(directory) / STATION_SOCKET)
        guest_path = str(Path(directory) / GUEST_SOCKET)
        with (
            socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as station,
            socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as guest,
        ):
            station.bind(station_path)
            guest.bind(guest_path)
            guest.sendto(FRAME, station_path)

            assert station.recv(len(FRAME)) == FRAME


def test_a_link_below_a_deep_directory_gives_the_emulator_socket_paths_that_fit(
    tmp_path: Path,
) -> None:
    deep = tmp_path.joinpath(*DEEP_PARTS)
    link = StationLink(deep, NetworkPlan())
    try:
        paths = emulator_paths(link)
    finally:
        link.stop()

    assert len(bytes(deep / STATION_SOCKET)) > SOCKET_ADDRESS_BYTES
    assert Path(paths["local.path"]).name == GUEST_SOCKET
    assert Path(paths["remote.path"]).name == STATION_SOCKET
    assert len(paths["local.path"].encode()) <= SOCKET_ADDRESS_BYTES
    assert len(paths["remote.path"].encode()) <= SOCKET_ADDRESS_BYTES


def test_a_stopped_link_leaves_no_socket_directory(tmp_path: Path) -> None:
    link = StationLink(tmp_path, NetworkPlan())
    directory = Path(emulator_paths(link)["local.path"]).parent

    assert directory.is_dir()
    link.stop()
    assert not directory.exists()


def test_a_link_whose_station_does_not_start_leaves_no_socket_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(link_module, "isolated_command", lambda arguments: REFUSING_STATION)
    link = StationLink(tmp_path, NetworkPlan())
    directory = Path(emulator_paths(link)["local.path"]).parent

    with pytest.raises(InfrastructureError, match="did not start"), link:
        pass

    assert not directory.exists()


def test_a_temporary_directory_too_deep_for_a_socket_address_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deep = tmp_path.joinpath(*DEEP_PARTS)
    deep.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(deep))

    with pytest.raises(InfrastructureError, match="TMPDIR"):
        socket_directory()

    assert list(deep.iterdir()) == []
