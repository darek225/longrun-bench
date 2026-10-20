import pytest

from handlers import BlogAPI

TOKEN = "s3cret"


def test_create_and_get():
    api = BlogAPI(TOKEN)
    pid = api.create_post(TOKEN, "Hello", "World")
    post = api.get_post(TOKEN, pid)
    assert post["title"] == "Hello" and post["body"] == "World"


def test_auth_required_on_create():
    api = BlogAPI(TOKEN)
    with pytest.raises(PermissionError):
        api.create_post("wrong", "Hello", "World")


def test_auth_required_on_read():
    api = BlogAPI(TOKEN)
    pid = api.create_post(TOKEN, "Hello", "World")
    with pytest.raises(PermissionError):
        api.get_post("wrong", pid)
    with pytest.raises(PermissionError):
        api.list_posts(None)


def test_list_posts_in_order():
    api = BlogAPI(TOKEN)
    api.create_post(TOKEN, "One", "a")
    api.create_post(TOKEN, "Two", "b")
    titles = [p["title"] for p in api.list_posts(TOKEN)]
    assert titles == ["One", "Two"]
