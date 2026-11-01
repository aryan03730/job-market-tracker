"""Shared pieces every job provider uses: the job shape, HTTP with retries, budgets."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

log = logging.getLogger(__name__)

USER_AGENT = "JobMarketTracker/1.0 (personal portfolio project; github.com/aryan03730)"


@dataclass
class RawJob:
    """A posting as one provider reported it, before cleaning."""
    source: str
    external_id: str
    title: str | None
    company: str | None
    location: str | None
    description: str | None
    url: str | None
    posted_at: datetime | None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_interval: str = "year"        # year | month | week | day | hour
    salary_currency: str | None = "USD"
    salary_text: str | None = None       # free-text salary when no numbers given
    salary_is_predicted: bool = False
    is_remote: bool = False
    keyword: str | None = None
    extra: dict = field(default_factory=dict)


class ProviderError(Exception):
    """The provider failed in a way that should count against its health."""


class BudgetExhausted(Exception):
    """This provider used its daily request budget; stop politely."""


class Provider:
    """Base class. Subclasses set name / required_env and implement fetch()."""

    name: str = "base"
    required_env: tuple[str, ...] = ()
    attribution: str | None = None  # shown on the dashboard
    homepage: str | None = None
    country_scoped: bool = False  # True when the API itself filters by country

    def __init__(self, settings, options: dict, env: dict[str, str], budget_left: int,
                 session: requests.Session | None = None):
        self.settings = settings
        self.options = options
        self.env = env
        self.budget_left = budget_left
        self.requests_made = 0
        self.http = session or requests.Session()
        self.http.headers.setdefault("User-Agent", USER_AGENT)
        self.http.headers.setdefault("Accept", "application/json")

    # ---- availability -------------------------------------------------
    @classmethod
    def missing_env(cls, env: dict[str, str]) -> list[str]:
        return [k for k in cls.required_env if not env.get(k)]

    # ---- HTTP ----------------------------------------------------------
    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
        """GET with retries, exponential backoff + jitter and Retry-After support."""
        if self.budget_left <= 0:
            raise BudgetExhausted(f"{self.name}: daily request budget used")
        retries = max(1, self.settings.retries)
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            self.budget_left -= 1
            self.requests_made += 1
            try:
                resp = self.http.get(url, params=params, headers=headers,
                                     timeout=self.settings.timeout_seconds)
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("%s: network error (try %s/%s): %s", self.name, attempt, retries, exc)
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise ProviderError(f"{self.name}: response was not JSON") from exc
                if resp.status_code in (401, 403):
                    # Bad key or blocked. Retrying will not help.
                    raise ProviderError(f"{self.name}: HTTP {resp.status_code} (check API key / access)")
                if resp.status_code == 404:
                    raise ProviderError(f"{self.name}: HTTP 404 (endpoint moved?) {url}")
                last_exc = ProviderError(f"{self.name}: HTTP {resp.status_code}")
                log.warning("%s: HTTP %s (try %s/%s)", self.name, resp.status_code, attempt, retries)
                if resp.status_code == 429 and resp.headers.get("Retry-After", "").isdigit():
                    wait = min(int(resp.headers["Retry-After"]), 60)
                    self._sleep(wait)
                    continue
            if attempt < retries:
                if self.budget_left <= 0:
                    break
                self._sleep(min(2 ** attempt + random.random(), 30))
        raise ProviderError(str(last_exc) if last_exc else f"{self.name}: request failed")

    def _sleep(self, seconds: float) -> None:  # separated so tests can skip waiting
        time.sleep(seconds)

    # ---- to implement ---------------------------------------------------
    def fetch(self) -> Iterable[RawJob]:
        raise NotImplementedError


# ---- small parsing helpers used by several providers --------------------

def parse_date(value: Any) -> datetime | None:
    """Accept ISO strings, 'YYYY-MM-DD HH:MM:SS', or unix timestamps."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = float(value)
            if ts > 1e12:  # milliseconds
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, OverflowError, OSError):
        return None


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        f = float(str(value).replace(",", ""))
        return f if f > 0 else None
    except ValueError:
        return None
