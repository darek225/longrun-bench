from log_summary import summarize


def test_counts_by_level():
    out = summarize(["INFO start", "ERROR disk full", "INFO done", "ERROR disk full", ""])
    assert out["total"] == 4
    assert out["by_level"] == {"INFO": 2, "ERROR": 2}


def test_top_errors_ranked():
    lines = ["ERROR a", "ERROR b", "ERROR a", "ERROR c", "ERROR a", "ERROR b"]
    out = summarize(lines)
    assert out["top_errors"][0] == ("a", 3)
    assert out["top_errors"][1] == ("b", 2)


def test_empty_input():
    assert summarize([]) == {"total": 0, "by_level": {}, "top_errors": []}
