# Spec: audit log with hash chain

Class `AuditLog(path)`. `append(actor, action, details=None)` appends a JSON line containing actor, action, details, prev (the previous entry's hash, or GENESIS for the first), and hash (sha256 of the entry without the hash field, JSON with sorted keys). Returns the new hash. `verify()` replays the chain and returns False on any mismatch. `query(actor=None)` returns parsed entries, optionally filtered by actor.
