"""Database build + refresh.

``build_seed`` is offline and imports no network client. ``sources`` is the ONLY
module in the entire app that imports an HTTP client; it is reached exclusively
from the explicit, user-initiated ``update_databases`` step — never from the
parse/annotate runtime path.
"""
