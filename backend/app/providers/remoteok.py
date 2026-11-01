"""Remote OK: remote jobs, no key. Their terms require a link back and credit."""
from .base import Provider, RawJob, parse_date, to_float


class RemoteOKProvider(Provider):
    name = "remoteok"
    attribution = "Remote jobs from Remote OK"
    homepage = "https://remoteok.com"

    def fetch(self):
        data = self.get_json("https://remoteok.com/api")
        if not isinstance(data, list):
            return
        for r in data:
            if not isinstance(r, dict) or "legal" in r or not r.get("id"):
                continue  # first element is a legal notice
            yield RawJob(
                source=self.name,
                external_id=str(r.get("id")),
                title=r.get("position"),
                company=r.get("company"),
                location=r.get("location") or "Remote",
                description=r.get("description"),
                url=r.get("url") or r.get("apply_url"),
                posted_at=parse_date(r.get("date") or r.get("epoch")),
                salary_min=to_float(r.get("salary_min")),
                salary_max=to_float(r.get("salary_max")),
                is_remote=True,
                extra={"tags": r.get("tags") or []},
            )
