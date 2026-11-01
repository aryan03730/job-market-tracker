"""Remotive: remote jobs, no key. Asks for <= 4 requests/day and a link back."""
from .base import Provider, RawJob, parse_date


class RemotiveProvider(Provider):
    name = "remotive"
    attribution = "Remote jobs from Remotive"
    homepage = "https://remotive.com"

    def fetch(self):
        # One request for the whole software-dev feed, filtered locally:
        # far kinder to their 4-requests-a-day rule than one call per keyword.
        data = self.get_json(
            "https://remotive.com/api/remote-jobs",
            params={"category": "software-dev", "limit": int(self.options.get("limit", 300))},
        )
        for r in data.get("jobs") or []:
            yield RawJob(
                source=self.name,
                external_id=str(r.get("id")),
                title=r.get("title"),
                company=r.get("company_name"),
                location=r.get("candidate_required_location") or "Remote",
                description=r.get("description"),
                url=r.get("url"),
                posted_at=parse_date(r.get("publication_date")),
                salary_text=r.get("salary") or None,
                is_remote=True,
                extra={"tags": r.get("tags") or []},
            )
