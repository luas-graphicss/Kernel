from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kernel_tool.outcome import CheckError
from kernel_tool.release.identity import project_license, project_version
from kernel_tool.toolchain.lock import ToolchainLock
from kernel_tool.toolchain.resolve import (
    COMPILER_ARTIFACT,
    EMULATOR_ARTIFACT,
    FIRMWARE_COMPONENT,
    RUNTIME_ARTIFACT,
    Toolchain,
)

PROJECT = "kernel"
COMPILER_RUNTIME = "libgcc"
PROJECT_LICENSE_FILE = "LICENSE"
RUNTIME_LICENSE_FILE = "LICENSE"
COMPILER_RUNTIME_EXCEPTION = "COPYING.RUNTIME"
ACCEPTED_WHEN_LINKED = frozenset(
    {
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "GPL-3.0-or-later WITH GCC-exception-3.1",
    }
)


class Role(StrEnum):
    PRODUCT = "product"
    LINKED = "linked"
    BUILD_TOOL = "build-tool"
    FIRMWARE = "firmware"
    EMULATOR = "emulator"


DISTRIBUTED_ROLES = (Role.PRODUCT, Role.LINKED)
ARTIFACT_ROLES = {
    COMPILER_ARTIFACT: Role.BUILD_TOOL,
    EMULATOR_ARTIFACT: Role.EMULATOR,
    RUNTIME_ARTIFACT: Role.LINKED,
}
COMPONENT_ROLES = {FIRMWARE_COMPONENT: Role.FIRMWARE}


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    component: str
    version: str
    license: str
    role: Role
    distributed: bool
    text: str | None


def license_inventory(root: Path, lock: ToolchainLock) -> tuple[LicenseRecord, ...]:
    records = [
        _record(PROJECT, project_version(root), project_license(root), Role.PRODUCT, PROJECT)
    ]
    for artifact in lock.artifacts:
        role = ARTIFACT_ROLES.get(artifact.name)
        if role is None:
            raise CheckError(f"{artifact.name}: the license inventory knows no role for it")
        text = artifact.name if role is Role.LINKED else None
        records.append(_record(artifact.name, artifact.version, artifact.license, role, text))
        if artifact.name == COMPILER_ARTIFACT:
            records.append(
                _record(
                    COMPILER_RUNTIME,
                    artifact.version,
                    artifact.license,
                    Role.LINKED,
                    COMPILER_RUNTIME,
                )
            )
    for component in lock.components:
        role = COMPONENT_ROLES.get(component.name)
        if role is None:
            raise CheckError(f"{component.name}: the license inventory knows no role for it")
        records.append(_record(component.name, component.version, component.license, role, None))
    return tuple(records)


def incompatibilities(records: tuple[LicenseRecord, ...]) -> list[str]:
    return [
        f"{record.component} {record.version}: {record.license} is not accepted "
        "in a distributed image"
        for record in records
        if record.distributed and record.license not in ACCEPTED_WHEN_LINKED
    ]


def license_texts(root: Path, toolchain: Toolchain) -> dict[str, Path]:
    exception = sorted(toolchain.compiler_root.rglob(COMPILER_RUNTIME_EXCEPTION))
    if not exception:
        raise CheckError(f"{COMPILER_RUNTIME_EXCEPTION} was not found in the pinned compiler")
    texts = {
        PROJECT: root / PROJECT_LICENSE_FILE,
        RUNTIME_ARTIFACT: toolchain.runtime_source / RUNTIME_LICENSE_FILE,
        COMPILER_RUNTIME: exception[0],
    }
    for name, path in texts.items():
        if not path.is_file():
            raise CheckError(f"the license text of {name} is missing: {path}")
    return texts


def _record(
    name: str, version: str, license_expression: str, role: Role, text: str | None
) -> LicenseRecord:
    distributed = role in DISTRIBUTED_ROLES
    return LicenseRecord(
        component=name,
        version=version,
        license=license_expression,
        role=role,
        distributed=distributed,
        text=f"licenses/{text}.txt" if text is not None else None,
    )
