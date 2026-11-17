from pathlib import Path

from kernel_tool.build.native import make_variables
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = Path("/cache/tools")
DECLARATION = "REQUIRED_VARIABLES :="
CONTINUATION = "\\"


def build_variables() -> dict[str, str]:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")
    toolchain = Toolchain(
        lock=lock, roots={artifact.name: TOOLS / artifact.root for artifact in lock.artifacts}
    )
    return make_variables(load_profile(REPOSITORY, DEFAULT_PROFILE), toolchain, Path("/build"))


def required_variables() -> set[str]:
    makefile = (REPOSITORY / "Makefile").read_text(encoding="utf-8")
    declaration = makefile.split(DECLARATION, 1)[1].split("$(foreach", 1)[0]
    return set(declaration.replace(CONTINUATION, " ").split())


def test_the_tool_sets_every_variable_the_makefile_requires() -> None:
    assert required_variables() <= set(build_variables())


def test_the_mapped_compiler_directory_is_the_one_the_cross_compiler_runs_from() -> None:
    variables = build_variables()

    assert "COMPILER_DIR" in required_variables()
    assert Path(variables["CROSS_COMPILE"]).parent.parent == Path(variables["COMPILER_DIR"])
