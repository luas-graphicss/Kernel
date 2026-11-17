from kernel_apps.shell.commands.table import HANDLERS
from kernel_apps.shell.session import Session
from kernel_apps.shell.words import split_words
from kernel_protocol.errors.codes import MESSAGE_TOO_LARGE, UNSUPPORTED, KernelError, error_name

UNKNOWN_COMMAND = "the shell has no such command"
NO_COMMAND = "none"


def run_words(session: Session, words: list[str]) -> None:
    handler = HANDLERS.get(words[0])
    if handler is None:
        raise KernelError(UNSUPPORTED, UNKNOWN_COMMAND)
    handler(session, words[1:])


def report_failure(session: Session, name: str, error: KernelError) -> None:
    session.write(f"shell: command={name} status=failed error={error_name(error.code)}")


def run_line(session: Session, line: str) -> None:
    name = NO_COMMAND
    try:
        words = split_words(line)
        if not words:
            return
        name = words[0]
        run_words(session, words)
    except KernelError as error:
        session.failed(error)
        report_failure(session, name, error)
        return
    session.write(f"shell: command={name} status=ok")


def serve_line(session: Session) -> None:
    try:
        line = session.read_line()
    except KernelError as error:
        if error.code != MESSAGE_TOO_LARGE:
            raise
        report_failure(session, NO_COMMAND, error)
        return
    run_line(session, line)
