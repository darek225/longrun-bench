from team_app import accept_invite, create_team, init_db, invite_member, list_members


def _setup(tmp_path):
    conn = init_db(str(tmp_path / "app.db"))
    team = create_team(conn, "Core")
    return conn, team


def test_invite_and_accept(tmp_path):
    conn, team = _setup(tmp_path)
    token = invite_member(conn, team, "a@example.com")
    assert list_members(conn, team, status="active") == []
    assert accept_invite(conn, token) is True
    assert list_members(conn, team, status="active") == ["a@example.com"]


def test_accept_unknown_token_fails(tmp_path):
    conn, team = _setup(tmp_path)
    assert accept_invite(conn, "deadbeef") is False


def test_double_accept_fails(tmp_path):
    conn, team = _setup(tmp_path)
    token = invite_member(conn, team, "a@example.com")
    assert accept_invite(conn, token) is True
    assert accept_invite(conn, token) is False


def test_teams_are_isolated(tmp_path):
    conn, team = _setup(tmp_path)
    other = create_team(conn, "Other")
    invite_member(conn, team, "a@example.com")
    assert list_members(conn, other) == []
