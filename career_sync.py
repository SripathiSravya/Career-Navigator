"""Import new occupations from the public European Commission ESCO dataset.
No API key or account is required. Imported records are deduplicated by name.
"""
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://ec.europa.eu/esco/api/search"
ESCO_SYNC_INTERVAL_HOURS = 24


def _text(value):
    if isinstance(value, str):
        return re.sub(r"<[^>]+>", " ", value).strip()
    if isinstance(value, dict):
        return _text(value.get("literal") or value.get("value") or value.get("label") or "")
    return ""


def _items(payload):
    embedded = payload.get("_embedded", {}) if isinstance(payload, dict) else {}
    if isinstance(embedded, dict):
        for value in embedded.values():
            if isinstance(value, list):
                return value
    for key in ("results", "items", "concepts"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def sync_occupations(db_path, force=False):
    """Fetch a page of ESCO occupations at most once every 24 hours and add usable new careers.

    The source is a European occupation classification, not an India-only
    vacancy feed. Only records whose descriptions map to existing technical
    skills are imported, so recommendations have meaningful skill data.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS career_sync_state (source TEXT PRIMARY KEY, last_sync TEXT, imported INTEGER DEFAULT 0, status TEXT)")
        row = conn.execute("SELECT last_sync FROM career_sync_state WHERE source='ESCO'").fetchone()
        if not force and row and row["last_sync"]:
            try:
                last = datetime.fromisoformat(row["last_sync"])
                if datetime.now(timezone.utc) - last < timedelta(hours=ESCO_SYNC_INTERVAL_HOURS):
                    return {"status": "recent", "imported": 0}
            except ValueError:
                pass

        params = urllib.parse.urlencode({
            "language": "en", "type": "Occupation", "offset": 0,
            "limit": 100, "full": "true", "selectedVersion": "1.2.0",
            "viewObsolete": "false"
        })
        request = urllib.request.Request(
            API_URL + "?" + params,
            headers={"Accept": "application/json", "User-Agent": "CareerNavigator/1.0"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        vocab_rows = conn.execute("SELECT DISTINCT skill FROM career_skills").fetchall()
        vocab = [r["skill"] for r in vocab_rows]
        imported = 0
        for item in _items(payload):
            name = _text(item.get("preferredLabel") or item.get("title") or item.get("label") or item.get("name"))
            description = _text(item.get("description") or item.get("definition") or "")
            if not name or len(name) > 120:
                continue
            # Avoid importing non-occupation fragments and records with no
            # usable technical-skill overlap in the current recommendation DB.
            searchable = (name + " " + description).lower()
            matched = []
            for skill in vocab:
                pattern = r"(?<![a-z0-9])" + re.escape(skill.lower()) + r"(?![a-z0-9])"
                if skill and re.search(pattern, searchable):
                    matched.append(skill)
            if not matched:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO careers(name,description,category,education,experience,status,updated) VALUES(?,?,?,?,?,?,?)",
                (name, description or "Occupation imported from the ESCO classification.",
                 "Imported Occupation", "Related qualification or equivalent skills", "Varies by role", "Active", datetime.now(timezone.utc).date().isoformat())
            )
            if cur.rowcount:
                career_id = cur.lastrowid
                conn.executemany(
                    "INSERT INTO career_skills(career_id,skill,weight) VALUES(?,?,?)",
                    [(career_id, skill, 3) for skill in matched]
                )
                conn.execute("INSERT INTO career_roles(career_id,title) VALUES(?,?)", (career_id, name))
                imported += 1

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO career_sync_state(source,last_sync,imported,status) VALUES('ESCO',?,?,?)",
                     (now, imported, "success"))
        conn.commit()
        return {"status": "success", "imported": imported}
    except Exception as exc:
        conn.execute("CREATE TABLE IF NOT EXISTS career_sync_state (source TEXT PRIMARY KEY, last_sync TEXT, imported INTEGER DEFAULT 0, status TEXT)")
        conn.execute("INSERT OR REPLACE INTO career_sync_state(source,last_sync,imported,status) VALUES('ESCO',?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), 0, "error: " + str(exc)[:300]))
        conn.commit()
        return {"status": "error", "imported": 0, "message": str(exc)}
    finally:
        conn.close()


# Daily discovery from Himalayas' public remote-jobs API. This is a remote-job
# source, not a complete India-wide job-market feed. The API supports country=IN
# and requires no key. We only create career records when at least two known
# technical skills appear in the title/description.
JOB_API_URL = "https://himalayas.app/jobs/api/search"
JOB_SYNC_INTERVAL_HOURS = 24
SOFT_SKILLS = {
    "communication", "teamwork", "leadership", "time management", "adaptability",
    "problem solving", "problem-solving", "critical thinking", "creativity",
    "collaboration", "interpersonal skills", "presentation skills", "work ethic",
    "attention to detail", "decision making", "decision-making", "customer service",
    "negotiation", "conflict resolution", "flexibility", "organization",
    "organizational skills", "self motivation", "self-motivation"
}

def sync_job_market_careers(db_path, force=False):
    """Daily import of eligible career titles seen in India-eligible remote jobs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS career_sync_state (source TEXT PRIMARY KEY, last_sync TEXT, imported INTEGER DEFAULT 0, status TEXT)")
        row = conn.execute("SELECT last_sync FROM career_sync_state WHERE source='HIMALAYAS_IN' ").fetchone()
        if not force and row and row["last_sync"]:
            try:
                last = datetime.fromisoformat(row["last_sync"])
                if datetime.now(timezone.utc) - last < timedelta(hours=JOB_SYNC_INTERVAL_HOURS):
                    return {"status": "recent", "imported": 0}
            except ValueError:
                pass

        params = urllib.parse.urlencode({"country": "IN", "sort": "recent", "page": 1})
        req = urllib.request.Request(JOB_API_URL + "?" + params, headers={
            "Accept": "application/json", "User-Agent": "CareerNavigator/1.0 (career discovery)"})
        with urllib.request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))

        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        vocab_rows = conn.execute("SELECT DISTINCT skill FROM career_skills").fetchall()
        vocab = [r["skill"] for r in vocab_rows if r["skill"].strip().lower() not in SOFT_SKILLS]
        imported = 0
        for job in jobs:
            title = _text(job.get("title") or job.get("name"))
            description = _text(job.get("description") or "")
            if not title or len(title) > 120:
                continue
            searchable = (title + " " + description).lower()
            matched = []
            for skill in vocab:
                if not skill or skill.lower() in SOFT_SKILLS:
                    continue
                pattern = r"(?<![a-z0-9])" + re.escape(skill.lower()) + r"(?![a-z0-9])"
                if re.search(pattern, searchable):
                    matched.append(skill)
            # Avoid creating careers from vague job ads with weak skill evidence.
            if len(set(x.lower() for x in matched)) < 2:
                continue
            clean_title = re.sub(r"\s+", " ", title).strip()
            cur = conn.execute(
                "INSERT OR IGNORE INTO careers(name,description,category,education,experience,status,updated) VALUES(?,?,?,?,?,?,?)",
                (clean_title, (description[:1800] or "Career title identified from India-eligible remote job postings.") + "\nSource: Himalayas public remote jobs feed.",
                 "Emerging Remote Career", "Related qualification or equivalent skills",
                 job.get("seniority") or "Varies by role", "Active", datetime.now(timezone.utc).date().isoformat())
            )
            if cur.rowcount:
                cid = cur.lastrowid
                conn.executemany("INSERT INTO career_skills(career_id,skill,weight) VALUES(?,?,?)",
                                 [(skill, 3) for skill in sorted(set(matched), key=str.lower)])
                conn.execute("INSERT INTO career_roles(career_id,title) VALUES(?,?)", (cid, clean_title))
                imported += 1

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO career_sync_state(source,last_sync,imported,status) VALUES('HIMALAYAS_IN',?,?,?)",
                     (now, imported, "success"))
        conn.commit()
        return {"status": "success", "imported": imported, "jobs_checked": len(jobs)}
    except Exception as exc:
        conn.execute("CREATE TABLE IF NOT EXISTS career_sync_state (source TEXT PRIMARY KEY, last_sync TEXT, imported INTEGER DEFAULT 0, status TEXT)")
        conn.execute("INSERT OR REPLACE INTO career_sync_state(source,last_sync,imported,status) VALUES('HIMALAYAS_IN',?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), 0, "error: " + str(exc)[:300]))
        conn.commit()
        return {"status": "error", "imported": 0, "message": str(exc)}
    finally:
        conn.close()
