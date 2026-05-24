"""Versioned prompt templates for LLLM.

Templates are stored as ``.md`` files alongside this module so they're
diffable in code review.  ``load_template(name, version)`` returns the
raw string; the orchestrator does the substitution.

Adding a new template version is intentionally an additive change —
``site_health_v1.md`` stays in the repo when ``site_health_v2.md``
arrives, so an audit row written against v1 can still be reproduced
later.
"""

from __future__ import annotations

import functools
from importlib import resources


@functools.lru_cache(maxsize=32)
def load_template(name: str, version: str = "v1") -> str:
    """Return the markdown text of ``{name}_{version}.md`` in this package.

    Cached because templates do not change at runtime; reloading them
    on every request would waste IO without buying anything.
    """
    filename = f"{name}_{version}.md"
    pkg = resources.files(__package__)
    return pkg.joinpath(filename).read_text(encoding="utf-8")


def template_version(name: str) -> str:
    """Canonical version string an audit row records.  Phase 1: v1."""
    return f"{name}_v1"
