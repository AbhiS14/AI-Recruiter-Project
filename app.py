import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF
from io import BytesIO
import pandas as pd

from utils.resume_parser import extract_keywords_from_pdf
from utils.ranking import rank_resume
from utils.cultural_fit import check_cultural_fit

app = Flask(__name__)
app.secret_key = "secret"
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DB
def init_db():
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT, email TEXT, password TEXT, role TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY, user_id INTEGER, filename TEXT, keywords TEXT,
            score INTEGER, cultural_score REAL)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY, user_id INTEGER, job_id INTEGER
        )''')

init_db()

@app.route('/')
def index():
    return render_template('index.html', body_class='index-bg')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        with sqlite3.connect("database.db") as conn:
            conn.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                         (name, email, password, role))
        return redirect(url_for('login'))
    return render_template('register.html', body_class='register-bg')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['name'] = user[1]
                session['role'] = user[4]
                return redirect(url_for('dashboard'))
        flash("Invalid login credentials", "danger")
    return render_template('login.html', body_class='login-bg')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session['role']
    if role == 'candidate':
        # Show jobs to apply for
        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, title, description FROM jobs ORDER BY id DESC")
            jobs = cur.fetchall()
            return render_template('jobs.html', jobs=jobs, body_class='jobs-list-bg')
    elif role in ['recruiter', 'admin']:
        name = request.args.get('name', '').lower()
        keyword = request.args.get('keyword', '').lower()
        min_score = request.args.get('min_score', '')
        max_score = request.args.get('max_score', '')

        query = """SELECT resumes.id, users.name, resumes.filename, resumes.keywords,
                          MAX(0, resumes.score - resumes.cultural_score) AS skill_score,
                          resumes.cultural_score
                   FROM resumes JOIN users ON resumes.user_id = users.id WHERE 1=1"""
        params = []
        if name:
            query += " AND lower(users.name) LIKE ?"
            params.append(f"%{name}%")
        if keyword:
            query += " AND lower(resumes.keywords) LIKE ?"
            params.append(f"%{keyword}%")
        if min_score.isdigit():
            query += " AND resumes.score >= ?"
            params.append(int(min_score))
        if max_score.isdigit():
            query += " AND resumes.score <= ?"
            params.append(int(max_score))
        query += " ORDER BY resumes.score DESC"

        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            resumes = cur.fetchall()
        return render_template('dashboard.html', resumes=resumes, body_class='dashboard-bg')
    return "Unauthorized Access"

@app.route('/upload_resume/<int:job_id>', methods=['GET', 'POST'])
def upload_resume(job_id):
    if 'user_id' not in session or session.get('role') != 'candidate':
        return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files.get('resume')
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            keywords = extract_keywords_from_pdf(filepath)

            with open(filepath, 'rb') as f:
                raw_text = f.read().decode('latin1', errors='ignore')

            with sqlite3.connect("database.db") as conn:
                cur = conn.cursor()
                cur.execute("SELECT description FROM jobs WHERE id=?", (job_id,))
                job = cur.fetchone()
                job_desc = job[0] if job else ''
                skill_score = rank_resume(job_desc, keywords)
                # Fix: Clamp cultural_score between 0 and 100, and handle errors gracefully
                try:
                    cultural_score = check_cultural_fit(raw_text)
                    if not isinstance(cultural_score, (int, float)) or cultural_score is None:
                        cultural_score = 0
                    cultural_score = max(0, min(100, float(cultural_score)))
                except Exception:
                    cultural_score = 0
                final_score = int((skill_score * 0.7) + (cultural_score * 0.3))
                cur.execute("""INSERT INTO resumes (user_id, filename, keywords, score, cultural_score)
                                VALUES (?, ?, ?, ?, ?)""", (session['user_id'], filename, keywords, final_score, cultural_score))
            flash("✅ Resume uploaded and ranked successfully!", "success")
            return redirect(url_for('dashboard'))
        flash("❌ Please upload a valid PDF file.", "danger")
    # Always return the upload page for GET or failed POST
    return render_template('upload.html', job_id=job_id, body_class='upload-bg')

@app.route('/add_job', methods=['GET', 'POST'])
def add_job():
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        with sqlite3.connect("database.db") as conn:
            conn.execute("INSERT INTO jobs (title, description) VALUES (?, ?)", (title, description))
        flash("✅ Job posted successfully!", "success")
        return redirect(url_for('add_job'))
    # Fetch all jobs to display under add job section
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, description FROM jobs ORDER BY id DESC")
        jobs_posted = cur.fetchall()
    return render_template('add_job.html', jobs_posted=jobs_posted, body_class='jobs-bg')

@app.route('/jobs')
def jobs():
    if session.get('role') != 'candidate':
        return "Unauthorized", 403
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, description FROM jobs ORDER BY id DESC")
        jobs = cur.fetchall()
    return render_template('jobs.html', jobs=jobs, body_class='jobs-list-bg')

@app.route('/apply_job/<int:job_id>', methods=['POST'])
def apply_job(job_id):
    if session.get('role') != 'candidate':
        return "Unauthorized", 403
    user_id = session['user_id']
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM job_applications WHERE user_id=? AND job_id=?", (user_id, job_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO job_applications (user_id, job_id) VALUES (?, ?)", (user_id, job_id))
            flash("✅ Applied for job successfully! Please upload your resume.", "success")
        else:
            flash("⚠️ You have already applied for this job.", "warning")
    return redirect(url_for('upload_resume', job_id=job_id))

@app.route('/export_excel')
def export_excel():
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403

    name = request.args.get('name', '').lower()
    keyword = request.args.get('keyword', '').lower()
    min_score = request.args.get('min_score', '')
    max_score = request.args.get('max_score', '')

    query = """SELECT users.name, resumes.filename, resumes.keywords,
                      MAX(0, resumes.score - resumes.cultural_score) AS skill_score,
                      resumes.cultural_score 
               FROM resumes JOIN users ON resumes.user_id = users.id WHERE 1=1"""
    params = []
    if name:
        query += " AND lower(users.name) LIKE ?"
        params.append(f"%{name}%")
    if keyword:
        query += " AND lower(resumes.keywords) LIKE ?"
        params.append(f"%{keyword}%")
    if min_score.isdigit():
        query += " AND resumes.score >= ?"
        params.append(int(min_score))
    if max_score.isdigit():
        query += " AND resumes.score <= ?"
        params.append(int(max_score))

    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        results = cur.fetchall()

    df = pd.DataFrame(results, columns=["Candidate", "Filename", "Keywords", "Skill Score", "Cultural Score"])
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name="Filtered Resumes")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="filtered_resumes.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/export_pdf')
def export_pdf():
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403

    name = request.args.get('name', '').lower()
    keyword = request.args.get('keyword', '').lower()
    min_score = request.args.get('min_score', '')
    max_score = request.args.get('max_score', '')

    query = """SELECT users.name, resumes.filename, resumes.keywords,
                      MAX(0, resumes.score - resumes.cultural_score) AS skill_score,
                      resumes.cultural_score 
               FROM resumes JOIN users ON resumes.user_id = users.id WHERE 1=1"""
    params = []
    if name:
        query += " AND lower(users.name) LIKE ?"
        params.append(f"%{name}%")
    if keyword:
        query += " AND lower(resumes.keywords) LIKE ?"
        params.append(f"%{keyword}%")
    if min_score.isdigit():
        query += " AND resumes.score >= ?"
        params.append(int(min_score))
    if max_score.isdigit():
        query += " AND resumes.score <= ?"
        params.append(int(max_score))

    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        results = cur.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Filtered Resumes Report", ln=True, align='C')
    pdf.ln(10)
    for row in results:
        pdf.cell(200, 10, txt=f"Name: {row[0]}, File: {row[1]}, Skill Score: {row[3]}, Cultural Fit: {row[4]}", ln=True)
    output = BytesIO()
    output.write(pdf.output(dest='S').encode('latin1'))
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="filtered_resumes.pdf", mimetype="application/pdf")

@app.route('/delete_resume/<int:resume_id>', methods=['POST'])
def delete_resume(resume_id):
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403
    with sqlite3.connect("database.db") as conn:
        conn.execute("DELETE FROM resumes WHERE id=?", (resume_id,))
    flash("✅ Resume deleted successfully.", "success")
    return redirect(url_for('dashboard'))

@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403
    selected_ids = request.form.get('resume_ids', '').split(',')
    selected_ids = [id for id in selected_ids if id]
    if selected_ids:
        placeholders = ",".join("?" * len(selected_ids))
        with sqlite3.connect("database.db") as conn:
            conn.execute(f"DELETE FROM resumes WHERE id IN ({placeholders})", selected_ids)
        flash("✅ Selected resumes deleted successfully.", "success")
    else:
        flash("❌ No resumes selected.", "danger")
    return redirect(url_for('dashboard'))

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/job_candidates/<int:job_id>')
def job_candidates(job_id):
    if session.get('role') not in ['admin', 'recruiter']:
        return "Unauthorized", 403
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute('''SELECT users.name, users.email FROM job_applications
                       JOIN users ON job_applications.user_id = users.id
                       JOIN resumes ON resumes.user_id = users.id AND resumes.rowid = (
                           SELECT MAX(rowid) FROM resumes WHERE user_id = users.id
                       )
                       WHERE job_applications.job_id = ?''', (job_id,))
        candidates = cur.fetchall()
        cur.execute('SELECT title FROM jobs WHERE id=?', (job_id,))
        job = cur.fetchone()
        job_title = job[0] if job else 'Unknown'
    return render_template('job_candidates.html', candidates=candidates, job_title=job_title)

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)