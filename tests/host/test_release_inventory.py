from dataclasses import replace
from pathlib import Path

from kernel_tool.release.advisories import (
    Advisory,
    Review,
    ReviewedComponent,
    load_review,
    review_problems,
)
from kernel_tool.release.identity import project_repository, project_version
from kernel_tool.release.licenses import (
    COMPILER_RUNTIME,
    PROJECT,
    Role,
    incompatibilities,
    license_inventory,
)
from kernel_tool.release.sbom import spdx_document
from kernel_tool.toolchain.lock import load_lock

REPOSITORY = Path(__file__).resolve().parents[2]
LOCK = load_lock(REPOSITORY / "toolchain.lock.toml")
FILES = {"kernel.elf": "a" * 64, "init.img": "b" * 64}


def test_the_inventory_separates_what_is_distributed_from_what_is_only_needed() -> None:
    records = {record.component: record for record in license_inventory(REPOSITORY, LOCK)}

    assert records[PROJECT].role is Role.PRODUCT
    assert records[PROJECT].version == project_version(REPOSITORY)
    assert records["micropython"].distributed and records[COMPILER_RUNTIME].distributed
    assert not records["qemu-riscv"].distributed
    assert not records["opensbi"].distributed
    assert not records["riscv-none-elf-gcc"].distributed
    assert incompatibilities(tuple(records.values())) == []


def test_a_linked_component_under_an_unaccepted_license_is_reported() -> None:
    records = license_inventory(REPOSITORY, LOCK)
    changed = tuple(
        replace(record, license="GPL-2.0-only") if record.component == "micropython" else record
        for record in records
    )

    assert incompatibilities(changed) == [
        "micropython 1.29.0: GPL-2.0-only is not accepted in a distributed image"
    ]


def test_the_bill_of_materials_names_every_component_and_file() -> None:
    records = license_inventory(REPOSITORY, LOCK)
    repository = project_repository(REPOSITORY)

    document = spdx_document(records, LOCK, FILES, repository, ("_muldi3.o",))

    packages = {package["name"]: package for package in document["packages"]}
    kinds = {relation["relationshipType"] for relation in document["relationships"]}
    assert document == spdx_document(records, LOCK, FILES, repository, ("_muldi3.o",))
    assert set(packages) == {record.component for record in records}
    assert (
        packages["micropython"]["checksums"][0]["checksumValue"]
        == LOCK.artifact("micropython").sha256
    )
    assert "_muldi3.o" in packages[COMPILER_RUNTIME]["comment"]
    assert [file["fileName"] for file in document["files"]] == ["./init.img", "./kernel.elf"]
    assert kinds == {
        "DESCRIBES",
        "CONTAINS",
        "STATIC_LINK",
        "BUILD_TOOL_OF",
        "RUNTIME_DEPENDENCY_OF",
    }
    assert str(document["documentNamespace"]).startswith(repository + "/spdx/")


def test_every_pinned_component_has_a_review_of_its_pinned_version() -> None:
    review = load_review(REPOSITORY)

    assert review_problems(LOCK, review) == []
    assert review.sources and review.reviewed


def test_a_review_of_another_version_or_an_open_advisory_blocks() -> None:
    review = load_review(REPOSITORY)
    open_advisory = Advisory("CVE-0000-0001", "critical", True, "reachable", "")
    treated = replace(open_advisory, identifier="CVE-0000-0002", treatment="patched in the port")
    components = tuple(
        ReviewedComponent(component.name, "0.0.1", ())
        if component.name == "opensbi"
        else replace(component, advisories=(open_advisory, treated))
        if component.name == "micropython"
        else component
        for component in review.components
        if component.name != "qemu-riscv"
    )

    problems = review_problems(LOCK, Review(review.reviewed, review.sources, components))

    assert problems == [
        "micropython 1.29.0: CVE-0000-0001 is critical, applicable and untreated",
        "opensbi: the review covers 0.0.1 but the lock pins 1.5.1",
        "qemu-riscv 9.2.4-1: no advisory review",
    ]
