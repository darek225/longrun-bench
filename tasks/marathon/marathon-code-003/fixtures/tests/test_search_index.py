from search_index import SearchIndex


def _index():
    idx = SearchIndex()
    idx.add("d1", "the quick brown fox jumps")
    idx.add("d2", "the quick blue hare runs quick")
    idx.add("d3", "a slow brown bear sleeps")
    return idx


def test_and_semantics():
    assert _index().search("quick brown") == ["d1"]


def test_ranking_by_frequency():
    assert _index().search("quick") == ["d2", "d1"]


def test_pagination():
    idx = _index()
    assert idx.search("the", limit=1, offset=0) == ["d1"]
    assert idx.search("the", limit=1, offset=1) == ["d2"]


def test_empty_and_unknown():
    idx = _index()
    assert idx.search("") == []
    assert idx.search("zebra") == []
