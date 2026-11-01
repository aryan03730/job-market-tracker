from app.pipeline.refresh import run_refresh
from tests.fake_http import FakeSession, demo_env


def seed(db, settings):
    run_refresh(db, settings, env=demo_env(), http_factory=FakeSession)


def test_health_before_any_data(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json["stale"] is True and r.json["postings"] == 0


def test_endpoints(client, db, settings):
    seed(db, settings)
    h = client.get("/health").json
    assert h["status"] == "ok" and h["postings"] > 0

    p = client.get("/postings?limit=5").json
    assert len(p["items"]) == 5 and p["total"] == h["postings"]
    dates = [i["posted_at"] for i in p["items"]]
    assert dates == sorted(dates, reverse=True)

    py = client.get("/postings?skill=Python&limit=100").json
    assert all("Python" in i["skills"] for i in py["items"])
    assert all(i["is_remote"] for i in client.get("/postings?remote=true").json["items"])
    assert all(i["salary_min"] for i in client.get("/postings?has_salary=1").json["items"])

    daily = client.get("/stats/daily?days=14").json
    assert len(daily) == 15 and sum(d["total"] for d in daily) > 0

    skills = client.get("/stats/skills").json
    assert skills[0]["count"] >= skills[-1]["count"] and 0 < skills[0]["share"] <= 1

    sal = client.get("/stats/salary").json
    assert sal["count"] > 0 and sal["p25"] <= sal["median"] <= sal["p75"]

    summary = client.get("/stats/summary").json
    assert set(summary["by_source"]) >= {"adzuna", "remotive"}

    provs = {p["name"]: p for p in client.get("/providers").json}
    assert provs["arbeitnow"]["state"] == "disabled" and provs["remotive"]["state"] == "healthy"
    assert client.get("/runs").json[0]["status"] == "ok"


def test_limit_is_capped_and_bad_input_ignored(client):
    r = client.get("/postings?limit=99999&offset=abc")
    assert r.status_code == 200 and r.json["limit"] == 100 and r.json["offset"] == 0


def test_admin_refresh_requires_token(client, settings):
    assert client.post("/admin/refresh").status_code == 401
    settings.admin_token = "secret"
    assert client.post("/admin/refresh", headers={"Authorization": "Bearer wrong"}).status_code == 401
