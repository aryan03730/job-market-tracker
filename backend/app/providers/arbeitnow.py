"""Arbeitnow: jobs (mostly Europe), no key. Off by default for a US tracker."""
from .base import Provider, RawJob, parse_date


class ArbeitnowProvider(Provider):
    name = "arbeitnow"
    attribution = "Jobs from Arbeitnow"
    homepage = "https://www.arbeitnow.com"

    def fetch(self):
        for page in range(1, int(self.options.get("pages", 2)) + 1):
            data = self.get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
            rows = data.get("data") or []
            for r in rows:
                yield RawJob(
                    source=self.name,
                    external_id=str(r.get("slug")),
                    title=r.get("title"),
                    company=r.get("company_name"),
                    location=r.get("location"),
                    description=r.get("description"),
                    url=r.get("url"),
                    posted_at=parse_date(r.get("created_at")),
                    is_remote=bool(r.get("remote")),
                )
            if not (data.get("links") or {}).get("next"):
                break
