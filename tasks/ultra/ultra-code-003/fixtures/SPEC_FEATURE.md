# Spec: migrate the blog API

Migrate legacy_app.py (in the workspace) to a class-based layout in handlers.py: class `BlogAPI(token)` with methods create_post(auth, title, body) returning an id, get_post(auth, post_id) returning the post dict or None, and list_posts(auth) returning posts in id order. Behavior must match the legacy semantics. CHANGE.md in the workspace adds a requirement that applies to every method.
