import argparse
import json
import logging
import sys

from kernel_tool.commands.options import CommandRegistry, load_toolchain
from kernel_tool.outcome import ExitCode
from kernel_tool.toolchain.inventory import Inventory, collect_inventory
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    toolchain = commands.add_parser(
        "toolchain", help="download, verify and unpack the pinned toolchain"
    )
    toolchain.set_defaults(handler=run_toolchain)

    inventory = commands.add_parser(
        "inventory", help="report version and hash of every tool the build uses"
    )
    inventory.add_argument("--json", action="store_true", help="print the inventory as JSON")
    inventory.set_defaults(handler=run_inventory)


def run_toolchain(workspace: Workspace, _options: argparse.Namespace) -> ExitCode:
    toolchain = load_toolchain(workspace)
    for artifact in toolchain.lock.artifacts:
        logger.info(
            "%s %s ready at %s", artifact.name, artifact.version, toolchain.roots[artifact.name]
        )
    return ExitCode.OK


def run_inventory(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    inventory = collect_inventory(load_toolchain(workspace))
    as_json: bool = options.json
    sys.stdout.write(format_inventory_json(inventory) if as_json else format_inventory(inventory))
    return ExitCode.OK


def format_inventory_json(inventory: Inventory) -> str:
    return json.dumps(inventory.to_document(), indent=2, sort_keys=True) + "\n"


def format_inventory(inventory: Inventory) -> str:
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
