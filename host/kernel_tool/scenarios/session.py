from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from kernel_tool.qemu.dialogue import Exchange, run_dialogue
from kernel_tool.qemu.session import SessionResult, run_session
from kernel_tool.scenarios.model import Scenario, Step
from kernel_tool.scenarios.networking import AttachedNetwork, NetworkEvidence, attached_network

ENCODING = "utf-8"

type CommandBuilder = Callable[[tuple[str, ...]], list[str]]


@dataclass(frozen=True, slots=True)
class Boot:
    session: SessionResult
    failures: tuple[str, ...]
    network: NetworkEvidence | None


def hold_session(
    scenario: Scenario,
    build_command: CommandBuilder,
    deadline: float,
    station_directory: Path,
    capture: Path,
) -> Boot:
    with attached_network(scenario.network, station_directory, capture) as station:
        command = build_command(station.arguments if station is not None else ())
        session, unanswered = _converse(scenario, command, deadline, station)
        failures = [f"the guest never reported {pattern!r}" for pattern in unanswered]
        evidence = None
        if station is not None:
            unreported, evidence = station.finish()
            failures.extend(unreported)
    return Boot(session, tuple(failures), evidence)


def _converse(
    scenario: Scenario, command: list[str], deadline: float, station: AttachedNetwork | None
) -> tuple[SessionResult, tuple[str, ...]]:
    if not scenario.steps:
        typed = scenario.serial_input.encode(ENCODING) if scenario.serial_input else None
        return run_session(command, deadline, typed), ()
    exchanges = tuple(
        Exchange(step.awaited, step.typed, _action(step, station)) for step in scenario.steps
    )
    dialogue = run_dialogue(command, deadline, exchanges)
    return dialogue.session, dialogue.unanswered


def _action(step: Step, station: AttachedNetwork | None) -> Callable[[], None] | None:
    if station is None or not step.orders:
        return None
    return partial(station.obey, step.orders)
