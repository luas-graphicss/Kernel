from kernel_tool.network.impairment import MILLISECOND, Impairment

DECISIONS = 2000


def fates(policy: dict[str, float], seed: int) -> list[tuple[float, ...]]:
    impairment = Impairment(policy, seed)
    return [impairment.decide().delays for _ in range(DECISIONS)]


def test_a_clean_link_delivers_every_frame_once_and_at_once() -> None:
    assert fates({}, 1) == [(0.0,)] * DECISIONS


def test_the_same_seed_decides_the_same_fates() -> None:
    policy = {"loss": 0.1, "duplicate": 0.1, "reorder": 0.2, "reorder_milliseconds": 20}

    assert fates(policy, 7) == fates(policy, 7)
    assert fates(policy, 7) != fates(policy, 8)


def test_loss_drops_about_the_share_it_names() -> None:
    lost = [delays for delays in fates({"loss": 0.25}, 3) if not delays]

    assert 0.2 * DECISIONS < len(lost) < 0.3 * DECISIONS
    assert Impairment({"loss": 1.0}, 1).decide().is_lost


def test_duplication_delivers_a_frame_twice() -> None:
    decided = fates({"duplicate": 1.0, "reorder_milliseconds": 10}, 5)

    assert all(len(delays) == 2 for delays in decided)
    assert all(delays[0] <= delays[1] <= 10 * MILLISECOND for delays in decided)


def test_reordering_delays_a_frame_behind_the_ones_after_it() -> None:
    decided = fates({"reorder": 0.5, "reorder_milliseconds": 20, "delay_milliseconds": 5}, 9)
    delays = [single[0] for single in decided]

    assert min(delays) == 5 * MILLISECOND
    assert 5 * MILLISECOND < max(delays) <= 25 * MILLISECOND
    assert any(delays[index] > delays[index + 1] for index in range(len(delays) - 1))
