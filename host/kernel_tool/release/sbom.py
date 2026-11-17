import hashlib
from datetime import UTC, datetime

from kernel_tool.release.licenses import COMPILER_RUNTIME, PROJECT, LicenseRecord, Role
from kernel_tool.toolchain.lock import ToolchainLock

SPDX_VERSION = "SPDX-2.3"
DATA_LICENSE = "CC0-1.0"
DOCUMENT = "SPDXRef-DOCUMENT"
NO_ASSERTION = "NOASSERTION"
CREATED_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
RELATIONSHIPS = {
    Role.LINKED: ("STATIC_LINK", True),
    Role.BUILD_TOOL: ("BUILD_TOOL_OF", False),
    Role.FIRMWARE: ("RUNTIME_DEPENDENCY_OF", False),
    Role.EMULATOR: ("RUNTIME_DEPENDENCY_OF", False),
}
PURPOSES = {
    Role.PRODUCT: "OPERATING-SYSTEM",
    Role.LINKED: "LIBRARY",
    Role.BUILD_TOOL: "APPLICATION",
    Role.FIRMWARE: "FIRMWARE",
    Role.EMULATOR: "APPLICATION",
}


def spdx_document(
    records: tuple[LicenseRecord, ...],
    lock: ToolchainLock,
    files: dict[str, str],
    repository: str,
    linked_members: tuple[str, ...],
) -> dict[str, object]:
    product = next(record for record in records if record.role is Role.PRODUCT)
    content = hashlib.sha256("".join(sorted(files.values())).encode("ascii")).hexdigest()
    name = f"{product.component}-{product.version}"
    return {
        "spdxVersion": SPDX_VERSION,
        "dataLicense": DATA_LICENSE,
        "SPDXID": DOCUMENT,
        "name": name,
        "documentNamespace": f"{repository}/spdx/{name}-{content}",
        "creationInfo": {
            "created": datetime.fromtimestamp(lock.source_date_epoch, UTC).strftime(CREATED_FORMAT),
            "creators": [f"Tool: kernel-tool-{product.version}"],
        },
        "packages": [_package(record, lock, linked_members) for record in records],
        "files": [_file(file, digest) for file, digest in sorted(files.items())],
        "relationships": [
            {
                "spdxElementId": DOCUMENT,
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": _package_id(PROJECT),
            },
            *(_file_relationship(file) for file in sorted(files)),
            *(_relationship(record) for record in records if record.role is not Role.PRODUCT),
        ],
    }


def _package(
    record: LicenseRecord, lock: ToolchainLock, linked_members: tuple[str, ...]
) -> dict[str, object]:
    package: dict[str, object] = {
        "SPDXID": _package_id(record.component),
        "name": record.component,
        "versionInfo": record.version,
        "downloadLocation": NO_ASSERTION,
        "filesAnalyzed": False,
        "licenseConcluded": record.license,
        "licenseDeclared": record.license,
        "copyrightText": NO_ASSERTION,
        "primaryPackagePurpose": PURPOSES[record.role],
    }
    pinned = {artifact.name: artifact for artifact in lock.artifacts}
    artifact = pinned.get(record.component)
    if artifact is not None:
        package["downloadLocation"] = artifact.url
        package["checksums"] = [{"algorithm": "SHA256", "checksumValue": artifact.sha256}]
    for component in lock.components:
        if component.name == record.component:
            package["checksums"] = [{"algorithm": "SHA256", "checksumValue": component.sha256}]
            package["comment"] = f"taken from {component.artifact}: {component.path}"
    if record.component == COMPILER_RUNTIME:
        package["comment"] = "members linked into the images: " + ", ".join(linked_members)
    return package


def _file(name: str, digest: str) -> dict[str, object]:
    return {
        "SPDXID": _file_id(name),
        "fileName": f"./{name}",
        "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
        "licenseConcluded": NO_ASSERTION,
        "copyrightText": NO_ASSERTION,
    }


def _file_relationship(name: str) -> dict[str, str]:
    return {
        "spdxElementId": _package_id(PROJECT),
        "relationshipType": "CONTAINS",
        "relatedSpdxElement": _file_id(name),
    }


def _relationship(record: LicenseRecord) -> dict[str, str]:
    kind, from_product = RELATIONSHIPS[record.role]
    product, other = _package_id(PROJECT), _package_id(record.component)
    return {
        "spdxElementId": product if from_product else other,
        "relationshipType": kind,
        "relatedSpdxElement": other if from_product else product,
    }


def _package_id(name: str) -> str:
    return f"SPDXRef-Package-{name}"


def _file_id(name: str) -> str:
    return "SPDXRef-File-" + name.replace(".", "-").replace("/", "-")
