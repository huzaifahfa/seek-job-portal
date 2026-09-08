"""
Unit tests for the SEEK Job Application Portal (app.py).

Run with:
    pytest test_app.py -v

Each test runs in its own temporary working directory (via the
`client` fixture) so that the SQLite file the app creates
("database.db") never collides between tests and never touches a
real/shared database.
"""
import re
import sqlite3 as sql

import pytest

import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Flask test client whose current working directory is a fresh temp
    folder for every test, so `sql.connect('database.db')` inside
    app.py always starts from a clean database.
    """
    monkeypatch.chdir(tmp_path)
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as test_client:
        # NOTE: table creation in app.py only happens inside the /admin and
        # /candidate view functions, not at app startup. Routes such as
        # /admin/manage, /job/<jid>, /job/<jid>/edit and /candidate/job/<jid>
        # will raise sqlite3.OperationalError ("no such table: jobs") if they
        # are the very first route hit against a brand-new database file.
        # We hit /admin once here so every test starts from initialized
        # tables, matching how the app behaves once it has been used at all.
        # See the README "What I'd improve" section for the underlying fix.
        test_client.get('/admin')
        yield test_client


# Helpers
def create_job(client, title="Backend Engineer", description="Build things.",
                location="Remote"):
    """POST to /admin to create a job and return its jid by inspecting the DB."""
    client.post('/admin', data={
        'title': title,
        'description': description,
        'location': location,
    })
    conn = sql.connect('database.db')
    conn.row_factory = sql.Row
    row = conn.execute(
        'SELECT jid FROM jobs WHERE title = ? ORDER BY jid DESC LIMIT 1', (title,)
    ).fetchone()
    conn.close()
    return row['jid']


# Landing page / role routing
class TestIndexRouting:
    def test_get_index_renders_form(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'Choose Your Role' in resp.data

    def test_post_admin_role_redirects_to_admin(self, client):
        resp = client.post('/', data={'role': 'admin'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/admin')

    def test_post_candidate_role_redirects_to_candidate(self, client):
        resp = client.post('/', data={'role': 'candidate'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/candidate')

    def test_post_unknown_role_falls_through(self, client):
        # No redirect branch matches -> falls through to render_template('index.html')
        resp = client.post('/', data={'role': 'bogus'})
        assert resp.status_code == 200


class TestAdminNav:
    def test_manage_choice_redirects_to_manage(self, client):
        resp = client.post('/admin_nav', data={'admin_route': 'manage'})
        assert resp.headers['Location'].endswith('/admin/manage')

    def test_default_choice_redirects_to_admin(self, client):
        resp = client.post('/admin_nav', data={'admin_route': 'admin'})
        assert resp.headers['Location'].endswith('/admin')

    def test_missing_choice_defaults_to_admin(self, client):
        resp = client.post('/admin_nav', data={})
        assert resp.headers['Location'].endswith('/admin')


# Job creation (core business logic)
class TestCreateJob:
    def test_get_admin_renders_empty_form(self, client):
        resp = client.get('/admin')
        assert resp.status_code == 200
        assert b'Create a New Job' in resp.data

    def test_create_job_with_all_fields_succeeds(self, client):
        resp = client.post('/admin', data={
            'title': 'Data Analyst',
            'description': 'Analyze data.',
            'location': 'Sydney',
        })
        assert resp.status_code == 200
        assert b'Job Created!' in resp.data

        conn = sql.connect('database.db')
        conn.row_factory = sql.Row
        job = conn.execute('SELECT * FROM jobs WHERE title = ?', ('Data Analyst',)).fetchone()
        conn.close()

        assert job is not None
        assert job['location'] == 'Sydney'
        assert job['status'] == 1  # new jobs default to "Open"

    @pytest.mark.parametrize('missing_field', ['title', 'description', 'location'])
    def test_create_job_missing_required_field_shows_error(self, client, missing_field):
        data = {
            'title': 'QA Engineer',
            'description': 'Test things.',
            'location': 'Melbourne',
        }
        data[missing_field] = ''

        resp = client.post('/admin', data=data)
        assert b'All fields (Title, Description, Location) are required.' in resp.data

        conn = sql.connect('database.db')
        count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        conn.close()
        assert count == 0  # nothing should have been inserted


# Manage / listing + status filter
class TestManageListings:
    def test_manage_lists_all_jobs_by_default(self, client):
        create_job(client, title='Job A')
        create_job(client, title='Job B')

        resp = client.get('/admin/manage')
        assert b'Job A' in resp.data
        assert b'Job B' in resp.data

    def test_manage_filters_open_jobs(self, client):
        open_jid = create_job(client, title='Open Role')
        closed_jid = create_job(client, title='Closed Role')
        client.post(f'/job/{closed_jid}/close')

        resp = client.get('/admin/manage?status_filter=1')
        assert b'Open Role' in resp.data
        assert b'Closed Role' not in resp.data

    def test_manage_filters_closed_jobs(self, client):
        open_jid = create_job(client, title='Still Open')
        closed_jid = create_job(client, title='Now Closed')
        client.post(f'/job/{closed_jid}/close')

        resp = client.get('/admin/manage?status_filter=2')
        assert b'Now Closed' in resp.data
        assert b'Still Open' not in resp.data

    def test_manage_empty_state(self, client):
        resp = client.get('/admin/manage')
        assert b'No jobs found.' in resp.data


# Viewing a single job
class TestViewJob:
    def test_view_existing_job_returns_details(self, client):
        jid = create_job(client, title='Frontend Engineer', location='Auckland')
        resp = client.get(f'/job/{jid}')
        assert resp.status_code == 200
        assert b'Frontend Engineer' in resp.data
        assert b'Auckland' in resp.data
        assert b'No applications received yet.' in resp.data

    def test_view_nonexistent_job_returns_404(self, client):
        resp = client.get('/job/9999')
        assert resp.status_code == 404

    def test_view_job_lists_applications(self, client):
        jid = create_job(client)
        client.post(f'/candidate/job/{jid}', data={
            'candidate_name': 'Ada Lovelace',
            'candidate_email': 'ada@example.com',
        })
        resp = client.get(f'/job/{jid}')
        assert b'Ada Lovelace' in resp.data
        assert b'ada@example.com' in resp.data


# Editing a job
class TestEditJob:
    def test_get_edit_prefills_form(self, client):
        jid = create_job(client, title='Old Title')
        resp = client.get(f'/job/{jid}/edit')
        assert resp.status_code == 200
        assert b'Old Title' in resp.data

    def test_edit_updates_job_and_redirects(self, client):
        jid = create_job(client, title='Old Title', location='Old Loc')
        resp = client.post(f'/job/{jid}/edit', data={
            'title': 'New Title',
            'description': 'New description.',
            'location': 'New Loc',
        })
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/job/{jid}')

        conn = sql.connect('database.db')
        conn.row_factory = sql.Row
        job = conn.execute('SELECT * FROM jobs WHERE jid = ?', (jid,)).fetchone()
        conn.close()
        assert job['title'] == 'New Title'
        assert job['location'] == 'New Loc'

    def test_edit_missing_field_shows_error_and_does_not_update(self, client):
        jid = create_job(client, title='Keep Me')
        resp = client.post(f'/job/{jid}/edit', data={
            'title': '',
            'description': 'New description.',
            'location': 'New Loc',
        })
        assert b'All fields are required.' in resp.data

        conn = sql.connect('database.db')
        conn.row_factory = sql.Row
        job = conn.execute('SELECT * FROM jobs WHERE jid = ?', (jid,)).fetchone()
        conn.close()
        assert job['title'] == 'Keep Me'  # unchanged

    def test_edit_nonexistent_job_returns_404(self, client):
        resp = client.get('/job/9999/edit')
        assert resp.status_code == 404


# Closing a job
class TestCloseJob:
    def test_close_job_sets_status_closed(self, client):
        jid = create_job(client)
        resp = client.post(f'/job/{jid}/close')
        assert resp.status_code == 302

        conn = sql.connect('database.db')
        status = conn.execute('SELECT status FROM jobs WHERE jid = ?', (jid,)).fetchone()[0]
        conn.close()
        assert status == 2

    def test_closed_job_no_longer_listed_for_candidates(self, client):
        jid = create_job(client, title='Soon Closed')
        client.post(f'/job/{jid}/close')

        resp = client.get('/candidate')
        assert b'Soon Closed' not in resp.data


# Candidate-facing listing + applications
class TestCandidateFlow:
    def test_candidate_listing_shows_only_open_jobs(self, client):
        open_jid = create_job(client, title='Open Job')
        closed_jid = create_job(client, title='Closed Job')
        client.post(f'/job/{closed_jid}/close')

        resp = client.get('/candidate')
        assert b'Open Job' in resp.data
        assert b'Closed Job' not in resp.data

    def test_apply_to_job_succeeds(self, client):
        jid = create_job(client)
        resp = client.post(f'/candidate/job/{jid}', data={
            'candidate_name': 'Grace Hopper',
            'candidate_email': 'grace@example.com',
        })
        assert b'Application Submitted!' in resp.data

        conn = sql.connect('database.db')
        count = conn.execute(
            'SELECT COUNT(*) FROM applications WHERE jid = ?', (jid,)
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_duplicate_application_is_rejected(self, client):
        jid = create_job(client)
        client.post(f'/candidate/job/{jid}', data={
            'candidate_name': 'Grace Hopper',
            'candidate_email': 'grace@example.com',
        })
        resp = client.post(f'/candidate/job/{jid}', data={
            'candidate_name': 'Grace Hopper',
            'candidate_email': 'different@example.com',
        })
        assert b'You have already submitted your application.' in resp.data

        conn = sql.connect('database.db')
        count = conn.execute(
            'SELECT COUNT(*) FROM applications WHERE jid = ?', (jid,)
        ).fetchone()[0]
        conn.close()
        assert count == 1  # second attempt was not inserted

    def test_apply_missing_fields_shows_error(self, client):
        jid = create_job(client)
        resp = client.post(f'/candidate/job/{jid}', data={
            'candidate_name': '',
            'candidate_email': '',
        })
        assert b'Name and Email are required.' in resp.data

    def test_apply_to_nonexistent_job_returns_404(self, client):
        resp = client.post('/candidate/job/9999', data={
            'candidate_name': 'Nobody',
            'candidate_email': 'nobody@example.com',
        })
        assert resp.status_code == 404