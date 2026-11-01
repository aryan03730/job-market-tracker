from datetime import datetime

import pytest

from app.pipeline.clean import (clean_job, fingerprint, normalize_location, normalize_salary,
                                parse_salary_text, strip_html)
from app.pipeline.skills import SkillMatcher
from app.providers.base import RawJob, parse_date


def raw(**kw):
    base = dict(source="test", external_id="1", title="Software Engineer", company="Acme Inc.",
                location="San Diego, CA", description="<p>Python &amp; SQL</p>",
                url="https://example.com/1", posted_at=datetime(2026, 10, 30))
    base.update(kw)
    return RawJob(**base)


@pytest.mark.parametrize("text,expected", [
    ("San Diego, CA", ("San Diego, CA", "CA", False, True)),
    ("Austin, Texas", ("Austin, TX", "TX", False, True)),
    ("Austin, TX 78701", ("Austin, TX 78701", "TX", False, True)),
    ("USA", ("Remote (US)", None, True, True)),
    ("Worldwide", ("Remote (Anywhere)", None, True, True)),
    ("Europe", ("Remote (Europe)", None, True, False)),
    ("", ("Remote (US)", None, True, True)),
])
def test_normalize_location(text, expected):
    is_remote = text in ("USA", "Worldwide", "Europe", "")
    assert normalize_location(text, is_remote) == expected


@pytest.mark.parametrize("text,lo,hi,interval", [
    ("$90k - $120k", 90000, 120000, "year"),
    ("$95,000 - $130,000 per year", 95000, 130000, "year"),
    ("$45/hr", 45, 45, "hour"),
    ("competitive", None, None, "year"),
])
def test_parse_salary_text(text, lo, hi, interval):
    a, b, i, _ = parse_salary_text(text)
    assert (a, b, i) == (lo, hi, interval)


def test_salary_annualizes_and_validates():
    assert normalize_salary(raw(salary_min=50, salary_max=60, salary_interval="hour"), 15000, 10**6) == (104000, 124800)
    assert normalize_salary(raw(salary_text="€60k - €80k"), 15000, 10**6) == (None, None)
    assert normalize_salary(raw(salary_min=10), 15000, 10**6) == (None, None)        # nonsense
    assert normalize_salary(raw(salary_min=150000, salary_max=120000), 15000, 10**6) == (120000, 150000)


def test_fingerprint_matches_across_sources():
    assert fingerprint("Software Engineer (Remote)", "Acme, Inc.") == fingerprint("software engineer", "ACME")
    assert fingerprint("Software Engineer", "Acme", "CA") != fingerprint("Software Engineer", "Acme", "TX")


def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>world</b></p><br>ok") == "Hello world ok"


def test_clean_job_skips_bad_rows(settings):
    assert clean_job(raw(title="  "), settings, True, False) == (None, "no_title")
    assert clean_job(raw(url=None), settings, True, False) == (None, "no_url")
    assert clean_job(raw(location="Germany", is_remote=True), settings, True, False) == (None, "not_us")
    # A country-scoped provider (Adzuna US) is trusted even with an odd location string.
    job, _ = clean_job(raw(location="Somewhere County"), settings, True, True)
    assert job is not None


def test_clean_job_happy_path(settings):
    job, reason = clean_job(raw(), settings, True, False)
    assert reason is None
    assert job.description == "Python & SQL"
    assert job.state == "CA" and job.company == "Acme Inc."


def test_future_dates_are_clamped(settings):
    job, _ = clean_job(raw(posted_at=datetime(2999, 1, 1)), settings, True, False)
    assert job.posted_at.year < 2999


def test_parse_date_formats():
    assert parse_date("2026-10-30T12:00:00Z") == datetime(2026, 10, 30, 12)
    assert parse_date("2026-10-30 12:00:00") == datetime(2026, 10, 30, 12)
    assert parse_date(1793361600).year == 2026
    assert parse_date("garbage") is None


def test_skill_matcher(settings):
    m = SkillMatcher(settings.skills)
    found = m.find("Senior Java Engineer", "Spring Boot, AWS, Kubernetes, PostgreSQL, CI/CD")
    assert {"Java", "Spring", "AWS", "Kubernetes", "PostgreSQL", "CI/CD", "SQL"} - {"SQL"} <= found
    assert "JavaScript" not in m.find("Java developer")
    assert "Java" not in m.find("JavaScript developer")
    assert "C++" in m.find("Strong C++ skills") and "C#" in m.find("C# and .NET")


def test_bad_skill_pattern_is_ignored():
    m = SkillMatcher({"Good": r"\bgood\b", "Broken": r"(unclosed"})
    assert m.find("good stuff") == {"Good"}
