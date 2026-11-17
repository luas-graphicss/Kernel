import argparse
import logging
import shutil
import sys

from kernel_tool.build.native import BuildOutputs, build_image, build_outputs
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.qualification.evidence import (
    REPRODUCTION,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.workspace import Workspace

CLEAN_BUILDS = ("first", "second")

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    reproduce = commands.add_parser(
        "reproduce-build",
        help="build twice in empty directories and require images identical to each other "
        "and to the current build",
    )
    add_profile_option(reproduce)
    reproduce.set_defaults(handler=run_reproduce)


def run_reproduce(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    current = build_outputs(workspace, profile)
    builds = []
    for label in CLEAN_BUILDS:
        directory = current.directory.with_name(f"{current.directory.name}-reproduce-{label}")
        if directory.exists():
            shutil.rmtree(directory)
        builds.append(build_image(workspace, profile, toolchain, directory))

    hashes = [artifact_hashes(build) for build in builds]
    differing = sorted(name for name in hashes[0] if hashes[0][name] != hashes[1][name])
    compared = current.kernel.is_file()
    stale = []
    if compared:
        present = artifact_hashes(current)
        stale = sorted(name for name in present if present[name] != hashes[0][name])
    for name, digest in hashes[0].items():
        sys.stdout.write(f"artifact {name} sha256={digest}\n")

    report = evidence_file(current, REPRODUCTION)
    passed = not differing and not stale and compared
    write_evidence(
        report,
        {
            "profile": profile.name,
            "artifacts": artifact_identity(current),
            "source_date_epoch": toolchain.lock.source_date_epoch,
            "builds": [
                {"directory": str(build.directory), "sha256": digests}
                for build, digests in zip(builds, hashes, strict=True)
            ],
            "differing": differing,
            "differing_from_current": stale,
            "compared_with_current": compared,
            "passed": passed,
        },
    )
    if differing:
        raise CheckError(f"two clean builds differ in {', '.join(differing)}; see {report}")
    if stale:
        raise CheckError(
            f"the current build differs from a clean build in {', '.join(stale)}; see {report}"
        )
    if not compared:
        raise CheckError("there is no current build to compare; run kernel-tool build first")
    logger.info("two clean builds and the current build are identical; see %s", report)
    return ExitCode.OK


def artifact_hashes(outputs: BuildOutputs) -> dict[str, str]:
    return {artifact.name: sha256_file(artifact) for artifact in outputs.artifacts}
