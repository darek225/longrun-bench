"""Legacy blog handlers (function style, no auth)."""

POSTS = {}


def create_post(title, body):
    pid = len(POSTS) + 1
    POSTS[pid] = {"id": pid, "title": title, "body": body}
    return pid


def get_post(post_id):
    return POSTS.get(post_id)
