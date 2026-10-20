# Spec: sliding-window rate limiter

Class `SlidingWindowLimiter(limit, window_seconds)` with `allow(key, now=None)` and `remaining(key, now=None)`. `allow` records the event when allowed. Events older than the window stop counting. Keys are independent. `now` is injectable for tests (epoch seconds); default to the current time.
