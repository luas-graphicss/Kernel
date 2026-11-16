import sys
from types import ModuleType

import pytest

from doubles.native_process import NativeProcess
from doubles.native_supervisor import NativeSupervisor

SUPERVISOR_MODULE = ModuleType("_supervisor")
PROCESS_MODULE = ModuleType("_process")
sys.modules.setdefault("_supervisor", SUPERVISOR_MODULE)
sys.modules.setdefault("_process", PROCESS_MODULE)


def bind(monkeypatch: pytest.MonkeyPatch, module: ModuleType, double, calls: tuple[str, ...]):
    for name in calls:
        monkeypatch.setattr(module, name, getattr(double, name), raising=False)
    return double


@pytest.fixture
def native_supervisor(monkeypatch: pytest.MonkeyPatch) -> NativeSupervisor:
    return bind(monkeypatch, SUPERVISOR_MODULE, NativeSupervisor(), NativeSupervisor.CALLS)


@pytest.fixture
def native_process(monkeypatch: pytest.MonkeyPatch) -> NativeProcess:
    return bind(monkeypatch, PROCESS_MODULE, NativeProcess(), NativeProcess.CALLS)
