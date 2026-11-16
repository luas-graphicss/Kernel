import argparse
import json
import logging
import sys

from kernel_tool.build.native import build_image, build_outputs, require_artifacts
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.toolchain.inventory import collect_inventory
from kernel_tool.verification.artifacts import (
    ArtifactReport,
    differing_artifacts,
    verify_artifacts,
)
from kernel_tool.workspace import Workspace

REPRODUCTION_SUFFIX = "-reproduce"

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    verify = commands.add_parser(
        "verify-artifacts",
        help="inspect the built images: static linking, input origins, layout and hashes",
    )
    add_profile_option(verify)
    verify.add_argument(
        "--reproduce",
        action="store_true",
        help="build again in a second directory and require identical images",
    )
    verify.set_defaults(handler=run_verify)


def run_verify(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)

    report = verify_artifacts(outputs, profile, toolchain)
    problems = list(report.problems)
    reproduce: bool = options.reproduce
    if reproduce:
        second_directory = outputs.directory.with_name(outputs.directory.name + REPRODUCTION_SUFFIX)
        rebuilt = build_image(workspace, profile, toolchain, second_directory)
        problems.extend(
            f"{name}: a second build in {second_directory} produced a different image"
            for name in differing_artifacts(outputs, rebuilt)
        )

    document = report.to_document() | {
        "profile": profile.name,
        "reproduced": reproduce and not problems,
        "inventory": collect_inventory(toolchain).to_document(),
        "problems": problems,
    }
    report_file = outputs.directory / "reports" / "artifacts.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(format_report(report))

    if problems:
        raise CheckError("artifact verification failed:\n" + "\n".join(problems))
    logger.info("artifacts verified; report written to %s", report_file)
    return ExitCode.OK


def format_report(report: ArtifactReport) -> str:
    lines = [
        f"artifact {record.name} bytes={record.bytes} sha256={record.sha256}"
        for record in report.artifacts
    ]
    lines.extend(
        f"executable {record.name} entry={record.entry:#x} "
        f"segments={len(record.load_segments)} "
        f"libgcc={','.join(record.compiler_library_members) or 'none'}"
        for record in report.executables
    )
    return "\n".join(lines) + "\n"
