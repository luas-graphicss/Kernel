import fcntl
import os
import socket
import struct
from pathlib import Path

TUN_DEVICE = "/dev/net/tun"
TUNSETIFF = 0x400454CA
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000
IFF_UP = 0x0001
IFF_RUNNING = 0x0040
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
SIOCSIFADDR = 0x8916
SIOCSIFNETMASK = 0x891C
INTERFACE_NAME_BYTES = 16
LOOPBACK = "lo"
ADDRESS_BITS = 32
IPV6_SWITCH = Path("/proc/sys/net/ipv6/conf/all/disable_ipv6")


def enter_private_network(rootless: bool) -> None:
    if not rootless:
        os.unshare(os.CLONE_NEWNET)
        return
    user = os.getuid()
    group = os.getgid()
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNET)
    Path("/proc/self/setgroups").write_text("deny", encoding="ascii")
    Path("/proc/self/uid_map").write_text(f"0 {user} 1", encoding="ascii")
    Path("/proc/self/gid_map").write_text(f"0 {group} 1", encoding="ascii")


def open_tap(name: str) -> int:
    descriptor = os.open(TUN_DEVICE, os.O_RDWR)
    request = struct.pack("16sH22x", name.encode("ascii"), IFF_TAP | IFF_NO_PI)
    fcntl.ioctl(descriptor, TUNSETIFF, request)
    return descriptor


def _address_request(name: str, address: str) -> bytes:
    endpoint = struct.pack("H2s4s8s", socket.AF_INET, b"", socket.inet_aton(address), b"")
    return struct.pack("16s16s8x", name.encode("ascii"), endpoint)


def _netmask(prefix: int) -> str:
    mask = (0xFFFFFFFF << (ADDRESS_BITS - prefix)) & 0xFFFFFFFF
    return socket.inet_ntoa(mask.to_bytes(4, "big"))


def bring_up(name: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        request = struct.pack("16sH22x", name.encode("ascii"), 0)
        flags = struct.unpack("16sH22x", fcntl.ioctl(control, SIOCGIFFLAGS, request))[1]
        request = struct.pack("16sH22x", name.encode("ascii"), flags | IFF_UP | IFF_RUNNING)
        fcntl.ioctl(control, SIOCSIFFLAGS, request)


def assign_address(name: str, address: str, prefix: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        fcntl.ioctl(control, SIOCSIFADDR, _address_request(name, address))
        fcntl.ioctl(control, SIOCSIFNETMASK, _address_request(name, _netmask(prefix)))


def silence_ipv6() -> None:
    try:
        IPV6_SWITCH.write_text("1", encoding="ascii")
    except OSError:
        return


def build_interface(name: str, address: str, prefix: int, rootless: bool) -> int:
    enter_private_network(rootless)
    silence_ipv6()
    bring_up(LOOPBACK)
    tap = open_tap(name)
    assign_address(name, address, prefix)
    bring_up(name)
    return tap
