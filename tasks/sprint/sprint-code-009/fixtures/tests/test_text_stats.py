from text_stats import stats


def test_basic():
    out = stats("a bb ccc")
    assert out["words"] == 3 and out["longest"] == "ccc"


def test_empty_text():
    out = stats("")
    assert out == {"words": 0, "longest": "", "avg_len": 0.0}
