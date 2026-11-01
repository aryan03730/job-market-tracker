"""Turns messy provider data into one clean shape.

Every function here is pure (no network, no database) so it is easy to test.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime

from ..db import utcnow
from ..providers.base import RawJob

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
STATE_BY_NAME = {v.lower(): k for k, v in US_STATES.items()}

_US_TOKENS = re.compile(r"\b(usa|u\.s\.a?\.?|us|united states|america|americas|north america)\b", re.I)
_ANYWHERE = re.compile(r"\b(worldwide|anywhere|global|international)\b", re.I)
_REMOTE = re.compile(r"\b(remote|work from home|wfh|telework|flexible)\b", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

SALARY_MULTIPLIER = {"year": 1, "month": 12, "biweek": 26, "week": 52, "day": 260, "hour": 2080}


@dataclass
class CleanJob:
    source: str
    external_id: str
    fingerprint: str
    title: str
    company: str | None
    location: str
    state: str | None
    is_remote: bool
    salary_min: float | None
    salary_max: float | None
    salary_is_predicted: bool
    description: str
    url: str
    keyword: str | None
    posted_at: datetime


# ---------------------------------------------------------------- text

def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h\d)\s*/?>", " ", text)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", html.unescape(text)).strip()


def clean_text(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    value = _WS.sub(" ", html.unescape(str(value))).strip()
    return value[:limit] or None


_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|gmbh|plc)\b\.?", re.I)
_TITLE_NOISE = re.compile(r"\((remote|hybrid|on-?site|us|usa)[^)]*\)|\b(remote|hybrid)\b", re.I)


def fingerprint(title: str, company: str | None, state: str | None = None) -> str:
    """Same job from two sources -> same fingerprint, so it is stored once.
    The state is included so one company's identical title in two states stays two jobs."""
    t = _TITLE_NOISE.sub(" ", title.lower())
    c = _COMPANY_SUFFIX.sub(" ", (company or "").lower())
    norm = lambda s: re.sub(r"[^a-z0-9+#]+", " ", s).strip()  # noqa: E731
    key = f"{norm(t)}|{norm(c)}|{(state or '').upper()}"
    return hashlib.sha1(key.encode()).hexdigest()


# ---------------------------------------------------------------- location

def normalize_location(raw: str | None, is_remote: bool) -> tuple[str, str | None, bool, bool]:
    """Returns (display, state_code, is_remote, looks_us_eligible)."""
    text = clean_text(raw, 200) or ""
    remote = is_remote or bool(_REMOTE.search(text))
    state = None

    # "San Diego, CA" / "Austin, TX 78701" / "Austin, Texas"
    for part in reversed([p.strip() for p in re.split(r"[,;/|]", text) if p.strip()]):
        token = re.sub(r"\s+\d{5}(-\d{4})?$", "", part).strip()
        if token.upper() in US_STATES and (len(token) == 2):
            state = token.upper()
            break
        if token.lower() in STATE_BY_NAME:
            state = STATE_BY_NAME[token.lower()]
            break

    us_ok = bool(state) or bool(_US_TOKENS.search(text)) or bool(_ANYWHERE.search(text))
    if not text or text.lower() in ("remote", "flexible / remote"):
        us_ok = True

    if remote and not state:
        if _US_TOKENS.search(text) or not text or text.lower() in ("remote", "flexible / remote"):
            display = "Remote (US)"
        elif _ANYWHERE.search(text):
            display = "Remote (Anywhere)"
        else:
            display = f"Remote ({text})"[:200]
    else:
        display = text or "Unknown"
        if state and re.fullmatch(r"[A-Za-z .'-]+,\s*[A-Za-z ]+", display):
            city = display.split(",")[0].strip()
            display = f"{city}, {state}"
    return display, state, remote, us_ok


# ---------------------------------------------------------------- salary

_MONEY = re.compile(r"(\d{1,3}(?:[,\s]\d{3})+|\d+(?:\.\d+)?)\s*(k|K)?")


def parse_salary_text(text: str | None) -> tuple[float | None, float | None, str, str | None]:
    """'$90k - $120k' -> (90000, 120000, 'year', 'USD'). Returns Nones when unclear."""
    if not text:
        return None, None, "year", None
    t = text.strip()
    currency = "USD"
    if re.search(r"€|eur\b", t, re.I):
        currency = "EUR"
    elif re.search(r"£|gbp\b", t, re.I):
        currency = "GBP"
    elif re.search(r"\b(cad|aud|inr|₹)\b", t, re.I):
        currency = "OTHER"
    interval = "year"
    if re.search(r"/\s*h(ou)?r|per hour|hourly|an hour", t, re.I):
        interval = "hour"
    elif re.search(r"/\s*mo|per month|monthly", t, re.I):
        interval = "month"
    nums = []
    for m in _MONEY.finditer(t):
        val = float(re.sub(r"[,\s]", "", m.group(1)))
        if m.group(2):
            val *= 1000
        nums.append(val)
    nums = [n for n in nums if n >= 7]  # drop stray small numbers ("2 weeks"); bounds check later
    if not nums:
        return None, None, interval, currency
    return min(nums[:2]), max(nums[:2]), interval, currency


def normalize_salary(job: RawJob, lo_valid: int, hi_valid: int) -> tuple[float | None, float | None]:
    lo, hi, interval, currency = job.salary_min, job.salary_max, job.salary_interval, job.salary_currency
    if lo is None and hi is None and job.salary_text:
        lo, hi, interval, currency = parse_salary_text(job.salary_text)
    if currency and currency.upper() != "USD":
        return None, None
    mult = SALARY_MULTIPLIER.get(interval or "year", 1)
    lo = lo * mult if lo else None
    hi = hi * mult if hi else None
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    lo = lo or hi
    hi = hi or lo
    if lo is None or not (lo_valid <= lo <= hi_valid) or not (lo_valid <= hi <= hi_valid):
        return None, None
    return round(lo, -2), round(hi, -2)


# ---------------------------------------------------------------- main entry

def clean_job(job: RawJob, settings, us_only: bool, country_scoped: bool) -> tuple[CleanJob | None, str | None]:
    """Returns (clean_job, None) or (None, reason_skipped)."""
    title = clean_text(strip_html(job.title), 300)
    if not title:
        return None, "no_title"
    url = (job.url or "").strip()
    if not url.startswith("http"):
        return None, "no_url"
    if not job.external_id or job.external_id == "None":
        return None, "no_id"

    display, state, remote, us_ok = normalize_location(job.location, job.is_remote)
    if us_only and not country_scoped and not us_ok:
        return None, "not_us"

    lo, hi = normalize_salary(job, settings.salary_min_valid, settings.salary_max_valid)
    company = clean_text(strip_html(job.company), 200)
    now = utcnow()
    posted = job.posted_at if job.posted_at and job.posted_at <= now else now

    return CleanJob(
        source=job.source,
        external_id=str(job.external_id)[:128],
        fingerprint=fingerprint(title, company, state),
        title=title,
        company=company,
        location=display,
        state=state,
        is_remote=remote,
        salary_min=lo,
        salary_max=hi,
        salary_is_predicted=job.salary_is_predicted and lo is not None,
        description=strip_html(job.description)[: settings.max_description_chars],
        url=url[:1000],
        keyword=(job.keyword or None) and job.keyword[:100],
        posted_at=posted,
    ), None
