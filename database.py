import sqlite3, os, re
from datetime import date, datetime, timezone
DB = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "career_database.db"))
ALIASES = {"js":"javascript","ml":"machine learning","dl":"deep learning","nodejs":"node.js","reactjs":"react","react.js":"react",
 "postgres":"postgresql","powerbi":"power bi","k8s":"kubernetes","ci cd":"ci/cd","natural language processing":"nlp","large language models":"llms","llm":"llms"}
def norm(s):
    s = re.sub(r"\s+", " ", s.strip().lower()); return ALIASES.get(s, s)
def get_db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
SCHEMA = """
CREATE TABLE IF NOT EXISTS careers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE COLLATE NOCASE NOT NULL, description TEXT, category TEXT,
 education TEXT, experience TEXT, status TEXT DEFAULT 'Active', updated TEXT);
CREATE TABLE IF NOT EXISTS career_skills(id INTEGER PRIMARY KEY AUTOINCREMENT, career_id INTEGER NOT NULL REFERENCES careers(id) ON DELETE CASCADE, skill TEXT NOT NULL, weight INTEGER DEFAULT 3);
CREATE TABLE IF NOT EXISTS career_roles(id INTEGER PRIMARY KEY AUTOINCREMENT, career_id INTEGER NOT NULL REFERENCES careers(id) ON DELETE CASCADE, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_resources(id INTEGER PRIMARY KEY AUTOINCREMENT, skill TEXT, topic TEXT, practice TEXT, project TEXT, outcome TEXT, link TEXT);
"""
SEED = """Data Scientist|Data & AI|Python,Statistics,Machine Learning,Pandas,SQL,Data Visualization
Data Analyst|Data & AI|Excel,SQL,Power BI,Data Visualization,Statistics,Python
Machine Learning Engineer|Data & AI|Python,Machine Learning,Deep Learning,TensorFlow,Docker,Git
AI Engineer|Data & AI|Python,Deep Learning,NLP,PyTorch,APIs,Machine Learning
Data Engineer|Data & AI|Python,SQL,ETL,Apache Spark,Airflow,AWS
Web Developer|Software|HTML,CSS,JavaScript,React,Git,APIs
Frontend Developer|Software|HTML,CSS,JavaScript,React,TypeScript,Responsive Design
Backend Developer|Software|Python,Node.js,SQL,APIs,Databases,Git
Full Stack Developer|Software|JavaScript,React,Node.js,SQL,APIs,Git
Mobile App Developer|Software|Kotlin,Flutter,Java,APIs,Git,UI Design
Software Engineer|Software|Java,Data Structures,Algorithms,OOP,Git,SQL
Game Developer|Software|C++,Unity,C#,Game Design,3D Math,Git
DevOps Engineer|Cloud & Infra|Linux,Docker,Kubernetes,CI/CD,Git,AWS
Cloud Engineer|Cloud & Infra|AWS,Azure,Linux,Networking,Docker,Terraform
Database Administrator|Cloud & Infra|SQL,MySQL,PostgreSQL,Database Design,Backup and Recovery,Linux
Cybersecurity Analyst|Security|Networking,Linux,Cybersecurity,Ethical Hacking,SIEM,Python
UI/UX Designer|Design|Figma,UI Design,UX Research,Wireframing,Prototyping,Adobe XD
Embedded Systems Engineer|Emerging Tech|C,C++,Microcontrollers,RTOS,Electronics,Python
IoT Developer|Emerging Tech|Python,Arduino,Raspberry Pi,MQTT,Networking,C
Blockchain Developer|Emerging Tech|Solidity,Ethereum,Cryptography,JavaScript,Smart Contracts,Git
QA Engineer|Quality & Docs|Manual Testing,Selenium,Test Automation,Java,SQL,Jira
Technical Writer|Quality & Docs|Technical Writing,Documentation,Markdown,Git,APIs,Communication
Business Analyst|Business|Excel,SQL,Requirements Analysis,Power BI,Communication,Documentation
Digital Marketer|Business|SEO,Content Marketing,Google Analytics,Social Media,Email Marketing,Copywriting
Product Manager|Business|Product Strategy,Roadmapping,Agile,Communication,Data Analysis,Jira"""
def parse_skills(text):
    out, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        name, w = line, 3
        if ":" in line:
            n, _, ws = line.rpartition(":")
            if ws.strip().isdigit(): name, w = n.strip(), max(1, min(5, int(ws)))
        if name and norm(name) not in seen: seen.add(norm(name)); out.append((name, w))
    return out
def parse_roles(text): return list(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip()))
def save_career(db, cid, form):
    name = form.get("name", "").strip()
    if not name: raise ValueError("Career name is required.")
    skills = parse_skills(form.get("skills", ""))
    if not skills: raise ValueError("Add at least one required skill (one per line, e.g. Python:5).")
    vals = (name, form.get("description", "").strip(), form.get("category", "").strip() or "Other", form.get("education", "").strip(),
            form.get("experience", "").strip(), form.get("status", "Active"), date.today().isoformat())
    try:
        if cid is None:
            cid = db.execute("INSERT INTO careers(name,description,category,education,experience,status,updated) VALUES(?,?,?,?,?,?,?)", vals).lastrowid
        else:
            db.execute("UPDATE careers SET name=?,description=?,category=?,education=?,experience=?,status=?,updated=? WHERE id=?", vals + (cid,))
            db.execute("DELETE FROM career_skills WHERE career_id=?", (cid,)); db.execute("DELETE FROM career_roles WHERE career_id=?", (cid,))
        db.executemany("INSERT INTO career_skills(career_id,skill,weight) VALUES(?,?,?)", [(cid, s, w) for s, w in skills])
        db.executemany("INSERT INTO career_roles(career_id,title) VALUES(?,?)", [(cid, t) for t in parse_roles(form.get("roles", ""))])
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback(); raise ValueError("A career with this name already exists.")
def vocabulary(db):
    return {norm(r["skill"]): r["skill"] for r in db.execute("SELECT DISTINCT skill FROM career_skills")}
def init_db():
    db = get_db(); db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM careers").fetchone():
        for line in SEED.splitlines():
            n, cat, sk = [x.strip() for x in line.split("|")]
            save_career(db, None, {"name": n, "category": cat, "description": f"{n} professionals work in the {cat} domain.",
              "education": "Bachelor's degree in a related field", "experience": "Entry level to mid level",
              "skills": "\n".join(f"{s}:{max(2, 5 - i // 2)}" for i, s in enumerate(sk.split(","))),
              "roles": "\n".join([f"Junior {n}", n, f"Associate {n}", f"{n} Trainee", f"{n} Consultant"])})
    db.commit(); db.close()
