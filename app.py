import os, re, json, uuid
from flask import Flask, render_template, request, flash, redirect, url_for, session
from apscheduler.schedulers.background import BackgroundScheduler
import database as D, recommendation as R, resume_parser as P, career_sync as CS

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', 'local-career-navigator-key'), MAX_CONTENT_LENGTH=5*1024*1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
D.init_db()
# Check ESCO and India-eligible remote job postings once every 24 hours.
# These checks run when the app starts; a restart/deploy may trigger an early check,
# while the stored timestamps prevent repeated checks inside each interval.
# If a source is unavailable, the existing application continues to work.
try:
    CS.sync_occupations(D.DB)
    CS.sync_job_market_careers(D.DB)
except Exception:
    pass

# Keep periodic checks running while the web process remains alive. The first
# check happens at startup above; these jobs perform subsequent checks.
try:
    _career_scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _career_scheduler.add_job(CS.sync_job_market_careers, "interval", hours=24,
                              args=[D.DB], id="daily_job_market_discovery",
                              replace_existing=True, max_instances=1)
    _career_scheduler.add_job(CS.sync_occupations, "interval", hours=24,
                              args=[D.DB], id="daily_esco_occupation_sync",
                              replace_existing=True, max_instances=1)
    _career_scheduler.start()
except Exception:
    # Scheduling must never prevent the career application from starting.
    _career_scheduler = None

# Persist analyzed profiles on the server so dashboard tools can reuse them.
_profile_db = D.get_db()
_profile_db.execute('CREATE TABLE IF NOT EXISTS analyzed_profiles (profile_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
_profile_db.commit(); _profile_db.close()
LEVELS = ['Fresher', '1-2 years', '3-5 years', '5+ years']

# Soft skills are reported separately so they do not reduce the technical match score.
SOFT_SKILLS = {
    'communication', 'teamwork', 'leadership', 'time management', 'adaptability',
    'problem solving', 'problem-solving', 'critical thinking', 'creativity',
    'collaboration', 'interpersonal skills', 'presentation skills', 'work ethic',
    'attention to detail', 'decision making', 'decision-making', 'customer service',
    'negotiation', 'conflict resolution', 'flexibility', 'organization',
    'organizational skills', 'self motivation', 'self-motivation'
}

PROJECTS = {
 'python': [
  ('Expense Tracker', 'Beginner', ['Python', 'File handling'], 'Record income and expenses, categorize spending, and show monthly totals.', 'A working command-line or simple desktop expense tracker.'),
  ('Student Management System', 'Intermediate', ['Python', 'SQL', 'OOP'], 'Create, update, search, and delete student records using a database.', 'A CRUD application with database integration.'),
  ('Flask Job Portal', 'Advanced', ['Python', 'Flask', 'SQL', 'HTML', 'CSS'], 'Build a portal with job listings, search, and user application tracking.', 'A deployed full-stack Flask application.')],
 'data analyst': [
  ('Sales Dashboard', 'Beginner', ['Excel', 'Data Analysis', 'Data Visualization'], 'Clean sales data and present monthly revenue and product insights.', 'A dashboard with clear business metrics.'),
  ('SQL Business Analysis', 'Intermediate', ['SQL', 'MySQL', 'Statistics'], 'Analyze customer and sales tables using joins, grouping, and subqueries.', 'A set of documented business insights and SQL queries.'),
  ('Customer Churn Analysis', 'Advanced', ['Python', 'Pandas', 'Statistics', 'Power BI'], 'Explore churn patterns and build an interactive analysis dashboard.', 'A reproducible analysis with visual findings.')],
 'web developer': [
  ('Personal Portfolio', 'Beginner', ['HTML', 'CSS', 'JavaScript'], 'Create a responsive portfolio with projects and contact details.', 'A published personal portfolio website.'),
  ('Task Manager', 'Intermediate', ['JavaScript', 'React', 'APIs'], 'Build a task app with create, edit, filter, and completion features.', 'A responsive task management application.'),
  ('E-commerce Website', 'Advanced', ['React', 'Node.js', 'SQL', 'APIs'], 'Build product browsing, cart, and order workflows.', 'A full-stack e-commerce prototype.')],
 'machine learning engineer': [
  ('House Price Prediction', 'Beginner', ['Python', 'Pandas', 'Machine Learning'], 'Train and evaluate a regression model on housing data.', 'A documented ML notebook with evaluation metrics.'),
  ('Customer Segmentation', 'Intermediate', ['Python', 'Machine Learning', 'Statistics'], 'Group customers using clustering and explain the segments.', 'A clustering analysis with visualizations.'),
  ('Model API Deployment', 'Advanced', ['Python', 'Flask', 'Docker', 'APIs'], 'Serve a trained model through an API and package it for deployment.', 'A tested model inference API.')],
 'ui/ux designer': [
  ('Mobile App Wireframe', 'Beginner', ['Figma', 'Wireframing'], 'Design key screens and user flows for a simple mobile app.', 'A clickable low-fidelity prototype.'),
  ('Usability Redesign', 'Intermediate', ['Figma', 'UX Research', 'Prototyping'], 'Review an existing interface and redesign it based on user needs.', 'A case study with before-and-after screens.'),
  ('End-to-End Product Case Study', 'Advanced', ['Figma', 'UX Research', 'UI Design'], 'Research a problem, define personas, prototype, and test a product flow.', 'A complete portfolio-ready UX case study.')]
}

def get_profile_skills():
    raw = request.values.get('skills', '')
    return [s.strip() for s in re.split(r'[,;\n]', raw) if s.strip()]

def extract_required_skills(text, vocab):
    low = ' ' + re.sub(r'[^a-z0-9+#./ -]', ' ', text.lower()) + ' '
    found = []
    for key, display in vocab.items():
        pattern = r'(?<![a-z0-9])' + re.escape(key) + r'(?![a-z0-9])'
        if re.search(pattern, low):
            found.append(display)
    return sorted(set(found), key=str.lower)

def save_analyzed_profile(payload):
    profile_id = session.get('profile_id') or uuid.uuid4().hex
    db = D.get_db()
    try:
        db.execute('INSERT OR REPLACE INTO analyzed_profiles(profile_id, payload) VALUES(?,?)',
                   (profile_id, json.dumps(payload)))
        db.commit()
    finally:
        db.close()
    session['profile_id'] = profile_id
    session['profile_skills'] = payload.get('skills', [])
    session['profile_career'] = payload.get('career', '')
    session['profile_name'] = payload.get('name', '')


def load_analyzed_profile():
    profile_id = session.get('profile_id')
    if not profile_id:
        return None
    db = D.get_db()
    try:
        row = db.execute('SELECT payload FROM analyzed_profiles WHERE profile_id=?', (profile_id,)).fetchone()
        return json.loads(row['payload']) if row else None
    finally:
        db.close()


def render_saved_analysis():
    profile = load_analyzed_profile()
    if not profile:
        session.pop('profile_id', None)
        return redirect(url_for('index'))
    db = D.get_db()
    try:
        recs = R.recommend(db, profile['skills'])
        roadmap = R.roadmap(db, recs[:3])
        for r in recs:
            roles = db.execute('SELECT title FROM career_roles WHERE career_id=? ORDER BY id LIMIT 6', (r['id'],)).fetchall()
            r['roles'] = [x['title'] for x in roles]
    finally:
        db.close()
    ready = R.readiness(profile['skills'], profile['education'], profile['experience'], recs[0] if recs else None, profile['resume_text'])
    quality = R.resume_quality(profile['resume_text'], len(profile['resume_skills']))
    guide = R.guidance(profile['name'], profile['education'], profile['experience'], recs, ready)
    return render_template('result.html', name=profile['name'], edu=profile['education'], exp=profile['experience'],
        manual=profile['manual'], rskills=profile['resume_skills'], skills=profile['skills'], recs=recs,
        roadmap=roadmap, quality=quality, ready=ready, guide=guide)


@app.route('/')
def index():
    # The home page is only the profile and resume input form.
    return render_template('index.html', form={}, levels=LEVELS)

@app.route('/career-analysis')
def career_analysis():
    return redirect(url_for('analyze_dashboard') if session.get('profile_id') else url_for('index'))

@app.errorhandler(413)
def too_big(e):
    flash('The file is too large. Maximum size is 5 MB.', 'danger')
    return render_template('index.html', form={}, levels=LEVELS), 413

@app.errorhandler(500)
def err(e):
    return render_template('error.html'), 500

@app.post('/analyze')
def analyze():
    f = request.form
    name, edu, exp, raw = f.get('name','').strip(), f.get('education','').strip(), f.get('experience',''), f.get('skills','').strip()
    file = request.files.get('resume'); errs = []
    if not name: errs.append('Full name is required.')
    if not edu: errs.append('Education is required.')
    if not raw: errs.append('Enter at least one skill.')
    if exp not in LEVELS: errs.append('Select an experience level.')
    if not file or not file.filename: errs.append('A PDF resume is required.')
    elif not file.filename.lower().endswith('.pdf'): errs.append('Resume must be a PDF file.')
    text = ''
    if not errs:
        try: text = P.extract_text(file.read())
        except ValueError as e: errs.append(str(e))
    if errs:
        for e in errs: flash(e, 'danger')
        return render_template('index.html', form=f, levels=LEVELS), 400
    db = D.get_db()
    try:
        vocab = D.vocabulary(db); rsk = P.find_skills(text, vocab)
        manual = [s.strip() for s in re.split(r'[,;\n]', raw) if s.strip()]
        combined = {}
        for s in manual + rsk: combined.setdefault(D.norm(s), vocab.get(D.norm(s), s))
        skills = sorted(combined.values(), key=str.lower)
        recs = R.recommend(db, skills); rm = R.roadmap(db, recs[:3])
        for r in recs:
            roles = db.execute('SELECT title FROM career_roles WHERE career_id=? ORDER BY id LIMIT 6', (r['id'],)).fetchall()
            r['roles'] = [x['title'] for x in roles]
    finally: db.close()
    rd = R.readiness(skills, edu, exp, recs[0] if recs else None, text)
    # Save the submitted profile in SQLite; dashboard tools reuse it without asking again.
    save_analyzed_profile({'name': name, 'education': edu, 'experience': exp, 'manual': manual,
                           'resume_skills': rsk, 'skills': skills, 'resume_text': text,
                           'career': recs[0]['name'] if recs else ''})
    return render_saved_analysis()

@app.route('/job-matcher', methods=['GET','POST'])
def job_matcher():
    result = None
    skills = get_profile_skills() or session.get('profile_skills', [])
    if request.method == 'POST':
        jd = request.form.get('job_description','').strip()
        if not jd:
            flash('Paste a job description before matching.', 'danger')
        elif not skills:
            flash('Enter your skills, separated by commas.', 'danger')
        else:
            db = D.get_db()
            try: vocab = D.vocabulary(db)
            finally: db.close()
            # Soft skills are excluded completely: they are not matched, counted,
            # or displayed. Only technical skills contribute to the percentage.
            soft_norm = {D.norm(s) for s in SOFT_SKILLS}
            required = [s for s in extract_required_skills(jd, vocab) if D.norm(s) not in soft_norm]
            if not required:
                flash('No recognised technical skills were detected in this job description. Add technical requirements such as Python, SQL, JavaScript, or HTML.', 'warning')
            else:
                user = {D.norm(s) for s in skills if D.norm(s) not in soft_norm}
                matched = [s for s in required if D.norm(s) in user]
                missing = [s for s in required if D.norm(s) not in user]
                pct = round(100 * len(matched) / len(required))
                result = {'matched': matched, 'missing': missing, 'pct': pct,
                          'count': len(required), 'has_technical': True}
    return render_template('job_matcher.html', skills=', '.join(skills), result=result)

@app.route('/projects')
def projects():
    career = request.args.get('career','').strip() or session.get('profile_career', '')
    skills = [s.strip() for s in request.args.get('skills','').split(',') if s.strip()] or session.get('profile_skills', [])
    key = D.norm(career)
    chosen = None
    for k, items in PROJECTS.items():
        if k in key or key in k: chosen = items; break
    if chosen is None:
        chosen = [
          ('Skill Showcase Website', 'Beginner', skills[:3] or ['HTML','CSS','JavaScript'], 'Create a small website that demonstrates your strongest skills and explains each project.', 'A shareable portfolio page.'),
          ('Career-Based Management App', 'Intermediate', skills[:4] or ['Python','SQL','OOP'], f'Build an application related to {career or "your target career"}, with data storage and search.', 'A functional application with a README and screenshots.'),
          ('End-to-End Capstone Project', 'Advanced', skills[:5] or ['Python','APIs','SQL','Git'], f'Design and build a complete solution that demonstrates the core work of a {career or "target role"}.', 'A tested, documented GitHub project.')]
    return render_template('projects.html', career=career or 'Your selected career', skills=skills, projects=chosen)

@app.route('/new-analysis')
def new_analysis():
    session.pop('profile_id', None)
    session.pop('profile_skills', None)
    session.pop('profile_career', None)
    session.pop('profile_name', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    return render_saved_analysis()

@app.route('/career-dashboard')
def analyze_dashboard():
    return render_saved_analysis()

if __name__ == '__main__': app.run(debug=False)
