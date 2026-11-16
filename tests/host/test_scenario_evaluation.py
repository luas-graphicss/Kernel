from kernel_tool.scenarios.evaluation import check_corpus, check_repeats, check_transcript
from kernel_tool.scenarios.model import BootModule, Image, Scenario
from kernel_tool.verification.transcript import KernelStatus, read_transcript

SCENARIO = Scenario(
    name="sample",
    image=Image.KERNEL,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.OK,
    expected_lines=(r"^boot: hart=0$", r"^policy: admitted=init$", r"^user: exit status=0$"),
    forbidden_lines=(r"^panic: ",),
)
PASSING = (
    "boot: hart=0\npolicy: admitted=init\ninit: hello\nuser: exit status=0\nkernel: status=ok\n"
)


def failures(serial_output: str) -> list[str]:
    return check_transcript(SCENARIO, read_transcript(serial_output))


def test_transcript_with_every_line_in_order_passes() -> None:
    assert failures(PASSING) == []


def test_firmware_output_before_the_kernel_is_ignored() -> None:
    assert failures("OpenSBI v1.5.1\npanic: firmware banner\n" + PASSING) == []


def test_wrong_final_status_is_a_failure() -> None:
    reported = failures(PASSING.replace("status=ok", "status=failed"))

    assert reported == ["kernel status is failed, expected ok"]


def test_missing_status_is_a_failure() -> None:
    assert failures(PASSING.replace("kernel: status=ok\n", "")) == [
        "kernel status is missing, expected ok"
    ]


def test_expected_lines_must_appear_in_order() -> None:
    swapped = "boot: hart=0\nuser: exit status=0\npolicy: admitted=init\nkernel: status=ok\n"

    assert failures(swapped) == [r"no line from position 3 matches '^user: exit status=0$'"]


def test_a_missing_line_does_not_hide_later_ones() -> None:
    reported = failures("boot: hart=0\nuser: exit status=0\nkernel: status=ok\n")

    assert reported == [r"no line from position 1 matches '^policy: admitted=init$'"]


def test_forbidden_line_is_a_failure() -> None:
    reported = failures(PASSING.replace("init: hello", "panic: reason=boom"))

    assert reported == ["line 'panic: reason=boom' matches the forbidden pattern '^panic: '"]


def test_repeated_boots_must_agree() -> None:
    first = ("boot: hart=0", "kernel: status=ok")

    assert check_repeats([first, first, first]) == []
    assert check_repeats([first]) == []
    assert check_repeats([first, ("boot: hart=1", "kernel: status=ok")]) != []


def test_guest_corpus_must_match_the_reference() -> None:
    reference = ("corpus: case=identity digest=aa", "corpus: case=wire digest=bb")
    lines = ("boot: hart=0", *reference, "kernel: status=ok")

    assert check_corpus(lines, reference) == []
    assert check_corpus(lines[:2], reference) != []
    assert check_corpus(lines, (reference[0], "corpus: case=wire digest=cc")) != []
    assert check_corpus(("boot: hart=0",), ()) == []
