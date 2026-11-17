import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from kernel_tool.commands import (
    artifacts,
    benchmark,
    boots,
    build,
    emulation,
    fault_test,
    fuzz,
    interfaces,
    soak,
    storage,
    test,
    toolchain,
)
from kernel_tool.commands.options import Command
from kernel_tool.outcome import ToolError
from kernel_tool.workspace import open_workspace

REGISTRARS = (
    toolchain.register,
    build.register,
    emulation.register,
    test.register,
    fault_test.register,
    fuzz.register,
    boots.register,
    soak.register,
    benchmark.register,
    storage.register,
    artifacts.register,
    interfaces.register,
)

logger = logging.getLogger("kernel_tool")


def main(arguments: Sequence[str] | None = None) -> int:
    options = _build_parser().parse_args(arguments)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    handler: Command = options.handler
    try:
        workspace = open_workspace(Path.cwd(), options.build_dir, os.environ)
        return handler(workspace, options)
    except ToolError as error:
        logger.error("%s: %s", error.label, error)
        return error.exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kernel-tool", description="Build, run and verify the kernel image."
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="build output directory (default: <repository>/build)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for register in REGISTRARS:
        register(commands)
    return parser
