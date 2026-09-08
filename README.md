# SEEK Job Application Portal

A small Flask + SQLite app with two roles:

- **Admin** — create job listings, view/manage them, view applications, close jobs.
- **Candidate** — browse open jobs and apply.

---

## 1. How to Run

### Requirements
- Python 3.10+
- `pip install flask`
- (for tests) `pip install pytest`

### Project layout expected by Flask
```
project/
├── app.py
├── test_app.py
├── database.db          # created automatically on first request
└── templates/
    ├── index.html
    ├── admin.html
    ├── listings.html
    ├── job.html
    └── candidate.html
```
Flask's `render_template()` looks for a `templates/` folder next to `app.py`, so make sure the five HTML files live there (not in the project root).

### Run it (activate the virtual environment and install flask, then run)
```bash
python -m venv .venv
source .venv/bin/activate
pip install flask
python app.py
```
The dev server starts at **http://127.0.0.1:5000/**. Open it in a browser, choose **Admin** or **Candidate**, and go.

There is no build step, no environment variables, and no external services — the SQLite file `database.db` is created automatically the first time `/admin` or `/candidate` is visited.

### Run the tests
```bash
pip install flask pytest
pytest test_app.py -v
```
---

## 2. Design Overview

**Stack:** Flask (routing + Jinja2 templates), `sqlite3`, Bootstrap 4 for some minor styling.

**Data model** (two tables, created on demand with `CREATE TABLE IF NOT EXISTS`):
- `jobs(jid, title, description, location, created_on, status)` — `status` is an integer: `1 = Open`, `2 = Closed`.
- `applications(appid, jid, candidate_name, candidate_email, submitted_on)` — `jid` is a loose foreign key back to `jobs`.

**Routes:**

| Route | Method(s) | Purpose |
|---|---|---|
| `/` | GET/POST | Landing page; role selector redirects to `/admin` or `/candidate`. |
| `/admin_nav` | POST | Small helper that routes the admin's dropdown menu choice to `/admin` (create) or `/admin/manage` (list). |
| `/admin` | GET/POST | Create-job form; POST inserts a new row with `status=1` (a newly created job is open for applications). |
| `/admin/manage` | GET | Lists all jobs, optionally filtered by `status_filter` query param (`1`, `2`, or `all`). |
| `/job/<jid>` | GET | Job detail page. In admin context, also shows all applications for that job and a "Close Job" action. |
| `/job/<jid>/edit` | GET/POST | Edit an existing job's title/description/location. |
| `/job/<jid>/close` | POST | Sets a job's status to `2` (Closed). |
| `/candidate` | GET | Lists only `status=1` (open) jobs for candidates. |
| `/candidate/job/<jid>` | GET/POST | Job detail + application form; POST inserts into `applications`, rejecting a second application from the same name **or** email for that job. |

**Templates** are shared/parameterized by a `role` variable (`'admin'` vs `'candidate'`) so `job.html` and `listings.html` render different actions (e.g., "Edit/Close" vs "Apply") from the same markup.

**Business rules implemented:**
- All three fields (title/description/location) are required to create or edit a job.
- A job starts `Open` and can only move to `Closed` (one-way) via `/job/<jid>/close`.
- Only `Open` jobs are shown to candidates.
- A candidate can't apply twice to the same job using the same name *or* the same email (checked with a single `SELECT ... WHERE jid = ? AND (candidate_name = ? OR candidate_email = ?)`).
- Requesting a job/edit page for a `jid` that doesn't exist returns a plain `404`.

---

## 3. Assumptions

- **No authentication/authorization.** Anyone who knows the URL can hit `/admin`, `/admin/manage`, `/job/<jid>/edit`, or `/job/<jid>/close`. I assumed this is fine for the scope of this exercise (a prototype/take-home), not a production deployment.
- **"Uniqueness" of an applicant is approximate.** The duplicate-application check is per-job, on `name OR email` — two different people who happen to share a name would be incorrectly blocked, and email format isn't validated.
- **Status is a bare integer (`1`/`2`)** rather than an enum/string, matching what the templates already expected (`job['status'] == 1`).
- **`database.db` is created relative to the current working directory**, not relative to `app.py`'s location — so the app must be launched from the project root (this is also why the test suite `chdir`s into a temp directory per test).
- Dates are stored as Python `datetime.now()` values and only ever truncated for display (`created_on[:10]`); no timezone handling was assumed to be in scope.

---

## 4. What I'd Improve With More Time

**Security:**
- Add real authentication (e.g., Flask-Login) and gate all `/admin*` routes behind an `admin_required` check instead of trusting a `role` string.
- Validate email format server-side (currently only `type="email"` client-side validation via HTML5).

**Features:**
- Pagination on `/admin/manage` and `/candidate` once the jobs table grows.
- Ability to re-open a closed job, or soft-delete a job.
- Admin ability to see/export all applications across jobs, not just per-job.
- Basic server-side validation feedback per-field, not just one combined error string.

**Testing:**
- Add tests for concurrent/race conditions on duplicate applications.
- Add integration/UI tests (e.g., Selenium/Playwright) for the Bootstrap modal confirm-close flow, which isn't exercised by the current server-side unit tests.

---

## Files

- `app.py` — Flask application (given).
- `templates/*.html` — Jinja2 templates (given).
- `test_app.py` — pytest suite covering the business logic and endpoints described above (30 tests).
