from kernel_client import capabilities, ipc, processes
from kernel_services.init import checks, probed
from kernel_services.init.system import ServiceSystem


def describe_devices(system: ServiceSystem) -> None:
    inventory = system.inventory
    serial = 1 if inventory.serial else 0
    entropy = 1 if inventory.entropy else 0
    print(f"init: devices serial={serial} entropy={entropy} block={len(inventory.blocks)}")


def run_system(system_handle: int, identity: int) -> bool:
    system = ServiceSystem(system_handle, identity)
    describe_devices(system)
    started = system.start()
    checked = checks.run(system)
    return system.stop() and started and checked


def main() -> bool:
    startup = processes.Startup()
    system = startup.handles[0]
    print("init: runtime=micropython privilege=user")
    registration = ipc.create_endpoint()
    probed_services = probed.run(system, registration)
    capabilities.close(registration)
    return run_system(system, startup.identity) and probed_services
