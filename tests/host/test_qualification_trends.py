from kernel_tool.qualification.trends import decline, growth, slowdown


def test_a_counter_that_keeps_rising_is_a_persistent_growth() -> None:
    assert growth([5, 6, 7, 8, 9, 10, 11, 12]).persistent
    assert not growth([5, 9, 5, 9, 5, 9, 5, 9]).persistent
    assert not growth([7, 7, 7, 7, 7, 7]).persistent
    assert not growth([1, 2]).persistent


def test_free_frames_that_keep_falling_are_a_persistent_decline() -> None:
    assert decline([900, 880, 860, 840, 820, 800]).persistent
    assert not decline([900, 880, 900, 880, 900, 880]).persistent


def test_rounds_slow_down_only_beyond_the_tolerated_factor() -> None:
    assert not slowdown([100, 110, 100, 120, 110, 125], 1.5).persistent
    assert slowdown([100, 100, 100, 300, 320, 340], 1.5).persistent
