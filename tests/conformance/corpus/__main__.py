import sys

from corpus.runner import run_reference


def main() -> int:
    sys.stdout.write("".join(f"{line}\n" for line in run_reference()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
