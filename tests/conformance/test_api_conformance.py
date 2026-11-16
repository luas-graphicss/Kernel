import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from kernel_apps.shell.commands.table import COMMANDS
from kernel_protocol.syscalls import numbers
from kernel_tool.commands.test import SUITES
from kernel_tool.scenarios.fault_suites import FAULT_SUITES
from kernel_tool.scenarios.model import Scenario

REPOSITORY = Path(__file__).resolve().parents[2]
MATRIX = REPOSITORY / "docs" / "architecture" / "api-conformance.md"
SECTION = re.compile(r"^## .*`(?P<source>[\w.]+)`$")
SEPARATOR = re.compile(r"^\|(?: -+ \|)+$")
QUOTED = re.compile(r"`([^`]+)`")
REFERENCE = re.compile(r"^(?P<suite>[a-z-]+)/(?P<scenario>[a-z-]+)(?:/(?P<case>[a-z-]+))?$")
EVIDENCE_COLUMN = "Evidência"
OPERATION_PREFIX = "OPERATION_"
SYSTEM_CALLS = "kernel_protocol.syscalls.numbers"
SHELL_COMMANDS = "kernel_apps.shell.commands.table"
SERVICES = (
    "kernel_protocol.services.lifecycle",
    "kernel_protocol.services.console",
    "kernel_protocol.services.entropy",
    "kernel_protocol.services.block",
    "kernel_protocol.services.files",
    "kernel_protocol.services.network",
    "kernel_protocol.services.control",
)
EVERY_SUITE = {**SUITES, **FAULT_SUITES}


@dataclass(frozen=True, slots=True)
class Row:
    source: str
    name: str
    evidence: tuple[str, ...]


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def subject(cell: str) -> str:
    quoted = QUOTED.search(cell)
    return quoted.group(1) if quoted else cell


def matrix_rows() -> list[Row]:
    rows: list[Row] = []
    source = ""
    in_table = False
    cites_evidence = False
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = SECTION.match(line)
            source = heading["source"] if heading else ""
        if not line.startswith("|"):
            in_table = False
            continue
        columns = cells(line)
        if not in_table:
            in_table = True
            cites_evidence = columns[-1] == EVIDENCE_COLUMN
        elif cites_evidence and not SEPARATOR.match(line):
            rows.append(Row(source, subject(columns[0]), tuple(QUOTED.findall(columns[-1]))))
    return rows


ROWS = matrix_rows()


def names_under(source: str) -> list[str]:
    return sorted(row.name for row in ROWS if row.source == source)


def operations(service: ModuleType) -> list[str]:
    return sorted(
        name.removeprefix(OPERATION_PREFIX)
        for name in vars(service)
        if name.startswith(OPERATION_PREFIX)
    )


def cited_scenario(citation: str) -> tuple[Scenario, str | None] | None:
    reference = REFERENCE.match(citation)
    if reference is None:
        return None
    for scenario in EVERY_SUITE.get(reference["suite"], ()):
        if scenario.name == reference["scenario"]:
            return scenario, reference["case"]
    return None


def exists(citation: str) -> bool:
    cited = cited_scenario(citation)
    if cited is None:
        return REFERENCE.match(citation) is None and (REPOSITORY / citation).is_file()
    scenario, case = cited
    return case is None or any(f" case={case} " in line for line in scenario.expected_lines)


def types(citation: str, command: str) -> bool:
    cited = cited_scenario(citation)
    return cited is not None and any(step.typed.split()[:1] == [command] for step in cited[0].steps)


def test_every_system_call_has_exactly_one_row() -> None:
    calls = sorted(
        name.lower()
        for name, value in vars(numbers).items()
        if name.isupper() and isinstance(value, int) and value < numbers.COUNT
    )

    assert names_under(SYSTEM_CALLS) == calls


@pytest.mark.parametrize("service", SERVICES)
def test_every_service_operation_has_exactly_one_row(service: str) -> None:
    assert names_under(service) == operations(importlib.import_module(service))


def test_every_shell_command_has_exactly_one_row() -> None:
    assert names_under(SHELL_COMMANDS) == sorted(name for name, _usage, _summary in COMMANDS)


def test_every_row_cites_evidence() -> None:
    assert ROWS
    assert not [row.name for row in ROWS if not row.evidence]


def test_every_citation_names_a_scenario_a_case_or_a_file_that_exists() -> None:
    assert not [
        (row.name, citation) for row in ROWS for citation in row.evidence if not exists(citation)
    ]


def test_every_shell_command_is_typed_by_a_scenario_it_cites() -> None:
    assert not [
        row.name
        for row in ROWS
        if row.source == SHELL_COMMANDS
        and not any(types(citation, row.name) for citation in row.evidence)
    ]
