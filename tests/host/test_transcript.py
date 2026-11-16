import pytest

from kernel_tool.verification.transcript import KernelStatus, read_transcript

FIRMWARE_BANNER = "OpenSBI v1.5.1\nBoot HART ID              : 0\n"


def test_firmware_output_is_not_part_of_the_kernel_transcript() -> None:
    transcript = read_transcript(FIRMWARE_BANNER + "boot: hart=0\nkernel: status=ok\n")

    assert transcript.lines == ("boot: hart=0", "kernel: status=ok")
    assert transcript.status is KernelStatus.OK


def test_failed_boot_is_reported() -> None:
    serial = (
        FIRMWARE_BANNER + "boot: rejected=memory reason=insufficient-ram\nkernel: status=failed\n"
    )

    assert read_transcript(serial).status is KernelStatus.FAILED


@pytest.mark.parametrize(
    ("kernel_output", "status"),
    [
        ("", KernelStatus.MISSING),
        ("boot: hart=0\n", KernelStatus.MISSING),
        ("boot: hart=0\nkernel: status=ok\ninit: still running\n", KernelStatus.AMBIGUOUS),
        ("boot: hart=0\nkernel: status=ok\nkernel: status=failed\n", KernelStatus.AMBIGUOUS),
        ("boot: hart=0\nkernel: status=maybe\n", KernelStatus.AMBIGUOUS),
    ],
    ids=["no-kernel-output", "no-status", "output-after-status", "two-statuses", "unknown-value"],
)
def test_only_a_single_final_status_line_counts(kernel_output: str, status: KernelStatus) -> None:
    assert read_transcript(FIRMWARE_BANNER + kernel_output).status is status


def test_carriage_returns_and_blank_lines_are_ignored() -> None:
    transcript = read_transcript("boot: hart=0\r\n\r\nkernel: status=ok\r\n")

    assert transcript.lines == ("boot: hart=0", "kernel: status=ok")
