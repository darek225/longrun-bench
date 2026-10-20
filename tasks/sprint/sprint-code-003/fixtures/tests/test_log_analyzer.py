from log_analyzer import count_level, first_error, summarize


def test_count_level_matches_whole_word():
    lines = ["ERROR disk full", "NOERROR here", "ERRORS galore", "INFO ok"]
    assert count_level(lines, "ERROR") == 1


def test_first_error_returns_first():
    lines = ["INFO start", "ERROR first", "ERROR second"]
    assert first_error(lines) == "ERROR first"


def test_summarize_skips_blank_lines(tmp_path):
    path = tmp_path / "app.log"
    path.write_text("one\n\n\ntwo\n")
    assert summarize(str(path)) == 2
