from summarize_log import summarize


def test_pairs():
    assert summarize(["INFO start", "ERROR disk"]) == [("INFO", "start"), ("ERROR", "disk")]


def test_blank_lines_are_skipped():
    assert summarize(["INFO start", "", "ERROR disk"]) == [("INFO", "start"), ("ERROR", "disk")]
