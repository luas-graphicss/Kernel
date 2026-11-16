from pathlib import Path

import pytest

from kernel_protocol.configuration.errors import (
    DEPENDENCY_CYCLE,
    DUPLICATE,
    GATEWAY_OFF_LINK,
    INVALID_ADDRESS,
    MISSING_DEPENDENCY,
    MISSING_KEY,
    MISSING_SECTION,
    MISSING_SERVICE,
    OUT_OF_RANGE,
    PROCESS_BUDGET,
    SELF_DEPENDENCY,
    SYNTAX,
    TOO_LARGE,
    UNKNOWN_DEPENDENCY,
    UNKNOWN_KEY,
    UNKNOWN_RIGHT,
    UNKNOWN_SECTION,
    UNKNOWN_SERVICE,
    UNSUPPORTED_VERSION,
    WRONG_TYPE,
    ConfigurationError,
)
from kernel_protocol.configuration.graph import dependents_of, start_order
from kernel_protocol.configuration.model import (
    CONTROL_ALL,
    FILES_READ_WRITE,
    NETWORK,
    SHELL,
    STORAGE,
)
from kernel_protocol.configuration.syntax import (
    MAX_DOCUMENT_BYTES,
    MAX_ITEMS,
    MAX_KEYS,
    MAX_LINE_BYTES,
    MAX_LINES,
    MAX_SECTIONS,
    parse_document,
)
from kernel_protocol.configuration.validation import Limits, load
from kernel_protocol.services.network import ACCESS_ALL, ACCESS_DELEGATE
from kernel_services.network.ipv4.address import parse_address

REPOSITORY = Path(__file__).resolve().parents[2]
SYSTEM = (REPOSITORY / "config" / "system" / "system.conf").read_text(encoding="utf-8")
VARIANTS = REPOSITORY / "tests" / "guest" / "configurations"
LIMITS = Limits(16)
SECOND = 1_000_000_000


def changed(original: str, replacement: str) -> str:
    assert SYSTEM.count(original) == 1, original
    return SYSTEM.replace(original, replacement)


def rejection(document: str, limits: Limits = LIMITS) -> tuple[str, str]:
    with pytest.raises(ConfigurationError) as raised:
        load(document, limits)
    return raised.value.reason, raised.value.subject


def test_the_system_configuration_of_the_repository_is_accepted() -> None:
    configuration = load(SYSTEM, LIMITS)

    assert configuration.name == "kernel"
    assert set(configuration.order) == {"console", "entropy", "storage", "network", "shell"}
    assert configuration.interface is not None
    assert configuration.interface.address == parse_address("10.0.2.15")
    assert configuration.interface.gateway == parse_address("10.0.2.2")
    assert (configuration.interface.prefix, configuration.interface.mtu) == (24, 1500)
    assert configuration.services[NETWORK].needs == ("entropy",)
    assert configuration.services[NETWORK].restarts == 3
    assert configuration.services[NETWORK].window_nanoseconds == 60 * SECOND
    assert configuration.services[STORAGE].heap_bytes == 2 * 1024 * 1024


def test_services_start_after_the_services_they_need() -> None:
    order = load(SYSTEM, LIMITS).order

    assert order.index("entropy") < order.index(NETWORK)
    assert order.index("console") < order.index(SHELL)
    assert order.index(STORAGE) < order.index(SHELL)


def test_access_policies_grant_what_they_name_and_nothing_else() -> None:
    configuration = load(SYSTEM, LIMITS)

    assert configuration.shell.control == CONTROL_ALL
    assert configuration.shell.files == FILES_READ_WRITE
    assert configuration.shell.network == ACCESS_ALL & ~ACCESS_DELEGATE
    assert configuration.applications.access.control == 0
    assert configuration.applications.limit == 4
    assert configuration.applications.heap_bytes == 2 * 1024 * 1024


def test_a_system_without_a_network_needs_no_interface() -> None:
    without_network = (
        SYSTEM.split("[service.network]")[0]
        + "[service.shell]"
        + SYSTEM.split("[service.shell]")[1]
    )
    without_interface = (
        without_network.split("[interface]")[0]
        + "[service.console]"
        + (without_network.split("[service.console]")[1])
    )

    configuration = load(without_interface, LIMITS)

    assert configuration.interface is None
    assert NETWORK not in configuration.services
    assert rejection(without_network) == (MISSING_SERVICE, NETWORK)


@pytest.mark.parametrize(
    ("name", "reason", "subject"),
    [
        ("circular.conf", DEPENDENCY_CYCLE, "console"),
        ("excessive.conf", OUT_OF_RANGE, "service.network.heap_bytes"),
        ("inconsistent.conf", GATEWAY_OFF_LINK, "interface.gateway"),
    ],
)
def test_the_documents_booted_by_the_supervision_suite_are_rejected(
    name: str, reason: str, subject: str
) -> None:
    document = (VARIANTS / name).read_text(encoding="utf-8")

    assert rejection(document) == (reason, subject)


@pytest.mark.parametrize(
    ("original", "replacement", "reason", "subject"),
    [
        ("version = 1", "version = 2", UNSUPPORTED_VERSION, "system.version"),
        ('name = "kernel"\n', "", MISSING_KEY, "system.name"),
        ('name = "kernel"', 'name = ""', OUT_OF_RANGE, "system.name"),
        ('name = "kernel"', "name = 7", WRONG_TYPE, "system.name"),
        ('name = "kernel"', 'name = "kernel"\ncolor = "blue"', UNKNOWN_KEY, "system.color"),
        ("[system]", "[machine]", UNKNOWN_SECTION, "machine"),
        ("[service.console]", "[service.printer]", UNKNOWN_SERVICE, "printer"),
        ("[service.entropy]", "[service.shell.extra]", UNKNOWN_SERVICE, "shell.extra"),
        ("[access.shell]", "[access.other]", UNKNOWN_SECTION, "access.other"),
        ('address = "10.0.2.15"', 'address = "10.0.2.300"', INVALID_ADDRESS, "interface.address"),
        ('address = "10.0.2.15"', 'address = "10.0.2.255"', INVALID_ADDRESS, "interface.address"),
        ('address = "10.0.2.15"', 'address = "10.0.2"', INVALID_ADDRESS, "interface.address"),
        ('gateway = "10.0.2.2"', 'gateway = "10.0.2.15"', GATEWAY_OFF_LINK, "interface.gateway"),
        ('gateway = "10.0.2.2"', 'gateway = "192.0.2.1"', GATEWAY_OFF_LINK, "interface.gateway"),
        ("prefix = 24", "prefix = 31", OUT_OF_RANGE, "interface.prefix"),
        ("mtu = 1500", "mtu = 9000", OUT_OF_RANGE, "interface.mtu"),
        ("mtu = 1500", "mtu = 575", OUT_OF_RANGE, "interface.mtu"),
        (
            "restarts = 3\nwindow_seconds = 60\nheap_bytes = 4194304",
            "restarts = 17\nwindow_seconds = 60",
            OUT_OF_RANGE,
            "service.network.restarts",
        ),
        (
            "heap_bytes = 4194304",
            "heap_bytes = 4194305",
            OUT_OF_RANGE,
            "service.network.heap_bytes",
        ),
        ("heap_bytes = 4194304", "heap_bytes = 1000", OUT_OF_RANGE, "service.network.heap_bytes"),
        ('needs = ["entropy"]', 'needs = ["entropy", "network"]', SELF_DEPENDENCY, "network"),
        (
            'needs = ["entropy"]',
            'needs = ["entropy", "printer"]',
            UNKNOWN_DEPENDENCY,
            "network.printer",
        ),
        ('needs = ["entropy"]\n', "", MISSING_DEPENDENCY, "network.entropy"),
        (
            'needs = ["entropy"]',
            'needs = ["entropy", "entropy"]',
            OUT_OF_RANGE,
            "service.network.needs",
        ),
        ('needs = ["entropy"]', 'needs = "entropy"', WRONG_TYPE, "service.network.needs"),
        (
            'files = "read-write"\ncontrol',
            'files = "everything"\ncontrol',
            OUT_OF_RANGE,
            "access.shell.files",
        ),
        ('"observe", "launch"', '"observe", "administer"', UNKNOWN_RIGHT, "access.shell.control"),
        ("limit = 4", "limit = 9", OUT_OF_RANGE, "access.application.limit"),
        ("limit = 4", 'limit = 4\ncontrol = ["power"]', UNKNOWN_KEY, "access.application.control"),
    ],
)
def test_an_inconsistent_or_excessive_document_names_what_is_wrong(
    original: str, replacement: str, reason: str, subject: str
) -> None:
    assert rejection(changed(original, replacement)) == (reason, subject)


@pytest.mark.parametrize("section", ["system", "interface", "access.shell", "access.application"])
def test_a_document_without_a_required_section_is_rejected(section: str) -> None:
    header = f"[{section}]"
    start = SYSTEM.index(header)
    following = SYSTEM.find("\n[", start)
    document = SYSTEM[:start] + (SYSTEM[following + 1 :] if following >= 0 else "")

    assert rejection(document) == (MISSING_SECTION, section)


@pytest.mark.parametrize("service", ["console", "entropy", "storage"])
def test_a_document_without_a_required_service_is_rejected(service: str) -> None:
    header = f"[service.{service}]"
    start = SYSTEM.index(header)
    following = SYSTEM.index("\n[", start)
    document = SYSTEM[:start] + SYSTEM[following + 1 :]

    assert rejection(document)[0] in (MISSING_SERVICE, UNKNOWN_DEPENDENCY)


def test_services_and_applications_must_fit_the_process_limit() -> None:
    assert rejection(SYSTEM, Limits(11)) == (PROCESS_BUDGET, "12")
    assert load(SYSTEM, Limits(12)).applications.limit == 4


def test_an_absent_document_is_empty_and_therefore_rejected() -> None:
    assert rejection("") == (MISSING_SECTION, "system")
    assert rejection("# nothing but a comment\n") == (MISSING_SECTION, "system")


@pytest.mark.parametrize(
    ("document", "reason", "subject"),
    [
        ("key = 1\n", SYNTAX, "line-1"),
        ("[system\n", SYNTAX, "line-1"),
        ("[System]\n", SYNTAX, "line-1"),
        ("[system]\nversion 1\n", SYNTAX, "line-2"),
        ("[system]\nVersion = 1\n", SYNTAX, "line-2"),
        ('[system]\nname = "open\n', SYNTAX, "line-2"),
        ('[system]\nname = "a\\"b"\n', SYNTAX, "line-2"),
        ("[system]\nversion = 01\n", SYNTAX, "line-2"),
        ("[system]\nversion = -1\n", SYNTAX, "line-2"),
        ("[system]\nversion = 1.5\n", SYNTAX, "line-2"),
        ("[system]\nversion =\n", SYNTAX, "line-2"),
        ('[system]\nneeds = ["a", 3]\n', SYNTAX, "line-2"),
        ('[system]\nneeds = ["a"\n', SYNTAX, "line-2"),
        ("[system]\nname = \x07\n", SYNTAX, "line-2"),
        ("[system]\nversion = 1\nversion = 1\n", DUPLICATE, "version"),
        ("[system]\n[system]\n", DUPLICATE, "system"),
        ("[system]\nversion = 1234567890123456789\n", TOO_LARGE, "line-2"),
        ("[system]\nname = " + '"' + "x" * 129 + '"\n', TOO_LARGE, "line-2"),
        ("[system]\n# " + "x" * MAX_LINE_BYTES + "\n", TOO_LARGE, "line-2"),
    ],
)
def test_text_that_is_not_a_document_is_rejected_at_its_line(
    document: str, reason: str, subject: str
) -> None:
    with pytest.raises(ConfigurationError) as raised:
        parse_document(document)

    assert (raised.value.reason, raised.value.subject) == (reason, subject)


def test_a_document_is_bounded_in_bytes_lines_sections_keys_and_items() -> None:
    sections = "".join(f"[s{index}]\n" for index in range(MAX_SECTIONS + 1))
    keys = "[system]\n" + "".join(f"k{index} = 1\n" for index in range(MAX_KEYS + 1))
    items = "[system]\nneeds = [" + ", ".join(['"x"'] * (MAX_ITEMS + 1)) + "]\n"

    for document, subject in (
        ("#" * (MAX_DOCUMENT_BYTES + 1), "document"),
        ("\n" * MAX_LINES, "lines"),
        (sections, f"line-{MAX_SECTIONS + 1}"),
        (keys, f"line-{MAX_KEYS + 2}"),
        (items, "line-2"),
    ):
        with pytest.raises(ConfigurationError) as raised:
            parse_document(document)
        assert (raised.value.reason, raised.value.subject) == (TOO_LARGE, subject)


def test_values_are_data_and_never_evaluated() -> None:
    document = parse_document(
        "[system]\nname = \"__import__('os').system('halt')\"\nflag = true\nlist = []\n"
    )

    assert document["system"] == {
        "name": "__import__('os').system('halt')",
        "flag": True,
        "list": [],
    }


def test_a_start_order_exists_only_without_cycles() -> None:
    needs = {"a": ("b",), "b": ("c",), "c": (), "d": ("a", "c")}

    assert start_order(needs) == ("c", "b", "a", "d")
    with pytest.raises(ConfigurationError) as raised:
        start_order({"a": ("b",), "b": ("c",), "c": ("a",), "d": ()})
    assert (raised.value.reason, raised.value.subject) == (DEPENDENCY_CYCLE, "a")


def test_dependents_include_the_services_that_need_a_dependent() -> None:
    needs = {"base": (), "middle": ("base",), "top": ("middle",), "other": ()}

    assert set(dependents_of("base", needs)) == {"middle", "top"}
    assert dependents_of("top", needs) == ()
    assert dependents_of("other", needs) == ()
