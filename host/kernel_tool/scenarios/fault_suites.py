from dataclasses import replace

from kernel_tool.scenarios.guest_program import case_lines, tests_image_scenario
from kernel_tool.scenarios.guest_suites import CASES, VOLUME_REPORT, with_data
from kernel_tool.scenarios.model import (
    DataAttachment,
    DataCheck,
    DataSource,
    Devices,
    Scenario,
)

DEVICE_RESET = "device-reset"
STORAGE_CRASH = "storage-crash"
JOURNAL_TRANSACTIONS = 7
RESET_CASES = CASES[DEVICE_RESET]
DEVICE_FAILED = r"^device: slot=\d+ state=failed reason=device-needs-reset$"

STALLED_DEVICE = replace(
    tests_image_scenario(
        "stalled-device",
        "suites.device_reset.main",
        (
            *case_lines(DEVICE_RESET, RESET_CASES[:-1]),
            DEVICE_FAILED,
            *case_lines(DEVICE_RESET, RESET_CASES[-1:]),
        ),
    ),
    devices=Devices(stalled=True),
)

FLUSH_TRACE = replace(
    tests_image_scenario(
        "flush-trace", "suites.storage.journal", (VOLUME_REPORT,) * JOURNAL_TRANSACTIONS
    ),
    devices=with_data(DataSource.FORMATTED, DataAttachment.TRACED, DataCheck.REPORTED),
)

FAULT_SUITES: dict[str, tuple[Scenario, ...]] = {
    DEVICE_RESET: (STALLED_DEVICE,),
    STORAGE_CRASH: (FLUSH_TRACE,),
}
