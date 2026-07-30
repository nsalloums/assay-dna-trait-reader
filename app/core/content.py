"""Static UI content loaded from the curated seed: disclaimers, trait categories,
and the strand-rules summary. Cached; contains no user data."""
from __future__ import annotations

import json
from functools import lru_cache

from .. import config


@lru_cache(maxsize=1)
def _seed() -> dict:
    if not config.SEED_FILE.exists():
        return {}
    return json.loads(config.SEED_FILE.read_text(encoding="utf-8"))


def disclaimers() -> dict:
    return _seed().get("disclaimers", {})


def trait_categories() -> list[dict]:
    return _seed().get("trait_categories", [])


def strand_summary() -> str:
    return _seed().get("strand_rules_summary", "")
