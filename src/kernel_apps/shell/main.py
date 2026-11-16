from kernel_apps.shell.interpreter import run_line
from kernel_apps.shell.session import Session
from kernel_client import services
from kernel_client.control import Control
from kernel_client.processes import Startup
from kernel_protocol.services.lifecycle import OPERATION_REGISTER

REGISTRATION = 0
CONTROL = 1
PROMPT = b"kernel> "


def main() -> bool:
    startup = Startup()
    session = Session(Control(startup.handles[CONTROL]))
    services.note(startup.handles[REGISTRATION], OPERATION_REGISTER)
    session.write("shell: ready")
    while True:
        session.write_bytes(PROMPT)
        run_line(session, session.read_line())
