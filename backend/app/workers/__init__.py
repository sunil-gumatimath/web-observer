"""Dramatiq actors package.

Import actor modules so `dramatiq app.workers` discovers them.

Every actor module MUST be imported here. Dramatiq discovers actors by
importing the package named on the command line, so an actor defined in a
module that is only imported lazily (e.g. ``ai_enrich``, imported from inside
the pipeline at send time) is never registered with a broker and no worker will
ever consume its messages — the jobs queue up and silently never run.
"""

from app.workers import (  # noqa: F401
    ai_enrich,
    branding,
    browser_checks,
    checks,
    notifications,
    webhooks,
)

__all__ = [
    "ai_enrich",
    "branding",
    "checks",
    "browser_checks",
    "notifications",
    "webhooks",
]
