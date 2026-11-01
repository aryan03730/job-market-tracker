"""Each adapter is tested against a mocked copy of the real endpoint. No live calls."""
import pytest
import responses

from app.providers import REGISTRY, BudgetExhausted, ProviderError


def make(name, settings, env=None, budget=50, **opts):
    cls = REGISTRY[name]
    options = {**settings.provider(name), **opts}
    return cls(settings, options, env or {}, budget)


@responses.activate
def test_adzuna(settings):
    responses.get("https://api.adzuna.com/v1/api/jobs/us/search/1", json={"results": [{
        "id": "42", "title": "Python Developer", "company": {"display_name": "Acme"},
        "location": {"display_name": "San Diego", "area": ["US", "California", "San Diego County", "San Diego"]},
        "description": "Python", "redirect_url": "https://adzuna/42", "created": "2026-10-30T10:00:00Z",
        "salary_min": 100000, "salary_max": 120000, "salary_is_predicted": "1"}]})
    jobs = list(make("adzuna", settings, {"ADZUNA_APP_ID": "a", "ADZUNA_APP_KEY": "b"}).fetch())
    assert len(jobs) == 2  # one per keyword
    j = jobs[0]
    assert (j.title, j.company, j.location, j.salary_is_predicted) == ("Python Developer", "Acme", "San Diego, California", True)
    assert "app_key=b" in responses.calls[0].request.url and "what=software+engineer" in responses.calls[0].request.url


@responses.activate
def test_usajobs_sends_required_headers(settings):
    responses.get("https://data.usajobs.gov/api/search", json={"SearchResult": {"SearchResultItems": [{
        "MatchedObjectId": "9", "MatchedObjectDescriptor": {
            "PositionTitle": "IT Specialist", "OrganizationName": "NASA", "PositionLocationDisplay": "Houston, Texas",
            "PositionURI": "https://usajobs/9", "PublicationStartDate": "2026-10-29T00:00:00.0000",
            "PositionRemuneration": [{"MinimumRange": "80000", "MaximumRange": "100000", "RateIntervalCode": "PA"}]}}]}})
    jobs = list(make("usajobs", settings, {"USAJOBS_API_KEY": "k", "USAJOBS_EMAIL": "me@x.com"}).fetch())
    assert jobs[0].company == "NASA" and jobs[0].salary_max == 100000
    h = responses.calls[0].request.headers
    assert h["Authorization-Key"] == "k" and h["User-Agent"] == "me@x.com"


@responses.activate
def test_remotive_single_request(settings):
    responses.get("https://remotive.com/api/remote-jobs", json={"jobs": [{
        "id": 1, "url": "https://remotive/1", "title": "Backend Engineer", "company_name": "R",
        "publication_date": "2026-10-30T00:00:00", "candidate_required_location": "USA",
        "salary": "$100k - $130k", "description": "<p>Go</p>"}]})
    jobs = list(make("remotive", settings).fetch())
    assert len(responses.calls) == 1 and jobs[0].salary_text == "$100k - $130k" and jobs[0].is_remote


@responses.activate
def test_remoteok_skips_legal_notice(settings):
    responses.get("https://remoteok.com/api", json=[{"legal": "terms"}, {
        "id": "5", "position": "SRE", "company": "Z", "url": "https://remoteok/5",
        "date": "2026-10-30T00:00:00+00:00", "salary_min": 0, "salary_max": 0}])
    jobs = list(make("remoteok", settings).fetch())
    assert [j.title for j in jobs] == ["SRE"] and jobs[0].salary_min is None


@responses.activate
def test_jobicy_themuse_himalayas_shapes(settings):
    responses.get("https://jobicy.com/api/v2/remote-jobs", json={"jobs": [{
        "id": 3, "url": "https://jobicy/3", "jobTitle": "Dev", "companyName": "J", "jobGeo": "USA",
        "pubDate": "2026-10-30 10:00:00", "annualSalaryMin": 90000, "annualSalaryMax": 110000}]})
    responses.get("https://www.themuse.com/api/public/jobs", json={"page_count": 1, "results": [{
        "id": 7, "name": "Engineer", "contents": "x", "publication_date": "2026-10-30T00:00:00Z",
        "locations": [{"name": "Flexible / Remote"}], "company": {"name": "M"}, "refs": {"landing_page": "https://muse/7"}}]})
    responses.get("https://himalayas.app/jobs/api", json={"jobs": [{
        "title": "H Dev", "companyName": "H", "guid": "https://h/1", "applicationLink": "https://h/1",
        "pubDate": 1793361600, "locationRestrictions": ["United States"]}]})
    assert list(make("jobicy", settings).fetch())[0].salary_min == 90000
    muse = list(make("themuse", settings, categories=["Software Engineering"]).fetch())
    assert muse[0].is_remote and muse[0].url == "https://muse/7"
    assert list(make("himalayas", settings).fetch())[0].location == "United States"


@responses.activate
def test_retries_then_succeeds(settings):
    responses.get("https://remoteok.com/api", status=503)
    responses.get("https://remoteok.com/api", json=[{"id": "1", "position": "A", "url": "https://r/1"}])
    p = make("remoteok", settings)
    assert len(list(p.fetch())) == 1 and p.requests_made == 2


@responses.activate
def test_auth_error_is_not_retried(settings):
    responses.get("https://remoteok.com/api", status=401)
    p = make("remoteok", settings)
    with pytest.raises(ProviderError, match="401"):
        list(p.fetch())
    assert p.requests_made == 1


@responses.activate
def test_non_json_is_a_provider_error(settings):
    responses.get("https://remoteok.com/api", body="<html>blocked</html>")
    with pytest.raises(ProviderError, match="not JSON"):
        list(make("remoteok", settings).fetch())


def test_budget_is_enforced(settings):
    with pytest.raises(BudgetExhausted):
        list(make("remoteok", settings, budget=0).fetch())


def test_missing_env_detection():
    assert REGISTRY["adzuna"].missing_env({"ADZUNA_APP_ID": "x"}) == ["ADZUNA_APP_KEY"]
    assert REGISTRY["remotive"].missing_env({}) == []
