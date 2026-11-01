"""Offline stand-in for requests.Session that answers like each real provider.

Used by `python -m scripts.refresh --demo` and by tests, so nothing ever calls a
live job API. Payload shapes mirror each provider's documented JSON.
"""
from __future__ import annotations

import random
import zlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

TITLES = [
    "Software Engineer", "Backend Developer (Python)", "Senior Software Engineer",
    "Full Stack Developer", "Data Engineer", "Frontend Engineer - React",
    "Software Engineer I", "Junior Python Developer", "Platform Engineer",
    "Machine Learning Engineer", "DevOps Engineer", "Software Development Engineer",
    "API Developer", "Cloud Engineer", "Site Reliability Engineer", "Java Developer",
]
COMPANIES = [
    "Northwind Labs", "Bluefin Health", "Cobalt Analytics", "Pinecrest Software",
    "Harbor Logistics", "Lumen Fintech", "Redwood Robotics", "Summit Insurance",
    "Atlas Retail", "Quarry Data", "Meridian Bank", "Orbit Media", "Tidepool AI",
    "Granite Security", "Cedar Education", "Vantage Energy",
]
CITIES = [
    ("San Diego", "California", "CA"), ("Austin", "Texas", "TX"), ("Seattle", "Washington", "WA"),
    ("New York", "New York", "NY"), ("Denver", "Colorado", "CO"), ("Chicago", "Illinois", "IL"),
    ("San Francisco", "California", "CA"), ("Boston", "Massachusetts", "MA"),
    ("Atlanta", "Georgia", "GA"), ("Raleigh", "North Carolina", "NC"),
]
SKILL_SNIPPETS = [
    "Python", "SQL", "PostgreSQL", "AWS", "Docker", "Kubernetes", "React", "TypeScript",
    "JavaScript", "Java", "Spring Boot", "Go (golang)", "Flask", "Django", "REST APIs",
    "GraphQL", "Git", "Linux", "Terraform", "Kafka", "Redis", "Node.js", "Azure", "GCP",
    "CI/CD", "machine learning", "Spark", "C#/.NET", "MongoDB", "Rust",
]
WEIGHTS = [30, 26, 14, 20, 16, 10, 15, 12, 14, 9, 6, 5, 6, 5, 12, 4, 15, 9, 6, 4, 5, 8, 7, 5, 10, 6, 4, 5, 4, 2]


def _rng(key: str) -> random.Random:
    return random.Random(f"demo-{key}")


def _desc(r: random.Random, html: bool = True) -> str:
    skills = set(r.choices(SKILL_SNIPPETS, weights=WEIGHTS, k=r.randint(3, 7)))
    body = (f"We are hiring an engineer to build and run production services. "
            f"You will work with {', '.join(sorted(skills))}. "
            "Collaborate with product and design, write tests, and review code.")
    return f"<p>{body}</p><ul><li>Health benefits</li><li>401k match</li></ul>" if html else body


def _when(r: random.Random, days: int = 28) -> datetime:
    now = datetime.now(timezone.utc)
    # More recent days get more postings, like a real feed.
    return now - timedelta(days=min(days, int(r.expovariate(1 / 7))), hours=r.randint(0, 23))


def _salary(r: random.Random, chance: float = 0.6):
    if r.random() > chance:
        return None, None
    lo = r.randrange(70, 170) * 1000
    return lo, lo + r.randrange(15, 60) * 1000


def _jobs(key: str, n: int):
    r = _rng(key)
    for i in range(n):
        yield r, i, r.choice(TITLES), r.choice(COMPANIES), r.choice(CITIES)


def adzuna(params):
    out = []
    for r, i, t, c, (city, state, _) in _jobs(f"adzuna-{params.get('what')}", 25):
        lo, hi = _salary(r, 0.8)
        out.append({
            "id": str(zlib.crc32(f"{params.get('what')}-{i}".encode())), "title": t,
            "company": {"display_name": c},
            "location": {"display_name": f"{city}, {state}", "area": ["US", state, f"{city} County", city]},
            "description": _desc(r, False)[:300] + "…", "redirect_url": f"https://www.adzuna.com/details/{i}",
            "created": _when(r).strftime("%Y-%m-%dT%H:%M:%SZ"), "salary_min": lo, "salary_max": hi,
            "salary_is_predicted": "1" if lo and r.random() < 0.3 else "0",
        })
    return {"count": len(out), "results": out}


def usajobs(params):
    items = []
    for r, i, t, c, (city, state, code) in _jobs(f"usajobs-{params.get('Keyword')}", 6):
        lo, hi = _salary(r, 1.0)
        items.append({"MatchedObjectId": f"{700000 + i}-{params.get('Keyword', '')[:3]}", "MatchedObjectDescriptor": {
            "PositionTitle": f"IT Specialist ({t})", "OrganizationName": "Department of Example Affairs",
            "PositionLocationDisplay": f"{city}, {state}", "PositionURI": f"https://www.usajobs.gov/job/{700000 + i}",
            "PublicationStartDate": _when(r).strftime("%Y-%m-%dT%H:%M:%S.%f0"),
            "PositionRemuneration": [{"MinimumRange": str(lo), "MaximumRange": str(hi), "RateIntervalCode": "PA"}],
            "UserArea": {"Details": {"JobSummary": _desc(r, False)}},
        }})
    return {"SearchResult": {"SearchResultCount": len(items), "SearchResultItems": items}}


def remotive(_params):
    jobs = []
    for r, i, t, c, _ in _jobs("remotive", 40):
        lo, hi = _salary(r, 0.4)
        jobs.append({
            "id": 2000000 + i, "url": f"https://remotive.com/remote-jobs/software-dev/job-{i}",
            "title": t, "company_name": c, "category": "Software Development",
            "publication_date": _when(r).strftime("%Y-%m-%dT%H:%M:%S"),
            "candidate_required_location": r.choice(["USA", "Worldwide", "Americas", "Europe", "US Only"]),
            "salary": f"${lo // 1000}k - ${hi // 1000}k" if lo else "", "description": _desc(r),
        })
    return {"job-count": len(jobs), "jobs": jobs}


def jobicy(params):
    jobs = []
    for r, i, t, c, _ in _jobs(f"jobicy-{params.get('tag')}", 8):
        lo, hi = _salary(r, 0.5)
        jobs.append({
            "id": 90000 + i * 7 + len(params.get("tag", "")), "url": f"https://jobicy.com/jobs/{i}",
            "jobTitle": t, "companyName": c, "jobGeo": "USA", "jobDescription": _desc(r),
            "pubDate": _when(r).strftime("%Y-%m-%d %H:%M:%S"),
            "annualSalaryMin": lo, "annualSalaryMax": hi, "salaryCurrency": "USD",
        })
    return {"jobCount": len(jobs), "jobs": jobs}


def themuse(params):
    page = int(params.get("page", 0))
    results = []
    for r, i, t, c, (city, state, code) in _jobs(f"muse-{params.get('category')}-{page}", 20):
        loc = r.choice([f"{city}, {code}", "Flexible / Remote"])
        results.append({
            "id": 15000000 + page * 100 + i + len(params.get("category", "")) * 1000, "name": t,
            "contents": _desc(r), "publication_date": _when(r).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "locations": [{"name": loc}], "company": {"name": c},
            "refs": {"landing_page": f"https://www.themuse.com/jobs/{i}"},
        })
    return {"page": page, "page_count": 2, "results": results}


def remoteok(_params):
    out = [{"legal": "API terms: link back to Remote OK and mention it as the source."}]
    for r, i, t, c, _ in _jobs("remoteok", 30):
        lo, hi = _salary(r, 0.5)
        out.append({
            "id": str(1090000 + i), "position": t, "company": c,
            "location": r.choice(["United States", "Worldwide", "", "Remote, US", "Germany"]),
            "date": _when(r).strftime("%Y-%m-%dT%H:%M:%S+00:00"), "description": _desc(r),
            "url": f"https://remoteok.com/remote-jobs/{1090000 + i}", "salary_min": lo or 0, "salary_max": hi or 0,
        })
    return out


def himalayas(params):
    offset = int(params.get("offset", 0))
    jobs = []
    for r, i, t, c, _ in _jobs(f"himalayas-{offset}", 20 if offset < 60 else 7):
        lo, hi = _salary(r, 0.5)
        jobs.append({
            "title": t, "companyName": c, "description": _desc(r),
            "guid": f"https://himalayas.app/companies/x/jobs/{offset + i}",
            "applicationLink": f"https://himalayas.app/companies/x/jobs/{offset + i}",
            "pubDate": int(_when(r).timestamp()), "minSalary": lo, "maxSalary": hi, "currency": "USD",
            "locationRestrictions": r.choice([["United States"], [], ["Canada", "United States"], ["United Kingdom"]]),
        })
    return {"jobs": jobs, "offset": offset, "limit": 20, "totalCount": 67}


def arbeitnow(params):
    return {"data": [], "links": {"next": None}}


ROUTES = {
    "api.adzuna.com": adzuna, "data.usajobs.gov": usajobs, "remotive.com": remotive,
    "jobicy.com": jobicy, "www.themuse.com": themuse, "remoteok.com": remoteok,
    "himalayas.app": himalayas, "www.arbeitnow.com": arbeitnow,
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.headers = payload, status, {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers: dict = {}

    def get(self, url, params=None, headers=None, timeout=None):
        host = urlparse(url).netloc
        if isinstance(params, list):
            params = dict(params)
        handler = ROUTES.get(host)
        if handler is None:
            return FakeResponse({"error": "unknown host"}, 404)
        return FakeResponse(handler(params or {}))


def demo_env() -> dict:
    return {"ADZUNA_APP_ID": "demo", "ADZUNA_APP_KEY": "demo",
            "USAJOBS_API_KEY": "demo", "USAJOBS_EMAIL": "demo@example.com"}
