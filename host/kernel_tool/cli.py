import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from kernel_tool.outcome import ExitCode, ToolError
from kernel_tool.toolchain.inventory import Inventory, collect_inventory
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain, ensure_toolchain
from kernel_tool.workspace import Workspace, open_workspace

logger = logging.getLogger("kernel_tool")

Command = Callable[[Workspace, argparse.Namespace], ExitCode]


def main(arguments: Sequence[str] | None = None) -> int:
    options = _build_parser().parse_args(arguments)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        workspace = open_workspace(Path.cwd(), options.build_dir, os.environ)
        return COMMANDS[options.command](workspace, options)
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
    commands.add_parser("toolchain", help="download, verify and unpack the pinned toolchain")
    inventory = commands.add_parser(
        "inventory", help="report version and hash of every tool the build uses"
    )
    inventory.add_argument("--json", action="store_true", help="print the inventory as JSON")
    return parser


def _load_toolchain(workspace: Workspace) -> Toolchain:
    return ensure_toolchain(load_lock(workspace.lock_file), workspace.cache_dir)


def _run_toolchain(workspace: Workspace, _options: argparse.Namespace) -> ExitCode:
    toolchain = _load_toolchain(workspace)
    for artifact in toolchain.lock.artifacts:
        logger.info(
            "%s %s ready at %s", artifact.name, artifact.version, toolchain.roots[artifact.name]
        )
    return ExitCode.OK


def _run_inventory(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    inventory = collect_inventory(_load_toolchain(workspace))
    as_json: bool = options.json
    sys.stdout.write(_format_inventory_json(inventory) if as_json else _format_inventory(inventory))
    return ExitCode.OK


def _format_inventory_json(inventory: Inventory) -> str:
    return json.dumps(inventory.to_document(), indent=2, sort_keys=True) + "\n"


def _format_inventory(inventory: Inventory) -> str:
    lines = [f"host {inventory.host}", f"source_date_epoch {inventory.source_date_epoch}"]
    lines.extend(
        f"artifact {record.name} {record.version} sha256={record.sha256} license={record.license}"
        for record in inventory.artifacts
    )
    lines.extend(
        f"component {record.name} {record.version} sha256={record.sha256} license={record.license}"
        for record in inventory.components
    )
    lines.extend(
        f"tool {record.name} [{record.origin}] {record.version} sha256={record.sha256}"
        for record in inventory.tools
    )
    return "\n".join(lines) + "\n"


COMMANDS: dict[str, Command] = {
    "toolchain": _run_toolchain,
    "inventory": _run_inventory,
}
