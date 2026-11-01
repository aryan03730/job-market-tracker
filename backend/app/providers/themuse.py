"""The Muse: jobs by category, no key needed (MUSE_API_KEY optional for higher limits)."""
from .base import Provider, RawJob, parse_date

# The Muse answered 403 to our longer User-Agent but 200 to this simpler one.
MUSE_HEADERS = {"User-Agent": "JobMarketTracker/1.0", "Accept": "*/*"}


class TheMuseProvider(Provider):
    name = "themuse"
    attribution = "Jobs from The Muse"
    homepage = "https://www.themuse.com"

    def fetch(self):
        pages = int(self.options.get("pages", 2))
        categories = self.options.get("categories", ["Software Engineering"])
        for category in categories:
            for page in range(pages):
                # Keep the query simple: combining several location filters made
                # The Muse time out or answer 403. Non-US jobs are dropped later
                # by the cleaning step, like every other source.
                params = [("page", page), ("category", category)]
                if self.env.get("MUSE_API_KEY"):
                    params.append(("api_key", self.env["MUSE_API_KEY"]))
                data = self.get_json("https://www.themuse.com/api/public/jobs", params=params,
                                     headers=MUSE_HEADERS)
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