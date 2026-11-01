"""Himalayas: remote jobs, no key."""
from .base import Provider, RawJob, parse_date, to_float


class HimalayasProvider(Provider):
    name = "himalayas"
    attribution = "Remote jobs from Himalayas"
    homepage = "https://himalayas.app"

    def fetch(self):
        limit = 20  # the public endpoint caps page size
        for page in range(int(self.options.get("pages", 5))):
            data = self.get_json("https://himalayas.app/jobs/api",
                                 params={"limit": limit, "offset": page * limit})
            jobs = data.get("jobs") or []
            for r in jobs:
                restrictions = r.get("locationRestrictions") or []
                names = [x.get("name") if isinstance(x, dict) else str(x) for x in restrictions]
                yield RawJob(
                    source=self.name,
                    external_id=str(r.get("guid") or r.get("applicationLink") or r.get("title")),
                    title=r.get("title"),
                    company=r.get("companyName"),
                    location=", ".join(n for n in names if n) or "Remote",
                    description=r.get("description") or r.get("excerpt"),
                    url=r.get("applicationLink") or r.get("guid"),
                    posted_at=parse_date(r.get("pubDate")),
                    salary_min=to_float(r.get("minSalary")),
                    salary_max=to_float(r.get("maxSalary")),
                    salary_currency=r.get("currency") or "USD",
                    is_remote=True,
                )
            if len(jobs) < limit:
                break
