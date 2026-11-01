"""USAJOBS: official US federal jobs. Free key at developer.usajobs.gov."""
from .base import Provider, RawJob, parse_date, to_float

_INTERVALS = {"PA": "year", "PH": "hour", "PM": "month", "PW": "week", "PD": "day", "BW": "biweek"}


class USAJobsProvider(Provider):
    name = "usajobs"
    required_env = ("USAJOBS_API_KEY", "USAJOBS_EMAIL")
    attribution = "Federal jobs from USAJOBS"
    country_scoped = True  # results are already limited to the US
    homepage = "https://www.usajobs.gov"

    def fetch(self):
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": self.env["USAJOBS_EMAIL"],
            "Authorization-Key": self.env["USAJOBS_API_KEY"],
        }
        for keyword in self.settings.keywords:
            params = {
                "Keyword": keyword,
                "ResultsPerPage": int(self.options.get("results_per_page", 100)),
                "DatePosted": self.settings.max_days_old,
            }
            if self.settings.location:
                params["LocationName"] = self.settings.location
            data = self.get_json("https://data.usajobs.gov/api/search", params=params, headers=headers)
            items = ((data.get("SearchResult") or {}).get("SearchResultItems")) or []
            for item in items:
                d = item.get("MatchedObjectDescriptor") or {}
                pay = (d.get("PositionRemuneration") or [{}])[0] or {}
                interval = _INTERVALS.get(pay.get("RateIntervalCode"), "year")
                lo, hi = to_float(pay.get("MinimumRange")), to_float(pay.get("MaximumRange"))
                summary = (((d.get("UserArea") or {}).get("Details")) or {}).get("JobSummary")
                yield RawJob(
                    source=self.name,
                    external_id=str(item.get("MatchedObjectId") or d.get("PositionID")),
                    title=d.get("PositionTitle"),
                    company=d.get("OrganizationName") or d.get("DepartmentName"),
                    location=d.get("PositionLocationDisplay"),
                    description=summary or d.get("QualificationSummary"),
                    url=d.get("PositionURI"),
                    posted_at=parse_date(d.get("PublicationStartDate")),
                    salary_min=lo, salary_max=hi, salary_interval=interval,
                    keyword=keyword,
                )
