import argparse
import logging
import sys

from kernel_tool.commands.options import CommandRegistry
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.release.interfaces import (
    LOCK_FILE,
    check_interfaces,
    freeze_interfaces,
    load_interfaces,
)
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    verify = commands.add_parser(
        "verify-interfaces",
        help="compare the sources of the frozen interfaces with their recorded digests",
    )
    verify.add_argument(
        "--freeze",
        action="store_true",
        help=f"record the current digests in {LOCK_FILE} instead of comparing",
    )
    verify.set_defaults(handler=run_interfaces)


def run_interfaces(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    freeze: bool = options.freeze
    if freeze:
        freeze_interfaces(workspace.root)
        logger.info("recorded the digests in %s", workspace.root / LOCK_FILE)
    for interface in load_interfaces(workspace.root):
        sys.stdout.write(f"interface {interface.name} {interface.version} {interface.digest}\n")
    problems = check_interfaces(workspace.root)
    if problems:
        raise CheckError("frozen interfaces changed:\n" + "\n".join(problems))
    return ExitCode.OK
