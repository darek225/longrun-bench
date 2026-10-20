# Spec: full-text search index

Class `SearchIndex` with `add(doc_id, text)` and `search(query, limit=10, offset=0)`. Tokenize on lowercase alphanumeric runs. Search uses AND semantics across query terms, ranks by total term frequency (ties broken by doc_id ascending), and returns doc_ids sliced by offset/limit. Empty queries and unknown terms return an empty list.
