from kernel_apps.shell.commands import files, network, power, programs
from kernel_apps.shell.session import Session

COMMANDS = (
    ("help", "help", "list the commands"),
    ("run", "run <path> [arguments]", "start a program from the volume as an application"),
    ("ps", "ps", "list the services and the applications"),
    ("kill", "kill <application>", "end an application"),
    ("wait", "wait <application> [seconds]", "wait for an application and report its status"),
    ("mem", "mem", "report memory and kernel object counters"),
    ("ls", "ls [path]", "list a directory"),
    ("cat", "cat <path>", "print a file"),
    ("mkdir", "mkdir <path>", "create a directory"),
    ("write", "write <path> <text>", "replace a file with one line of text"),
    ("rm", "rm <path>", "remove a file or an empty directory"),
    ("sync", "sync", "make the writable volumes durable"),
    ("net", "net [counters|neighbors]", "report the network interface"),
    ("ping", "ping <address> [count]", "send echo requests to a station"),
    ("shutdown", "shutdown [restart]", "stop the system in order and power off or restart"),
)


def show_help(session: Session, arguments: list[str]) -> None:
    for _name, usage, summary in COMMANDS:
        session.write(f"help: {usage} - {summary}")


HANDLERS = {
    "help": show_help,
    "run": programs.run,
    "ps": programs.list_processes,
    "kill": programs.kill,
    "wait": programs.wait,
    "mem": programs.memory,
    "ls": files.list_directory,
    "cat": files.print_file,
    "mkdir": files.make_directory,
    "write": files.write_file,
    "rm": files.remove,
    "sync": files.sync,
    "net": network.describe,
    "ping": network.ping,
    "shutdown": power.shutdown,
}
