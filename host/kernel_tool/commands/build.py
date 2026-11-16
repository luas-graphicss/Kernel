import argparse
import logging

from kernel_tool.build.native import ANALYSIS_GOAL, build_image, run_make
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import ExitCode
from kernel_tool.verification.native_check import run_hosted_tests
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    native_check = commands.add_parser(
        "native-check",
        help="run the hosted native tests under sanitizers and the static analyzer",
    )
    add_profile_option(native_check)
    native_check.set_defaults(handler=run_native_check)

    build = commands.add_parser("build", help="build the kernel image with the pinned toolchain")
    add_profile_option(build)
    build.set_defaults(handler=run_build)


def run_native_check(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    suites = run_hosted_tests(workspace)
    run_make(
        workspace, selected_profile(workspace, options), load_toolchain(workspace), ANALYSIS_GOAL
    )
    logger.info("native check passed: %s and static analysis", ", ".join(suites))
    return ExitCode.OK


def run_build(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    outputs = build_image(
        workspace, selected_profile(workspace, options), load_toolchain(workspace)
    )
    logger.info("built %s", outputs.kernel)
    return ExitCode.OK
