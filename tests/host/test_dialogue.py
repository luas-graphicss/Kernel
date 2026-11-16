import sys

from kernel_tool.qemu.dialogue import Conversation, Exchange, run_dialogue

GUEST = """
import sys
print("guest: ready", flush=True)
for line in sys.stdin:
    word = line.strip()
    if word == "stop":
        break
    print(f"guest: heard={word}", flush=True)
print("kernel: status=ok", flush=True)
"""


def awaited(*patterns: str) -> tuple[Exchange, ...]:
    return tuple(Exchange(pattern) for pattern in patterns)


def test_exchanges_are_answered_in_order_as_their_lines_are_heard() -> None:
    conversation = Conversation(awaited(r"^first$", r"^second$"))

    assert conversation.hear(b"second\n") == []
    assert [exchange.awaited for exchange in conversation.hear(b"first\n")] == [r"^first$"]
    assert conversation.unanswered == (r"^second$",)
    assert [exchange.awaited for exchange in conversation.hear(b"second\n")] == [r"^second$"]
    assert conversation.unanswered == ()


def test_one_chunk_may_answer_several_exchanges() -> None:
    conversation = Conversation(awaited(r"^one$", r"^two$", r"^three$"))

    assert len(conversation.hear(b"one\ntwo\n")) == 2
    assert conversation.unanswered == (r"^three$",)


def test_the_same_pattern_twice_needs_two_occurrences() -> None:
    conversation = Conversation(awaited(r"status=ok$", r"status=ok$"))

    assert len(conversation.hear(b"shell: command=run status=ok\n")) == 1
    assert len(conversation.hear(b"kernel> ")) == 0
    assert len(conversation.hear(b"shell: command=wait status=ok\n")) == 1


def test_carriage_returns_and_split_characters_do_not_hide_a_line() -> None:
    conversation = Conversation(awaited(r"^caf\u00e9: ready$"))
    encoded = "caf\u00e9: ready\r\n".encode()

    assert conversation.hear(encoded[:4]) == []
    assert len(conversation.hear(encoded[4:])) == 1
    assert conversation.transcript == "caf\u00e9: ready\n"


def test_a_pattern_may_match_text_after_a_prompt() -> None:
    conversation = Conversation(awaited(r"shell: command=ls status=ok$"))

    assert len(conversation.hear(b"kernel> shell: command=ls status=ok\n")) == 1


def test_a_dialogue_types_its_answers_and_runs_their_actions() -> None:
    done: list[str] = []
    exchanges = (
        Exchange(r"^guest: ready$", "alpha\n"),
        Exchange(r"^guest: heard=alpha$", "beta\n", lambda: done.append("noted")),
        Exchange(r"^guest: heard=beta$", "stop\n"),
    )

    result = run_dialogue([sys.executable, "-c", GUEST], 30.0, exchanges)

    assert result.unanswered == ()
    assert result.session.exit_code == 0
    assert done == ["noted"]
    assert result.session.transcript.splitlines() == [
        "guest: ready",
        "guest: heard=alpha",
        "guest: heard=beta",
        "kernel: status=ok",
    ]


def test_a_guest_that_never_says_what_is_awaited_runs_into_the_deadline() -> None:
    exchanges = (Exchange(r"^guest: ready$"), Exchange(r"^never printed$", "stop\n"))

    result = run_dialogue([sys.executable, "-c", GUEST], 1.0, exchanges)

    assert result.unanswered == (r"^never printed$",)
    assert result.session.timed_out
