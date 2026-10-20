import json

from csv2json import convert


def test_basic_rows():
    out = json.loads(convert("name,age\nalice,30\nbob,25\n"))
    assert out == [{"name": "alice", "age": "30"}, {"name": "bob", "age": "25"}]


def test_quoted_commas():
    out = json.loads(convert('name,note\nalice,"hi, there"\n'))
    assert out == [{"name": "alice", "note": "hi, there"}]


def test_empty_input():
    assert json.loads(convert("")) == []
