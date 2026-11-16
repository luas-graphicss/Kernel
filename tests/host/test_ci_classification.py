import os
import subprocess
from pathlib import Path

from kernel_tool.outcome import ExitCode

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "classify-exit.sh"


def classify(status: int, summary: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT), "sh", "-c", f"exit {status}"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "GITHUB_STEP_SUMMARY": str(summary)},
        check=False,
    )


def test_success_adds_no_annotation_and_no_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"

    completed = classify(ExitCode.OK, summary)

    assert completed.returncode == ExitCode.OK
    assert completed.stdout == ""
    assert not summary.exists()


def test_failed_check_keeps_its_status_and_is_labelled(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"

    completed = classify(ExitCode.FAILED, summary)

    assert completed.returncode == ExitCode.FAILED
    assert completed.stdout.startswith("::error title=Check failed::")
    assert summary.read_text().startswith("- Check failed: ")


def test_unavailable_infrastructure_is_labelled_apart_from_failure(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"

    completed = classify(ExitCode.UNAVAILABLE, summary)

    assert completed.returncode == ExitCode.UNAVAILABLE
    assert completed.stdout.startswith("::error title=Infrastructure unavailable::")
    assert summary.read_text().startswith("- Infrastructure unavailable: ")


def test_summary_is_optional_outside_the_workflow(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["sh", str(SCRIPT), "sh", "-c", f"exit {int(ExitCode.UNAVAILABLE)}"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"]},
        cwd=tmp_path,
        check=False,
    )

    assert completed.returncode == ExitCode.UNAVAILABLE
    assert list(tmp_path.iterdir()) == []
