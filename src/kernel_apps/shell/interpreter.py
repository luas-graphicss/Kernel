from kernel_apps.shell.commands.table import HANDLERS
from kernel_apps.shell.session import Session
from kernel_apps.shell.words import split_words
from kernel_protocol.errors.codes import UNSUPPORTED, KernelError, error_name

UNKNOWN_COMMAND = "the shell has no such command"


def run_words(session: Session, words: list[str]) -> None:
    handler = HANDLERS.get(words[0])
    if handler is None:
        raise KernelError(UNSUPPORTED, UNKNOWN_COMMAND)
    handler(session, words[1:])


def run_line(session: Session, line: str) -> None:
    name = "none"
    try:
        words = split_words(line)
        if not words:
            return
        name = words[0]
        run_words(session, words)
    except KernelError as error:
        session.failed(error)
        session.write(f"shell: command={name} status=failed error={error_name(error.code)}")
        return
    session.write(f"shell: command={name} status=ok")
