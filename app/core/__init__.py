"""Core on-device logic: parsing, strand normalization, sessions, annotation join.

None of these modules import an HTTP client. The parse/annotate runtime path is
therefore structurally incapable of network egress (see the privacy tests).
"""
