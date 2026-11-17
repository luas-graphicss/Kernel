import json
import shutil
from dataclasses import asdict
from pathlib import Path

from kernel_services.filesystem.boot.layout import ABI_VERSION
from kernel_services.filesystem.format.layout import FORMAT_VERSION
from kernel_tool.build.native import BuildOutputs
from kernel_tool.profiles.model import Profile
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qemu.drives import FileDrive
from kernel_tool.release.checksums import write_checksums
from kernel_tool.release.identity import project_repository, project_version
from kernel_tool.release.interfaces import load_interfaces
from kernel_tool.release.licenses import LicenseRecord, license_inventory, license_texts
from kernel_tool.release.sbom import spdx_document
from kernel_tool.scenarios.disks import BOOT_IDENTITY, DATA_IDENTITY
from kernel_tool.scenarios.guest_program import INIT_OPTION
from kernel_tool.scenarios.shell import MANAGER_PROGRAM
from kernel_tool.storage.boot_image import runtime_tag
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.verification.artifacts import verify_artifacts
from kernel_tool.workspace import LOCK_FILE_NAME, Workspace

RELEASE_DIRECTORY = "release"
MANIFEST_FILE = "manifest.json"
SBOM_FILE = "sbom.spdx.json"
LICENSES_FILE = "licenses.json"
REPORT_FILE = "release-report.json"
PROFILE_FILE = "profile.toml"
DATA_IMAGE = "data.img"
EMULATOR_PLACEHOLDER = "{emulator}"
FIRMWARE_PLACEHOLDER = "{firmware}"
ARTIFACT_ROLES = (
    ("kernel.elf", "kernel image with the supervisor runtime and the policy"),
    ("init.img", "user runtime with the services, the shell and the application runner"),
    ("boot.img", "boot volume with the configuration, the release identity and the programs"),
)
ENCODING = "utf-8"


def bundle_name(root: Path, profile: Profile) -> str:
    return f"kernel-{project_version(root)}-{profile.name}"


def bundle_directory(workspace: Workspace, outputs: BuildOutputs, profile: Profile) -> Path:
    return outputs.directory / RELEASE_DIRECTORY / bundle_name(workspace.root, profile)


def assemble_bundle(
    workspace: Workspace,
    profile: Profile,
    toolchain: Toolchain,
    outputs: BuildOutputs,
    report: dict[str, object],
) -> Path:
    root = workspace.root
    directory = bundle_directory(workspace, outputs, profile)
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)

    sources = {outputs.kernel.name: outputs.kernel, outputs.init_image.name: outputs.init_image}
    sources[outputs.boot_image.name] = outputs.boot_image
    for name, _role in ARTIFACT_ROLES:
        shutil.copyfile(sources[name], directory / name)
    shutil.copyfile(root / LOCK_FILE_NAME, directory / LOCK_FILE_NAME)
    shutil.copyfile(root / "config" / "profiles" / f"{profile.name}.toml", directory / PROFILE_FILE)

    records = license_inventory(root, toolchain.lock)
    for name, text in license_texts(root, toolchain).items():
        target = directory / "licenses" / f"{name}.txt"
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(text, target)
    hashes = {name: sha256_file(directory / name) for name, _role in ARTIFACT_ROLES}
    members = linked_members(outputs, profile, toolchain)
    sbom = spdx_document(records, toolchain.lock, hashes, project_repository(root), members)

    _write(directory / LICENSES_FILE, {"licenses": [asdict(record) for record in records]})
    _write(directory / SBOM_FILE, sbom)
    _write(directory / REPORT_FILE, report)
    _write(directory / MANIFEST_FILE, manifest(root, profile, toolchain, hashes, records, report))
    write_checksums(directory)
    return directory


def linked_members(
    outputs: BuildOutputs, profile: Profile, toolchain: Toolchain
) -> tuple[str, ...]:
    report = verify_artifacts(outputs, profile, toolchain)
    released = (outputs.kernel.name, outputs.init_program.name)
    members = {
        member
        for record in report.executables
        if record.name in released
        for member in record.compiler_library_members
    }
    return tuple(sorted(members))


def manifest(
    root: Path,
    profile: Profile,
    toolchain: Toolchain,
    hashes: dict[str, str],
    records: tuple[LicenseRecord, ...],
    report: dict[str, object],
) -> dict[str, object]:
    lock = toolchain.lock
    return {
        "name": "kernel",
        "version": project_version(root),
        "profile": profile.name,
        "qualified": report.get("ready") is True,
        "artifacts": [
            {"file": name, "role": role, "sha256": hashes[name]} for name, role in ARTIFACT_ROLES
        ],
        "interfaces": [
            {"name": interface.name, "version": interface.version, "digest": interface.digest}
            for interface in load_interfaces(root)
        ],
        "boot_image_abi": ABI_VERSION,
        "volume_formats": [FORMAT_VERSION],
        "runtime": runtime_tag(lock).decode("ascii"),
        "source_date_epoch": lock.source_date_epoch,
        "requires": [
            {"name": record.component, "version": record.version, "role": record.role.value}
            for record in records
            if not record.distributed
        ],
        "launch": launch_command(profile, toolchain),
    }


def launch_command(profile: Profile, toolchain: Toolchain) -> list[str]:
    request = BootRequest(
        kernel=Path("kernel.elf"),
        memory_mib=profile.machine.memory_mib,
        boot_module=Path("init.img"),
        arguments=INIT_OPTION + MANAGER_PROGRAM,
        drives=(
            FileDrive(BOOT_IDENTITY, Path("boot.img"), read_only=True),
            FileDrive(DATA_IDENTITY, Path(DATA_IMAGE)),
        ),
        entropy=True,
    )
    replaced = {
        str(toolchain.emulator(profile.machine.emulator)): EMULATOR_PLACEHOLDER,
        str(toolchain.component_path(profile.machine.firmware)): FIRMWARE_PLACEHOLDER,
    }
    return [replaced.get(word, word) for word in boot_command(profile, toolchain, request)]


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding=ENCODING)
