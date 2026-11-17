from kernel_tool.fuzzing.model import Family, Target
from kernel_tool.fuzzing.targets import boot, interface, network, storage
from kernel_tool.outcome import CheckError

TARGETS: tuple[Target, ...] = (
    *boot.TARGETS,
    *interface.TARGETS,
    *storage.TARGETS,
    *network.TARGETS,
)


def targets_of(family: Family) -> tuple[Target, ...]:
    return tuple(target for target in TARGETS if target.family is family)


def target_named(family: Family, name: str) -> Target:
    for target in targets_of(family):
        if target.name == name:
            return target
    raise CheckError(f"the {family.value} family has no fuzzing target named {name!r}")
