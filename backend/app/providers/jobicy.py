"""Jobicy: remote jobs, no key. Credit Jobicy and link to the original posting."""
from .base import Provider, RawJob, parse_date, to_float


class JobicyProvider(Provider):
    name = "jobicy"
    attribution = "Remote jobs from Jobicy"
    homepage = "https://jobicy.com"

    def fetch(self):
        geo = "usa" if (self.settings.country or "").lower() == "us" else None
        for keyword in self.settings.keywords:
            params = {"count": int(self.options.get("count", 50)), "tag": keyword[:50]}
            if geo:
                params["geo"] = geo
            data = self.get_json("https://jobicy.com/api/v2/remote-jobs", params=params)
            for r in data.get("jobs") or []:
                yield RawJob(
                    source=self.name,
                    external_id=str(r.get("id")),
                    title=r.get("jobTitle"),
                    company=r.get("companyName"),
                    location=r.get("jobGeo") or "Remote",
                    description=r.get("jobDescription") or r.get("jobExcerpt"),
                    url=r.get("url"),
                    posted_at=parse_date(r.get("pubDate")),
                    salary_min=to_float(r.get("annualSalaryMin") or r.get("salaryMin")),
                    salary_max=to_float(r.get("annualSalaryMax") or r.get("salaryMax")),
                    salary_currency=r.get("salaryCurrency") or "USD",
                    salary_interval=_period(r.get("salaryPeriod")),
                    is_remote=True,
                    keyword=keyword,
                )


def _period(p):
    p = (p or "year").lower()
    return {"yearly": "year", "annual": "year", "monthly": "month", "hourly": "hour",
            "weekly": "week", "daily": "day"}.get(p, p if p in ("year", "month", "hour", "week", "day") else "year")
