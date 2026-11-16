import hashlib
import zlib

import pytest

from kernel_tool.network.orders import Call, Darken, Inject
from kernel_tool.network.plan import (
    BLOCK_BYTES,
    CLEAN,
    GREETING_LINES,
    GREETING_WORDS_PER_LINE,
    GUEST_ADDRESS,
    PEER_ADDRESS,
    PREFIX,
    LinkPolicy,
    NetworkPlan,
    decode_source_request,
    encode_source_request,
    greeting,
    stream,
    stream_block,
    stream_crc32,
    stream_sha256,
)


def test_a_stream_is_the_same_for_the_same_seed_and_differs_between_seeds() -> None:
    assert stream(3, 5000) == stream(3, 5000)
    assert stream(3, 5000) != stream(4, 5000)
    assert len(stream(3, 5000)) == 5000
    assert stream(3, 5000) == stream(3, 8192)[:5000]


def test_every_block_starts_with_its_own_number() -> None:
    blocks = [stream_block(9, index) for index in range(300)]

    assert all(len(block) == BLOCK_BYTES for block in blocks)
    assert [int.from_bytes(block[:4], "big") for block in blocks] == list(range(300))
    assert len(set(blocks)) == len(blocks)


def test_digests_describe_the_stream_they_name() -> None:
    assert stream_sha256(17, 4096) == hashlib.sha256(stream(17, 4096)).hexdigest()
    assert stream_crc32(23, 4096) == f"{zlib.crc32(stream(23, 4096)):08x}"
    assert len(stream_crc32(1, 1)) == 8


@pytest.mark.parametrize(("seed", "length"), [(0, 0), (23, 131072), (0xFFFFFFFF, 0xFFFFFFFF)])
def test_a_source_request_survives_its_encoding(seed: int, length: int) -> None:
    request = encode_source_request(seed, length)

    assert len(request) == 8
    assert decode_source_request(request) == (seed, length)


def test_the_greeting_is_text_with_a_known_shape() -> None:
    lines = greeting().decode("ascii").splitlines()

    assert len(lines) == GREETING_LINES
    assert all(len(line.split(" ")) == GREETING_WORDS_PER_LINE for line in lines)
    assert lines[0] == "line 0000 of the greeting"
    assert greeting().endswith(b"\n")


def test_a_plan_names_both_stations_and_both_directions() -> None:
    impaired = LinkPolicy(loss=0.03, duplicate=0.02, reorder=0.1, reorder_milliseconds=20)
    document = NetworkPlan(impaired, CLEAN, 7).to_document()

    assert document["address"] == PEER_ADDRESS
    assert document["guest"] == GUEST_ADDRESS
    assert document["prefix"] == PREFIX
    assert document["seed"] == 7
    assert document["uplink"] == {
        "loss": 0.03,
        "duplicate": 0.02,
        "reorder": 0.1,
        "reorder_milliseconds": 20,
        "delay_milliseconds": 0,
    }
    assert document["downlink"] == NetworkPlan().to_document()["uplink"]


def test_orders_become_the_commands_the_station_obeys() -> None:
    assert Call(8080, 5, 4096).to_command() == {
        "command": "call",
        "port": 8080,
        "seed": 5,
        "bytes": 4096,
    }
    assert Inject((b"\x01\x02", b"\xff")).to_command() == {
        "command": "inject",
        "frames": ["0102", "ff"],
    }
    assert Darken(1500).to_command() == {"command": "darken", "milliseconds": 1500}
