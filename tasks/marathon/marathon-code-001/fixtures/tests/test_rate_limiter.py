from rate_limiter import SlidingWindowLimiter


def test_allows_up_to_limit():
    lim = SlidingWindowLimiter(3, 60)
    assert [lim.allow("k", now=1000.0 + i) for i in range(3)] == [True, True, True]


def test_blocks_beyond_limit():
    lim = SlidingWindowLimiter(2, 60)
    assert lim.allow("k", now=0.0) is True
    assert lim.allow("k", now=1.0) is True
    assert lim.allow("k", now=2.0) is False


def test_window_expiry_frees_slots():
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("k", now=0.0) is True
    assert lim.allow("k", now=30.0) is False
    assert lim.allow("k", now=61.0) is True


def test_keys_are_isolated():
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("a", now=0.0) is True
    assert lim.allow("b", now=0.0) is True
    assert lim.allow("a", now=1.0) is False


def test_remaining_counts_down():
    lim = SlidingWindowLimiter(3, 60)
    assert lim.remaining("k", now=0.0) == 3
    lim.allow("k", now=0.0)
    assert lim.remaining("k", now=1.0) == 2
