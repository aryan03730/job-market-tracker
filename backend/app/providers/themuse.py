"""The Muse: jobs by category, no key needed (MUSE_API_KEY optional for higher limits)."""
from .base import Provider, RawJob, parse_date


class TheMuseProvider(Provider):
    name = "themuse"
    attribution = "Jobs from The Muse"
    homepage = "https://www.themuse.com"

    def fetch(self):
        pages = int(self.options.get("pages", 2))
        categories = self.options.get("categories", ["Software Engineering"])
        for category in categories:
            for page in range(pages):
                params = [("page", page), ("category", category), ("descending", "true")]
                if (self.settings.country or "").lower() == "us":
                    params.append(("location", "Flexible / Remote"))
                    params.append(("location", self.settings.location or "United States"))
                if self.env.get("MUSE_API_KEY"):
                    params.append(("api_key", self.env["MUSE_API_KEY"]))
                data = self.get_json("https://www.themuse.com/api/public/jobs", params=params)
                results = data.get("results") or []
                for r in results:
                    locs = [l.get("name") for l in (r.get("locations") or []) if l.get("name")]
                    yield RawJob(
                        source=self.name,
                        external_id=str(r.get("id")),
                        title=r.get("name"),
                        company=(r.get("company") or {}).get("name"),
                        location="; ".join(locs) or None,
                        description=r.get("contents"),
                        url=(r.get("refs") or {}).get("landing_page"),
                        posted_at=parse_date(r.get("publication_date")),
                        is_remote=any("remote" in l.lower() for l in locs),
                        keyword=category,
                    )
                if page + 1 >= int(data.get("page_count") or 0):
                    break
