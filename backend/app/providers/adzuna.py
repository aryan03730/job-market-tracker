"""Adzuna: large US aggregator. Free key at developer.adzuna.com (about 1,000 calls/month)."""
from .base import Provider, RawJob, parse_date, to_float


class AdzunaProvider(Provider):
    name = "adzuna"
    required_env = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
    attribution = "Jobs by Adzuna"
    country_scoped = True  # results are already limited to the US
    homepage = "https://www.adzuna.com"

    def fetch(self):
        country = self.settings.country or "us"
        per_page = int(self.options.get("results_per_page", 50))
        pages = int(self.options.get("pages_per_keyword", 1))
        for keyword in self.settings.keywords:
            for page in range(1, pages + 1):
                params = {
                    "app_id": self.env["ADZUNA_APP_ID"],
                    "app_key": self.env["ADZUNA_APP_KEY"],
                    "what": keyword,
                    "results_per_page": per_page,
                    "max_days_old": self.settings.max_days_old,
                    "sort_by": "date",
                }
                if self.settings.location:
                    params["where"] = self.settings.location
                data = self.get_json(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params=params
                )
                results = data.get("results") or []
                for r in results:
                    loc = r.get("location") or {}
                    area = loc.get("area") or []   # e.g. ["US", "California", "San Diego County", "San Diego"]
                    location = loc.get("display_name")
                    if len(area) >= 2:
                        location = f"{area[-1]}, {area[1]}" if len(area) >= 3 else area[1]
                    yield RawJob(
                        source=self.name,
                        external_id=str(r.get("id")),
                        title=r.get("title"),
                        company=(r.get("company") or {}).get("display_name"),
                        location=location,
                        description=r.get("description"),
                        url=r.get("redirect_url"),   # Adzuna's terms require this link
                        posted_at=parse_date(r.get("created")),
                        salary_min=to_float(r.get("salary_min")),
                        salary_max=to_float(r.get("salary_max")),
                        salary_is_predicted=str(r.get("salary_is_predicted")) == "1",
                        keyword=keyword,
                    )
                if len(results) < per_page:
                    break
