import argparse
import logging

from kernel_tool.commands.options import CommandRegistry, add_profile_option, suite_context
from kernel_tool.outcome import CheckError, ExitCode, InfrastructureError
from kernel_tool.qualification.boots import BootRecord, boot_repeatedly, boots_document
from kernel_tool.qualification.evidence import (
    BOOTS,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.scenarios.release_suites import BOOT_TO_SHELL
from kernel_tool.workspace import Workspace

DEFAULT_BOOTS = 1000
PROGRESS_INTERVAL = 50

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    boots = commands.add_parser(
        "repeat-boot",
        help="boot the release image to its shell many times and keep the result of every boot",
    )
    add_profile_option(boots)
    boots.add_argument(
        "--count",
        type=positive_count,
        default=DEFAULT_BOOTS,
        help=f"boots to run (default: {DEFAULT_BOOTS})",
    )
    boots.set_defaults(handler=run_boots)


def positive_count(text: str) -> int:
    count = int(text)
    if count <= 0:
        raise argparse.ArgumentTypeError("the count must be greater than zero")
    return count


def run_boots(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    count: int = options.count
    context = suite_context(workspace, options)
    report = evidence_file(context.outputs, BOOTS)
    records: list[BootRecord] = []
    try:
        boot_repeatedly(BOOT_TO_SHELL, context, count, records, log_progress)
    except InfrastructureError:
        logger.error("stopped after %d of %d boots", len(records), count)
        raise
    finally:
        identity = artifact_identity(context.outputs)
        write_evidence(report, boots_document(context.profile.name, identity, count, records))

    failed = [record.number for record in records if not record.passed]
    if failed:
        raise CheckError(f"{len(failed)} of {count} boots failed: {failed}; see {report}")
    logger.info("%d boots reached the shell and stopped in order; see %s", count, report)
    return ExitCode.OK


def log_progress(record: BootRecord) -> None:
    if not record.passed:
        logger.error("boot %d failed: %s", record.number, "; ".join(record.failures))
    elif record.number % PROGRESS_INTERVAL == 0:
        logger.info("%d boots completed", record.number)
