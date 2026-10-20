# Mid-task change: authentication required

Product now requires token authentication on every handler. The API class is constructed with a token; every method takes an auth argument and must raise PermissionError when it does not match.
