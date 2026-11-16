import argparse
from collections.abc import Callable

from kernel_tool.build.native import build_outputs, require_artifacts
from kernel_tool.outcome import ExitCode
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from kernel_tool.profiles.model import Profile
from kernel_tool.scenarios.runner import SuiteContext
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain, ensure_toolchain
from kernel_tool.workspace import Workspace

type Command = Callable[[Workspace, argparse.Namespace], ExitCode]
type CommandRegistry = argparse._SubParsersAction[argparse.ArgumentParser]


def add_profile_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"profile from config/profiles (default: {DEFAULT_PROFILE})",
    )


def selected_profile(workspace: Workspace, options: argparse.Namespace) -> Profile:
    name: str = options.profile
    return load_profile(workspace.root, name)


def load_toolchain(workspace: Workspace) -> Toolchain:
    return ensure_toolchain(load_lock(workspace.lock_file), workspace.cache_dir)


def suite_context(workspace: Workspace, options: argparse.Namespace) -> SuiteContext:
    profile = selected_profile(workspace, options)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)
    directory = outputs.directory / "scenarios"
    directory.mkdir(parents=True, exist_ok=True)
    return SuiteContext(
        root=workspace.root,
        profile=profile,
        toolchain=load_toolchain(workspace),
        outputs=outputs,
        directory=directory,
    )
