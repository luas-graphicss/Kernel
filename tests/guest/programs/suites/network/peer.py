from kernel_services.network.ipv4.address import parse_address

GUEST = parse_address("10.0.2.15")
PEER = parse_address("10.0.2.2")
ABSENT = parse_address("10.0.2.99")
REMOTE = parse_address("192.0.2.1")
BROADCAST = parse_address("10.0.2.255")
PREFIX = 24
MTU = 1500
HARDWARE = b"\x52\x54\x00\x12\x34\x56"
ECHO_PORT = 7
SINK_PORT = 9
SILENT_PORT = 13
SLOW_PORT = 14
SOURCE_PORT = 19
CLOSED_PORT = 81
LISTEN_PORT = 8080
DIGEST_BYTES = 32
SECOND = 1000000000
MILLISECOND = 1000000
