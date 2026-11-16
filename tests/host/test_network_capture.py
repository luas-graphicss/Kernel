from pathlib import Path

import pytest

from kernel_tool.network.capture import GLOBAL_HEADER, Capture, read_capture

SNAP_BYTES = 96


def test_a_capture_keeps_the_head_of_each_frame_and_its_true_length(tmp_path: Path) -> None:
    path = tmp_path / "traffic.pcap"
    capture = Capture(path, SNAP_BYTES)
    short = bytes(range(60))
    long = bytes(range(256)) * 6

    capture.record(short)
    capture.record(long)
    capture.close()

    assert capture.frames == 2
    assert read_capture(path) == [(60, short), (len(long), long[:SNAP_BYTES])]


def test_an_empty_capture_holds_only_its_header(tmp_path: Path) -> None:
    path = tmp_path / "traffic.pcap"
    Capture(path, SNAP_BYTES).close()

    assert path.stat().st_size == GLOBAL_HEADER.size
    assert read_capture(path) == []


def test_a_file_that_is_no_ethernet_capture_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "traffic.pcap"
    path.write_bytes(bytes(GLOBAL_HEADER.size))

    with pytest.raises(ValueError, match="not an Ethernet capture"):
        read_capture(path)
