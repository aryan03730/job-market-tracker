"""Finds named skills in a posting's title + description using patterns from tracker.toml."""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


class SkillMatcher:
    def __init__(self, patterns: dict[str, str]):
        self.compiled: dict[str, re.Pattern] = {}
        for skill, pattern in patterns.items():
            try:
                self.compiled[skill] = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                # A typo in the config should not take the whole refresh down.
                log.error("Skipping skill %r: bad pattern %r (%s)", skill, pattern, exc)

    def find(self, *texts: str | None) -> set[str]:
        blob = " ".join(t for t in texts if t)
        return {skill for skill, rx in self.compiled.items() if rx.search(blob)}
