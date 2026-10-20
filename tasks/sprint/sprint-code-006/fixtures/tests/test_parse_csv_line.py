from parse_csv_line import parse_line


def test_simple():
    assert parse_line("a,b,c") == ["a", "b", "c"]


def test_quoted_comma():
    assert parse_line('a,"b,c",d') == ["a", "b,c", "d"]
