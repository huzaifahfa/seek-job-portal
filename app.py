from calendar import error

from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import sqlite3 as sql

app = Flask(__name__)

host = 'http://127.0.0.1:5000/'

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        result = request.form.get('role')    # this is updated to work with dropdown form
        if result == "admin":                     # basically redirect link to admin.html when admin is chosen
            return redirect(url_for('admin'))
        elif result == "candidate":                # redirect link to candidate.html when candidate is chosen
            return redirect(url_for('candidate'))
    return render_template('index.html')


@app.route('/admin_nav', methods=['POST'])
def admin_nav():
    # Grab the choice from the dropdown
    destination = request.form.get('admin_route')

    if destination == "manage":
        return redirect(url_for('manage'))
    else:
        # Defaults back to admin if 'admin' is chosen or something goes wrong
        return redirect(url_for('admin'))
@app.route('/admin', methods=['POST', 'GET'])
def admin():
    error = None
    success_msg = None

    connection = sql.connect('database.db')

    try:
        connection.execute('CREATE TABLE IF NOT EXISTS jobs (jid INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, location TEXT, created_on DATETIME, status INTEGER);')
        connection.execute('CREATE TABLE IF NOT EXISTS applications (appid INTEGER PRIMARY KEY AUTOINCREMENT, jid INTEGER, candidate_name TEXT, candidate_email TEXT, submitted_on DATETIME, FOREIGN KEY(jid) REFERENCES jobs(jid));')
        connection.commit()

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')
            
            if title and description and location:
                connection.execute('''
                    INSERT INTO jobs (title, description, location, created_on, status) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (title, description, location, datetime.now(), 1)) # 1 to indicate job status is open
                connection.commit()
                success_msg = "Job Created!"
            else:
                error = "All fields (Title, Description, Location) are required."

    finally:
        connection.close()

    return render_template(
        'admin.html', 
        error=error, 
        success_msg=success_msg, 
    )


@app.route('/admin/manage', methods=['GET'])
def manage():
    connection = sql.connect('database.db')

    try:
        connection.row_factory = sql.Row
        status_filter = request.args.get('status_filter', 'all')

        if status_filter == '1':
            cursor = connection.execute('SELECT * FROM jobs WHERE status = 1 ORDER BY created_on DESC')
        elif status_filter == '2':
            cursor = connection.execute('SELECT * FROM jobs WHERE status = 2 ORDER BY created_on DESC')
        else:
            cursor = connection.execute('SELECT * FROM jobs ORDER BY created_on DESC')

        jobs = cursor.fetchall()

    finally:
        connection.close()

    return render_template('listings.html', jobs=jobs, role='admin')


@app.route('/job/<int:jid>', methods=['GET'])
def view_job(jid):
    connection = sql.connect('database.db')

    try:
        connection.row_factory = sql.Row
        cursor = connection.execute('SELECT * FROM jobs WHERE jid = ?', (jid,))
        job = cursor.fetchone()

        if job:
            cursor = connection.execute('SELECT * FROM applications WHERE jid = ? ORDER BY submitted_on DESC', (jid,))
            applications = cursor.fetchall()

    finally:
        connection.close()

    # If the user types in a URL for a job that doesn't exist, handle it gracefully
    if job is None:
        return "Job not found", 404

    return render_template('job.html', job=job, role='admin', applications=applications)


@app.route('/job/<int:jid>/edit', methods=['GET', 'POST'])
def edit_job(jid):
    error = None
    connection = sql.connect('database.db')

    try:
        connection.row_factory = sql.Row

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')

            if title and description and location:
                connection.execute('''
                                   UPDATE jobs
                                   SET title       = ?,
                                       description = ?,
                                       location    = ?
                                   WHERE jid = ?
                                   ''', (title, description, location, jid))
                connection.commit()
                return redirect(url_for('view_job', jid=jid))
            else:
                error = "All fields are required."

        cursor = connection.execute('SELECT * FROM jobs WHERE jid = ?', (jid,))
        job = cursor.fetchone()

        if job is None:
            return "Job not found", 404

    finally:
        connection.close()

    return render_template('admin.html', job=job, error=error)


@app.route('/job/<int:jid>/close', methods=['POST'])
def close_job(jid):
    connection = sql.connect('database.db')
    try:
        connection.execute('UPDATE jobs SET status = 2 WHERE jid = ?', (jid,))
        connection.commit()

    finally:
        connection.close()

    return redirect(url_for('view_job', jid=jid))

@app.route('/candidate', methods=['GET'])
def candidate():
    connection = sql.connect('database.db')

    try:
        connection.execute('CREATE TABLE IF NOT EXISTS jobs (jid INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description LONGTEXT, location TEXT, created_on DATETIME, status INTEGER);')
        connection.execute('CREATE TABLE IF NOT EXISTS applications (appid INTEGER PRIMARY KEY AUTOINCREMENT, jid INTEGER, candidate_name TEXT, candidate_email TEXT, submitted_on DATETIME, FOREIGN KEY(jid) REFERENCES jobs(jid));')
        connection.commit()
        connection.row_factory = sql.Row
        cursor = connection.execute('SELECT * FROM jobs WHERE status=1 ORDER BY created_on DESC')
        open_jobs = cursor.fetchall()

    finally:
        connection.close()

    return render_template('listings.html', jobs=open_jobs, role='candidate')

@app.route('/candidate/job/<int:jid>', methods=['GET', 'POST'])
def candidate_job(jid):
    error = None
    success_msg = None
    connection = sql.connect('database.db')

    try:
        connection.row_factory = sql.Row
        cursor = connection.execute('SELECT * FROM jobs WHERE jid = ?', (jid,))
        job = cursor.fetchone()

        if job is None:
            return "Job not found or is no longer accepting applications.", 404

        if request.method == 'POST':
            candidate_name = request.form.get('candidate_name')
            candidate_email = request.form.get('candidate_email')

            if candidate_name and candidate_email:
                cursor = connection.execute('''
                                            SELECT *
                                            FROM applications
                                            WHERE jid = ?
                                              AND (candidate_name = ? OR candidate_email = ?)
                                            ''', (jid, candidate_name, candidate_email))

                existing_application = cursor.fetchone()

                if existing_application:
                    error = "You have already submitted your application."
                else:
                    connection.execute('''
                                       INSERT INTO applications (jid, candidate_name, candidate_email, submitted_on)
                                       VALUES (?, ?, ?, ?)
                                       ''', (jid, candidate_name, candidate_email, datetime.now()))
                    connection.commit()
                    success_msg = "Application Submitted!"
            else:
                error = "Name and Email are required."

    finally:
        connection.close()

    return render_template('job.html', job=job, role='candidate', error=error, success_msg=success_msg)


if __name__ == '__main__':
    app.run()
