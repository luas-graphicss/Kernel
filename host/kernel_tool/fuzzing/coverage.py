import sys
from types import CodeType

TOOL_ID = 3
TOOL_NAME = "kernel-tool-fuzzing"


class LineCoverage:
    def __init__(self, watched_prefix: str) -> None:
        self._watched_prefix = watched_prefix
        self._fresh = 0
        self.lines = 0

    def start(self) -> None:
        monitoring = sys.monitoring
        monitoring.use_tool_id(TOOL_ID, TOOL_NAME)
        monitoring.register_callback(TOOL_ID, monitoring.events.LINE, self._line_runs)
        monitoring.set_events(TOOL_ID, monitoring.events.LINE)
        monitoring.restart_events()

    def stop(self) -> None:
        monitoring = sys.monitoring
        monitoring.set_events(TOOL_ID, monitoring.events.NO_EVENTS)
        monitoring.register_callback(TOOL_ID, monitoring.events.LINE, None)
        monitoring.free_tool_id(TOOL_ID)

    def take_fresh(self) -> int:
        fresh = self._fresh
        self._fresh = 0
        return fresh

    def _line_runs(self, code: CodeType, _line: int) -> object:
        if code.co_filename.startswith(self._watched_prefix):
            self._fresh += 1
            self.lines += 1
        return sys.monitoring.DISABLE
