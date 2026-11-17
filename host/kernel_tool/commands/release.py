import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from kernel_tool.build.native import build_outputs, require_artifacts
from kernel_tool.commands.fuzz import FUZZ_DIRECTORY
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.qualification.evidence import artifact_identity
from kernel_tool.qualification.gates import Gate, Qualification, evaluate
from kernel_tool.release.bundle import MANIFEST_FILE, assemble_bundle
from kernel_tool.release.checksums import require_intact
from kernel_tool.release.identity import project_version
from kernel_tool.release.signing import sign_bundle, verify_bundle
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    check = commands.add_parser(
        "release-check",
        help="evaluate every release gate and assemble the bundle locally; publishes nothing",
    )
    add_profile_option(check)
    check.set_defaults(handler=run_release_check)

    sign = commands.add_parser(
        "release-sign", help="sign the checksums of a bundle with a key kept outside the repository"
    )
    sign.add_argument("bundle", type=Path, help="bundle directory written by release-check")
    sign.add_argument("--key", type=Path, required=True, help="private OpenSSH signing key")
    sign.add_argument(
        "--rehearsal",
        action="store_true",
        help="allow signing a bundle whose manifest says it is not qualified",
    )
    sign.set_defaults(handler=run_sign)

    verify = commands.add_parser(
        "release-verify",
        help="check a bundle against its checksums and, when signers are given, its signature",
    )
    verify.add_argument("bundle", type=Path, help="bundle directory to check")
    add_signer_options(verify)
    verify.set_defaults(handler=run_release_verify)


def add_signer_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allowed-signers",
        type=Path,
        default=None,
        help="OpenSSH allowed signers file that lists the release keys",
    )
    parser.add_argument("--identity", default=None, help="signer identity expected in that file")


def run_release_check(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)
    fuzzing = workspace.build_dir / FUZZ_DIRECTORY
    gates = evaluate(Qualification(workspace.root, outputs, fuzzing, toolchain.lock))
    for gate in gates:
        sys.stdout.write(format_gate(gate))

    unmet = [gate.name for gate in gates if not gate.met]
    report: dict[str, object] = {
        "version": project_version(workspace.root),
        "profile": profile.name,
        "ready": not unmet,
        "artifacts": artifact_identity(outputs),
        "gates": [asdict(gate) for gate in gates],
    }
    bundle = assemble_bundle(workspace, profile, toolchain, outputs, report)
    if unmet:
        raise CheckError(
            f"{len(unmet)} of {len(gates)} release gates are not met: {', '.join(unmet)}; "
            f"the bundle in {bundle} is marked as not qualified"
        )
    logger.info("every release gate is met; the bundle is in %s", bundle)
    return ExitCode.OK


def run_sign(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    bundle: Path = options.bundle
    rehearsal: bool = options.rehearsal
    require_intact(bundle)
    if not is_qualified(bundle) and not rehearsal:
        raise CheckError(
            f"{bundle} is not qualified; only a bundle that passed release-check is signed"
        )
    signature = sign_bundle(bundle, options.key, workspace.root)
    logger.info("signature written to %s", signature)
    return ExitCode.OK


def run_release_verify(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    bundle: Path = options.bundle
    verify_release(bundle, options.allowed_signers, options.identity)
    qualified = "qualified" if is_qualified(bundle) else "not qualified"
    logger.info("%s is intact and %s", bundle, qualified)
    return ExitCode.OK


def verify_release(bundle: Path, allowed_signers: Path | None, identity: str | None) -> None:
    if (allowed_signers is None) != (identity is None):
        raise CheckError("--allowed-signers and --identity are given together")
    if allowed_signers is not None and identity is not None:
        verify_bundle(bundle, allowed_signers, identity)
    else:
        require_intact(bundle)


def is_qualified(bundle: Path) -> bool:
    try:
        manifest = json.loads((bundle / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CheckError(f"{bundle}: cannot read {MANIFEST_FILE}: {error}") from error
    return isinstance(manifest, dict) and manifest.get("qualified") is True


def format_gate(gate: Gate) -> str:
    return f"{'MET' if gate.met else 'NOT MET'} {gate.name}: {gate.detail}\n"
