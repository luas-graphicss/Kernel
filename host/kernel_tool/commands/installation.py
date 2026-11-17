import argparse
import logging
from pathlib import Path

from kernel_tool.commands.options import CommandRegistry
from kernel_tool.commands.release import add_signer_options, verify_release
from kernel_tool.outcome import ExitCode
from kernel_tool.release.installation import Installation, install, rollback, update
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    installing = commands.add_parser(
        "install", help="place a release bundle in a directory and create its data volume"
    )
    add_bundle_options(installing)
    installing.set_defaults(handler=run_install)

    updating = commands.add_parser(
        "update", help="replace the installed release, keeping the earlier one and the data volume"
    )
    add_bundle_options(updating)
    updating.set_defaults(handler=run_update)

    returning = commands.add_parser(
        "rollback", help="return to the earlier release when it reads the format of the volume"
    )
    add_target_option(returning)
    returning.set_defaults(handler=run_rollback)


def add_target_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", type=Path, required=True, help="installation directory")


def add_bundle_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("bundle", type=Path, help="release bundle directory")
    add_target_option(parser)
    add_signer_options(parser)


def run_install(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    verify_release(options.bundle, options.allowed_signers, options.identity)
    target: Path = options.target
    target.mkdir(parents=True, exist_ok=True)
    return report(install(options.bundle, target))


def run_update(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    verify_release(options.bundle, options.allowed_signers, options.identity)
    return report(update(options.bundle, options.target))


def run_rollback(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    return report(rollback(options.target))


def report(installation: Installation) -> ExitCode:
    logger.info(
        "%s runs %s; earlier release: %s; data volume: %s",
        installation.target,
        installation.current,
        installation.previous or "none",
        installation.data_image,
    )
    return ExitCode.OK
