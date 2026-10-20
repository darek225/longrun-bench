"""Compute simple text statistics."""


def stats(text):
    words = text.split()
    longest = max(words, key=len)
    return {'words': len(words), 'longest': longest, 'avg_len': sum(len(w) for w in words) / len(words)}
