from corpus import accounting_case, identity_case, scheduling_case, wire_case

REFERENCE_SEED = 0x4B524E4C
REFERENCE_TRANSITIONS = 10000

CASES = (
    ("identity", identity_case.run),
    ("scheduling", scheduling_case.run),
    ("accounting", accounting_case.run),
    ("wire", wire_case.run),
)


def report_line(name: str, seed: int, transitions: int, digest: str) -> str:
    return f"corpus: case={name} seed={seed} transitions={transitions} digest={digest}"


def run_reference() -> list[str]:
    return [
        report_line(
            name, REFERENCE_SEED, REFERENCE_TRANSITIONS, run(REFERENCE_SEED, REFERENCE_TRANSITIONS)
        )
        for name, run in CASES
    ]
