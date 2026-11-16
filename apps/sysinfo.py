import sys

from kernel_apps import runtime
from kernel_protocol.errors.codes import OK
from kernel_services.network.ipv4.address import format_address

MODE_NAMES = ("read-only", "read-write")


def describe_files(application: runtime.Application) -> None:
    namespace = application.files
    if namespace is None:
        print("sysinfo: files=none")
        return
    for mount in namespace.status():
        name = str(mount.name, "utf-8")
        if mount.code != OK:
            print(f"sysinfo: mount={name} state=unavailable")
        else:
            print(f"sysinfo: mount={name} mode={MODE_NAMES[mount.mode]}")


def describe_network(application: runtime.Application) -> None:
    network = application.network
    if network is None:
        print("sysinfo: network=none")
        return
    status = network.status()
    print(
        f"sysinfo: address={format_address(status.address)}/{status.prefix} "
        f"link={'up' if status.is_linked else 'down'}"
    )


def main() -> bool:
    application = runtime.current()
    version = sys.implementation.version
    print(
        f"sysinfo: runtime={sys.implementation.name}-{version[0]}.{version[1]} "
        f"platform={sys.platform} arguments={len(application.arguments) - 1}"
    )
    describe_files(application)
    describe_network(application)
    return True
