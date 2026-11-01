# Build guide: Job Market Tracker, from scratch to live

This guide walks through building the project in 10 steps. Each step matches one
commit in this repo's history (`git log --oneline`), so you can check out any step
and see exactly what existed at that point:

```bash
git log --oneline          # list the steps
git checkout <commit>      # look at the project as of that step
git checkout main          # back to the finished version
```

Rebuild each step yourself in VS Code rather than copying it; type it, run it,
break it. You should be able to explain every file in an interview.

---

## What you are building

```
 GitHub Actions (daily cron)                        Visitors
        │                                              │
        ▼                                              ▼
 scripts/refresh.py ──► 8 job APIs           React dashboard (Vercel)
        │   (each isolated, retried,                   │
        │    rested if broken)                         ▼
        ▼                                     Flask API (Render)
   clean → dedupe → skills ──► PostgreSQL (Neon) ◄────┘
```

* **Refresh** runs on a schedule, never on a visitor's request. One refresh a day
  serves every visitor, which keeps you far inside every free tier.
* **The API** only reads the database.
* **The dashboard** only talks to the API.

### What "self-surviving" means here

| Problem | What the code does | Where |
|---|---|---|
| You have no API keys yet | Keyless sources (Remotive, Jobicy, The Muse, Remote OK, Himalayas) still run; keyed ones are skipped | `refresh.py`, `missing_env()` |
| A source is down for a day | Retries with backoff; the other sources still run | `base.py` `get_json()` |
| A source breaks for good (API changed) | After 3 failures in a row it rests 6h, then 12h, 24h… up to 7 days, then gets a trial run; one success fully resets it | `_record_failure()` |
| A source starts returning nothing | Counted as a failure, so you see it on the dashboard | `run_refresh()` |
| A source changes its JSON shape | Caught per source; logged; other sources unaffected | `run_refresh()` |
| Free-tier limits / fair-use rules | Per-source daily request budget stored in the database | `daily_request_budget` in `tracker.toml` |
| Main daily run fails | A second scheduled run 12h later retries, only if data is stale | `refresh.yml`, `--if-stale` |
| A run crashes half way | It is marked failed after an hour so it never blocks future runs | `_start_run()` |
| Database is asleep (Neon free tier) | Connection is retried with backoff | `Database.wait_until_ready()` |
| Database fills up | Postings not seen for 60 days are deleted | `_prune()` |
| GitHub pauses the schedule after 60 quiet days | Workflow pushes an empty commit after 50 quiet days | `refresh.yml` Keepalive |
| Render free API is asleep | Dashboard retries requests | `frontend/src/api.js` |
| Everything fails | Workflow exits 1, GitHub emails you | `scripts/refresh.py` |

### Decisions from the scope deck (slide 7), as built

| Decision | Choice | Change it in |
|---|---|---|
| Keyword list | software engineer, backend developer, python developer, full stack developer, data engineer, frontend developer | `tracker.toml` `[search] keywords` |
| Skill list | 36 skills, regex per skill | `tracker.toml` `[skills]` |
| US only or one city | US only (`country = "us"`); set `location = "San Diego"` for one city | `tracker.toml` |
| Show salary ranges? | Yes, only when the source states them; Adzuna's *estimated* salaries are stored but left out of the salary chart | `[salary] include_predicted` |
| Are we allowed to store and show postings? | **Read each source's terms yourself before going public.** The code follows the rules the sources publish: link every posting to its original page, credit each source on the page, Adzuna links use `redirect_url`, Remotive gets at most 2 calls a day | Footer + `daily_request_budget` |

---

## Step 0. Tools and accounts (30 min)

Install: Python 3.12+, Node 22+, Git, VS Code.

Create free accounts (you can do the keyed ones later; the project runs without them):

| Account | Why | Needed for |
|---|---|---|
| GitHub | Code + the daily scheduler | Step 9 |
| [Neon](https://neon.tech) | PostgreSQL database | Step 9 |
| [Render](https://render.com) | Hosts the Flask API | Step 9 |
| [Vercel](https://vercel.com) | Hosts the React dashboard | Step 9 |
| [Adzuna developer](https://developer.adzuna.com) | Biggest US source, gives app_id + app_key | optional |
| [USAJOBS developer](https://developer.usajobs.gov) | Federal jobs, gives an API key tied to your email | optional |

---

## Step 1. Project skeleton and config

**Files:** `.gitignore`, `backend/requirements*.txt`, `backend/.env.example`,
`backend/tracker.toml`, `backend/app/config.py`

```bash
mkdir job-market-tracker && cd job-market-tracker && git init
mkdir -p backend/app && cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
```

**Idea:** settings that change (keywords, skills, which sources are on) live in
`tracker.toml`; secrets live in environment variables; `config.py` merges the two.
Environment variables always win, so production keys never go in the repo.

Note `_normalize_db_url()`: Neon gives you `postgresql://…`, SQLAlchemy needs
`postgresql+psycopg://…`. With no `DATABASE_URL` it falls back to a local SQLite file,
so you can develop with zero setup.

**Check:** `python -c "from app.config import get_settings; print(get_settings().keywords)"`

---

## Step 2. Database models

**File:** `backend/app/db.py`

Four tables:

| Table | Purpose |
|---|---|
| `postings` | One row per job. `fingerprint` (hash of title + company + state) is unique, so the same job from two sources is stored once. `(source, external_id)` is also unique. |
| `skill_counts` | One row per (posting, skill), as in the scope. Counting skills is a `GROUP BY`. |
| `provider_health` | Per source: failures in a row, cooldown, requests used today, last error. This is the self-healing memory. |
| `refresh_runs` | One row per refresh, with a JSON report. Powers `/health` and `/runs`. |

`Database.create_all()` creates the tables on first start, so there is no manual
migration step. Same code runs on SQLite and PostgreSQL.

**Check:** `python -c "from app.db import Database; Database('sqlite:///t.db').create_all()"` then open `t.db` in a SQLite viewer.

---

## Step 3. The provider layer (the "API pool")

**Files:** `backend/app/providers/*.py`

`base.py` is the important file:

* `RawJob`: the one shape every source is translated into.
* `Provider.get_json()`: every HTTP call goes through here. It retries network
  errors and 5xx/429 with exponential backoff and jitter, honors `Retry-After`,
  does **not** retry 401/403/404 (retrying a bad key is pointless), counts every
  request against the daily budget, and raises `ProviderError` or `BudgetExhausted`.
* `required_env`: which environment variables a source needs. Missing = skipped.
* `country_scoped`: true for Adzuna and USAJOBS, whose results are already US-only.

Each other file is a small adapter that maps one API's JSON to `RawJob`:

| Source | Key? | Notes |
|---|---|---|
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | One call per keyword; uses `location.area` to get the state |
| USAJOBS | `USAJOBS_API_KEY`, `USAJOBS_EMAIL` | Needs `Host`, `User-Agent` (your email) and `Authorization-Key` headers |
| Remotive | none | One call for the whole feed, filtered locally (they ask for ≤4 calls/day) |
| Jobicy | none | `geo=usa`, `tag=<keyword>` |
| The Muse | optional `MUSE_API_KEY` | Browses by category, not keyword |
| Remote OK | none | First array item is a legal notice; skipped |
| Himalayas | none | Pages of 20 |
| Arbeitnow | none | Mostly Europe; off by default |

`providers/__init__.py` has `REGISTRY`. **To add a source:** write a subclass with
`name` and `fetch()`, add it to `REGISTRY`, add a `[providers.<name>]` block to
`tracker.toml`. Nothing else changes.

---

## Step 4. Cleaning and skills

**Files:** `backend/app/pipeline/clean.py`, `backend/app/pipeline/skills.py`

Pure functions, no network or database, so they are easy to test.

* `strip_html()`: descriptions arrive as HTML.
* `normalize_location()`: "San Diego, California" and "San Diego, CA" become
  "San Diego, CA" with `state="CA"`; "USA", "Worldwide", "Europe" become
  "Remote (US)", "Remote (Anywhere)", "Remote (Europe)". Also decides whether a
  remote job is open to US candidates.
* `normalize_salary()`: hourly ×2080, monthly ×12, etc.; parses free text like
  "$90k - $120k"; drops non-USD and nonsense values; swaps min/max if reversed.
* `fingerprint()`: lowercases, removes "(Remote)", "Inc", "LLC", punctuation, so
  "Software Engineer (Remote) – Acme, Inc." and "software engineer – ACME" match.
* `clean_job()`: returns the clean job or a skip reason (`no_title`, `no_url`, `not_us`).
* `SkillMatcher`: compiles the regexes from `tracker.toml`. A typo in one pattern
  is logged and skipped instead of breaking the refresh.

---

## Step 5. The refresh pipeline

**Files:** `backend/app/pipeline/refresh.py`, `backend/scripts/refresh.py`,
`backend/tests/fake_http.py`

`run_refresh()` in order:

1. Take a lock (a `running` row in `refresh_runs`); clear stale locks older than 1h.
2. For each provider: skip if disabled / missing keys / cooling down / out of budget;
   otherwise fetch, clean each job, and record success or failure in `provider_health`.
   A provider's crash is caught right there and never touches the others.
3. Store: dedupe the batch, insert new postings with their skills, bump
   `last_seen_at` on ones already stored (and fill in a salary if one appears).
4. Prune postings unseen for `retention_days`.
5. Save the run report. Status is `ok`, `partial` (some sources failed) or `failed`.

`fake_http.py` imitates every provider so you can run all of this offline:

```bash
python -m scripts.refresh --demo        # sample data, no network
python -m scripts.refresh               # real APIs
python -m scripts.refresh --only remotive,jobicy
python -m scripts.refresh --if-stale 20 # do nothing if data is <20h old
```

**Check:** run `--demo` and read the JSON report it prints.

---

## Step 6. The Flask API

**Files:** `backend/app/__init__.py`, `backend/app/routes.py`, `backend/wsgi.py`

| Endpoint | Returns |
|---|---|
| `GET /health` | DB status, posting count, hours since last good refresh, `stale` flag |
| `GET /postings?limit=20` | Newest first. Filters: `q`, `source`, `skill`, `remote`, `state`, `has_salary`, `days`, `offset` |
| `GET /stats/daily?days=30` | Postings per day (missing days filled with 0), split by source |
| `GET /stats/skills` | Skill counts and share of postings; accepts the same filters |
| `GET /stats/salary` | 25th/50th/75th percentile and $20k buckets; accepts filters (e.g. `skill=Python`) |
| `GET /stats/summary` | Totals, new in 24h, remote share, salary share, by source, top states |
| `GET /providers` | Each source's state: healthy, failing, cooling_down, needs_key, disabled |
| `GET /runs` | Last refresh reports |
| `POST /admin/refresh` | Starts a refresh; needs `Authorization: Bearer $ADMIN_TOKEN` |

`limit` is capped at 100 and bad numbers fall back to defaults, so no query string
can make the API do something expensive.

Optional safety net: set `AUTO_REFRESH_IF_STALE_HOURS=30` and the API starts a
background refresh itself if `/health` sees stale data.

```bash
python wsgi.py                     # http://localhost:5000/health
```

---

## Step 7. Tests (pytest, APIs mocked)

**Files:** `backend/tests/*.py`

```bash
pytest -q        # 43 tests, about 3 seconds, zero network calls
```

* `test_clean.py`: locations, salary parsing, fingerprints, skill regexes.
* `test_providers.py`: each adapter against a mocked copy of its real URL
  (`responses` library); retry on 503; no retry on 401; non-JSON handling; budgets.
* `test_refresh.py`: the self-healing rules: second run inserts nothing
  (idempotent); missing keys skip; a broken source is rested after 3 failures and
  recovers after one success; empty feeds and changed JSON shapes are caught;
  budgets persist; pruning; crashed-run recovery; run lock.
* `test_api.py`: every endpoint, filters, caps, admin auth.

---

## Step 8. The React dashboard

**Files:** `frontend/*`

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to Flask on :5000)
```

| Component | Shows |
|---|---|
| `Kpis` | Open postings, new in 24h, companies, % with salary, % remote |
| `DailyChart` | Postings per day, 7/30/90-day toggle |
| `SalaryChart` | Salary histogram with 25th/median/75th |
| `SkillsChart` | Top 15 skills; **click a bar** to filter the salary chart and postings by that skill |
| `BreakdownCard` | Postings by source and top states |
| `Postings` | Search + filters, newest first, "Show more" paging; every row links to the original listing |
| `Providers` | Health of every source, with what to do for ones needing a key |

Every chart card has a **Table** button showing the same numbers as a table.
Dark mode follows the system setting. The footer credits each source.

`VITE_API_URL` points the built site at your deployed API.

---

## Step 9. Automate and deploy

### 9a. Database (Neon)
Create a project, copy the connection string (`postgresql://…?sslmode=require`).
Tables create themselves on the first run.

### 9b. GitHub repo and secrets
Push the repo. Then **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Required? |
|---|---|
| `DATABASE_URL` | yes |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | optional |
| `USAJOBS_API_KEY`, `USAJOBS_EMAIL` | optional |
| `MUSE_API_KEY` | optional |

Then **Actions → Refresh job postings → Run workflow**. Open the run; the summary
shows a table of every source. Your database now has data.

`refresh.yml` runs daily at 13:17 UTC (about 6am Pacific). The 01:17 UTC run is the
backup: it does nothing unless the main run failed. `ci.yml` runs tests and the
frontend build on every push.

### 9c. API on Render
**New → Blueprint**, pick the repo (it reads `render.yaml`). Set `DATABASE_URL` and
`CORS_ORIGINS` (your Vercel URL, add it after 9d). Visit
`https://<your-api>.onrender.com/health`.

### 9d. Dashboard on Vercel
**Add New → Project**, pick the repo, **Root Directory = `frontend`**, framework Vite,
env var `VITE_API_URL=https://<your-api>.onrender.com`. Deploy. Put the Vercel URL
into Render's `CORS_ORIGINS` and redeploy the API.

---

## Step 10. Ship it

- [ ] `/health` shows `"status": "ok"`
- [ ] Data sources table: keyless sources "Healthy"
- [ ] A posting link opens the source's page
- [ ] Repo pinned on your GitHub profile, live link in the README
- [ ] Screenshot in the README
- [ ] Read each source's terms (links in the footer) before sharing widely

### How to describe it (from the scope deck)
Say what it does today and what you built. For example:

> Built a job market tracker that pulls US software postings daily from several
> job APIs (Adzuna, USAJOBS, Remotive and others) with a Python pipeline on GitHub
> Actions, cleans and dedupes them into PostgreSQL, and serves a Flask API and
> React dashboard of postings per day, top skills and salary ranges. Each source is
> isolated with retries and automatic cooldowns, so one failing API never stops
> the refresh. 43 pytest tests with all APIs mocked.

Personal project, not client or company work, and nothing it does not yet do.

---

## Ideas for later
* Email yourself new postings that match your skills.
* Trend lines per skill (needs a daily snapshot table).
* Add Jooble or Findwork as more keyed sources (same pattern as Adzuna).
