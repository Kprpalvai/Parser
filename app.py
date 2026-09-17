from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tracker.db")))
STATIC_DIR = BASE_DIR / "static"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Job Application Tracker", version="1.0.0")

STOPWORDS = {
    "a","an","and","are","as","at","be","been","being","but","by","can","could","did","do","does","for","from",
    "had","has","have","he","her","here","hers","him","his","how","i","if","in","into","is","it","its","may","me",
    "more","most","must","my","no","not","of","on","or","our","ours","shall","she","should","so","some","such",
    "than","that","the","their","theirs","them","then","there","these","they","this","those","to","too","us","very",
    "was","we","were","what","when","where","which","while","who","why","will","with","would","you","your","yours",
    "job","role","work","working","team","teams","company","years","year","experience","preferred","required","requirements",
    "responsibilities","responsibility","skills","skill","candidate","candidates","position","including","using","across","within"
}

SKILL_PHRASES = [
    "python", "sql", "excel", "tableau", "power bi", "looker", "snowflake", "bigquery", "aws", "azure", "gcp",
    "machine learning", "deep learning", "natural language processing", "nlp", "generative ai", "llm", "large language models",
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "spark", "databricks", "airflow", "dbt", "kafka",
    "product management", "roadmap", "agile", "scrum", "jira", "figma", "a/b testing", "experimentation", "statistics",
    "data analysis", "data analytics", "data visualization", "forecasting", "financial modeling", "salesforce", "hubspot",
    "javascript", "typescript", "react", "next.js", "node.js", "java", "c++", "c#", "go", "kubernetes", "docker",
    "terraform", "git", "github", "rest api", "graphql", "microservices", "system design", "cybersecurity", "linux",
    "stakeholder management", "project management", "program management", "leadership", "communication", "presentation"
]

STATUS_VALUES = ["Saved", "Applied", "Recruiter Screen", "Interview", "Final Round", "Offer", "Rejected", "Withdrawn"]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#./-]{1,}", (text or "").lower())
    return [w.strip("./-") for w in words if len(w) > 2 and w not in STOPWORDS]


def extract_keywords(text: str, limit: int = 28) -> list[str]:
    lower = (text or "").lower()
    phrases = [p for p in SKILL_PHRASES if p in lower]
    counts = Counter(tokenize(text))
    single = [w for w, _ in counts.most_common(50) if w not in phrases]
    out = []
    for item in phrases + single:
        if item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def ats_analysis(resume: str, description: str) -> dict:
    jd_keywords = extract_keywords(description, 30)
    resume_lower = (resume or "").lower()
    matched = [k for k in jd_keywords if k in resume_lower]
    missing = [k for k in jd_keywords if k not in resume_lower]

    if not jd_keywords:
        score = 0
    else:
        weighted_total = 0.0
        weighted_match = 0.0
        for k in jd_keywords:
            weight = 2.3 if k in SKILL_PHRASES else 1.0
            weighted_total += weight
            if k in resume_lower:
                weighted_match += weight
        score = round(100 * weighted_match / max(weighted_total, 1), 0)

    evidence_bonus = 0
    if re.search(r"\b\d+(?:\.\d+)?%", resume or ""):
        evidence_bonus += 3
    if re.search(r"\b(led|built|improved|increased|reduced|launched|delivered|owned|designed|implemented)\b", (resume or "").lower()):
        evidence_bonus += 3
    score = int(min(100, score + evidence_bonus))

    suggestions = []
    top_missing = missing[:8]
    if top_missing:
        suggestions.append("Add truthful evidence for these high-value terms where relevant: " + ", ".join(top_missing[:6]) + ".")
    if not re.search(r"\b\d+(?:\.\d+)?%|\$\d|\b\d+x\b", resume or ""):
        suggestions.append("Quantify 2–4 bullets with measurable impact (%, $, time saved, scale, latency, revenue, users, or volume).")
    if description and resume:
        title_terms = extract_keywords(description, 8)
        suggestions.append("Mirror the job's language in your summary and most relevant recent role, especially: " + ", ".join(title_terms[:4]) + ".")
    suggestions.append("Keep keywords inside natural accomplishment bullets; do not keyword-stuff or claim tools you have not used.")

    return {"score": score, "matched": matched[:12], "missing": missing[:12], "suggestions": suggestions[:4]}


def people_strategy(company: str, title: str) -> dict:
    q_hm = quote_plus(f'{company} "{title}" hiring manager')
    q_team = quote_plus(f'{company} {title}')
    q_alumni = quote_plus(f'{company} alumni {title}')
    return {
        "hiring_manager_hint": f"Target the manager/director leading the {title} function at {company}; verify ownership before contacting.",
        "referral_hint": f"Prioritize 1st/2nd-degree connections, alumni, former coworkers, and team members at {company} before cold outreach.",
        "searches": [
            {"label": "LinkedIn hiring-manager search", "url": f"https://www.linkedin.com/search/results/people/?keywords={q_hm}"},
            {"label": "LinkedIn team search", "url": f"https://www.linkedin.com/search/results/people/?keywords={q_team}"},
            {"label": "Google alumni/referral search", "url": f"https://www.google.com/search?q={q_alumni}"},
        ],
    }


def init_db():
    conn = connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Saved',
            applied_date TEXT DEFAULT '',
            source TEXT DEFAULT '',
            apply_url TEXT DEFAULT '',
            salary TEXT DEFAULT '',
            job_description TEXT DEFAULT '',
            resume_text TEXT DEFAULT '',
            ats_score INTEGER DEFAULT 0,
            matched_keywords TEXT DEFAULT '[]',
            missing_keywords TEXT DEFAULT '[]',
            suggestions TEXT DEFAULT '[]',
            hiring_manager_name TEXT DEFAULT '',
            hiring_manager_url TEXT DEFAULT '',
            referral_name TEXT DEFAULT '',
            referral_url TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    if count == 0:
        samples = [
            {
                "company": "Northstar Analytics", "title": "Senior Data Analyst", "location": "Remote / US",
                "status": "Applied", "applied_date": "2026-09-11", "source": "Company Careers", "apply_url": "https://example.com/jobs/northstar-data-analyst",
                "salary": "$120k–$145k", "job_description": "Senior Data Analyst responsible for SQL, Python, Tableau, experimentation, statistics, stakeholder management, forecasting, data visualization and executive presentation. Build dashboards and translate business questions into measurable insights.",
                "resume_text": "Data analyst with 5 years of experience using SQL, Python, Tableau and Excel. Built executive dashboards, automated reporting, led stakeholder reviews, and improved reporting turnaround by 40%. Experienced in forecasting and data visualization.",
                "hiring_manager_name": "", "hiring_manager_url": "", "referral_name": "", "referral_url": "", "notes": "Tailor analytics bullets before recruiter follow-up."
            },
            {
                "company": "Atlas AI", "title": "Product Manager, Generative AI", "location": "San Francisco, CA",
                "status": "Recruiter Screen", "applied_date": "2026-09-08", "source": "Referral", "apply_url": "https://example.com/jobs/atlas-genai-pm",
                "salary": "$155k–$190k", "job_description": "Product Manager for generative AI products. Own product roadmap, customer discovery, experimentation, A/B testing, stakeholder management, LLM evaluation, analytics, agile execution, and launch strategy. Partner with engineering and design.",
                "resume_text": "Product manager with experience owning roadmap, agile delivery, customer discovery and cross-functional launches. Led A/B testing that increased activation 18%. Partnered with engineering, design, analytics and executive stakeholders. Built an internal generative AI pilot using large language models.",
                "hiring_manager_name": "Maya Chen", "hiring_manager_url": "https://www.linkedin.com", "referral_name": "Jordan Lee", "referral_url": "https://www.linkedin.com", "notes": "Prepare LLM evaluation examples for screen."
            },
            {
                "company": "Orbit Commerce", "title": "Business Intelligence Engineer", "location": "Los Angeles, CA",
                "status": "Saved", "applied_date": "", "source": "Job Board", "apply_url": "https://example.com/jobs/orbit-bi-engineer",
                "salary": "$110k–$135k", "job_description": "Business Intelligence Engineer using SQL, dbt, Snowflake, Tableau, Python and data modeling. Develop trusted datasets, KPI definitions, dashboards, stakeholder reporting, and automated pipelines.",
                "resume_text": "Analytics professional skilled in SQL, Python, Tableau and stakeholder reporting. Built KPI dashboards and automated recurring analysis. Created data models for executive reporting and improved dashboard adoption across teams.",
                "hiring_manager_name": "", "hiring_manager_url": "", "referral_name": "", "referral_url": "", "notes": "Need stronger data engineering/tooling alignment."
            },
            {
                "company": "Crescent Health", "title": "Strategy & Operations Manager", "location": "New York, NY",
                "status": "Interview", "applied_date": "2026-09-02", "source": "LinkedIn", "apply_url": "https://example.com/jobs/crescent-strategy-ops",
                "salary": "$135k–$165k", "job_description": "Strategy and Operations Manager. Lead strategic planning, financial modeling, forecasting, program management, stakeholder management, analytics, executive presentation and cross-functional initiatives. Track KPIs and improve operational performance.",
                "resume_text": "Strategy and analytics professional. Led cross-functional planning, financial modeling and forecasting. Managed executive KPI reviews and delivered a program that reduced cycle time 22%. Strong SQL, Excel, stakeholder management and presentation skills.",
                "hiring_manager_name": "", "hiring_manager_url": "", "referral_name": "Priya S.", "referral_url": "https://www.linkedin.com", "notes": "Interview: prepare 2 operating-model stories."
            }
        ]
        now = datetime.utcnow().isoformat(timespec="seconds")
        for s in samples:
            analysis = ats_analysis(s["resume_text"], s["job_description"])
            conn.execute("""
              INSERT INTO applications
              (company,title,location,status,applied_date,source,apply_url,salary,job_description,resume_text,ats_score,matched_keywords,missing_keywords,suggestions,hiring_manager_name,hiring_manager_url,referral_name,referral_url,notes,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                s["company"], s["title"], s["location"], s["status"], s["applied_date"], s["source"], s["apply_url"], s["salary"],
                s["job_description"], s["resume_text"], analysis["score"], json.dumps(analysis["matched"]), json.dumps(analysis["missing"]),
                json.dumps(analysis["suggestions"]), s["hiring_manager_name"], s["hiring_manager_url"], s["referral_name"], s["referral_url"], s["notes"], now, now
            ))
    conn.commit()
    conn.close()


class ApplicationIn(BaseModel):
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = ""
    status: str = "Saved"
    applied_date: str = ""
    source: str = ""
    apply_url: str = ""
    salary: str = ""
    job_description: str = ""
    resume_text: str = ""
    hiring_manager_name: str = ""
    hiring_manager_url: str = ""
    referral_name: str = ""
    referral_url: str = ""
    notes: str = ""


class StatusIn(BaseModel):
    status: str


class ContactIn(BaseModel):
    hiring_manager_name: str = ""
    hiring_manager_url: str = ""
    referral_name: str = ""
    referral_url: str = ""


def row_to_dict(row):
    d = dict(row)
    for k in ["matched_keywords", "missing_keywords", "suggestions"]:
        try:
            d[k] = json.loads(d[k] or "[]")
        except Exception:
            d[k] = []
    d["people_strategy"] = people_strategy(d["company"], d["title"])
    return d


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/applications")
def list_applications():
    conn = connect()
    rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC, id DESC").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/api/applications/{app_id}")
def get_application(app_id: int):
    conn = connect()
    row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return row_to_dict(row)


@app.post("/api/applications")
def create_application(item: ApplicationIn):
    if item.status not in STATUS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status")
    analysis = ats_analysis(item.resume_text, item.job_description)
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn = connect()
    cur = conn.execute("""
      INSERT INTO applications
      (company,title,location,status,applied_date,source,apply_url,salary,job_description,resume_text,ats_score,matched_keywords,missing_keywords,suggestions,hiring_manager_name,hiring_manager_url,referral_name,referral_url,notes,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item.company,item.title,item.location,item.status,item.applied_date,item.source,item.apply_url,item.salary,item.job_description,item.resume_text,
        analysis["score"],json.dumps(analysis["matched"]),json.dumps(analysis["missing"]),json.dumps(analysis["suggestions"]),item.hiring_manager_name,
        item.hiring_manager_url,item.referral_name,item.referral_url,item.notes,now,now
    ))
    app_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.put("/api/applications/{app_id}")
def update_application(app_id: int, item: ApplicationIn):
    if item.status not in STATUS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status")
    analysis = ats_analysis(item.resume_text, item.job_description)
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn = connect()
    exists = conn.execute("SELECT 1 FROM applications WHERE id=?", (app_id,)).fetchone()
    if not exists:
        conn.close(); raise HTTPException(status_code=404, detail="Application not found")
    conn.execute("""
      UPDATE applications SET company=?,title=?,location=?,status=?,applied_date=?,source=?,apply_url=?,salary=?,job_description=?,resume_text=?,ats_score=?,matched_keywords=?,missing_keywords=?,suggestions=?,hiring_manager_name=?,hiring_manager_url=?,referral_name=?,referral_url=?,notes=?,updated_at=?
      WHERE id=?
    """, (
        item.company,item.title,item.location,item.status,item.applied_date,item.source,item.apply_url,item.salary,item.job_description,item.resume_text,
        analysis["score"],json.dumps(analysis["matched"]),json.dumps(analysis["missing"]),json.dumps(analysis["suggestions"]),item.hiring_manager_name,
        item.hiring_manager_url,item.referral_name,item.referral_url,item.notes,now,app_id
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.patch("/api/applications/{app_id}/status")
def update_status(app_id: int, item: StatusIn):
    if item.status not in STATUS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status")
    conn = connect()
    cur = conn.execute("UPDATE applications SET status=?,updated_at=? WHERE id=?", (item.status,datetime.utcnow().isoformat(timespec="seconds"),app_id))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"ok": True}


@app.patch("/api/applications/{app_id}/contacts")
def update_contacts(app_id: int, item: ContactIn):
    conn = connect()
    cur = conn.execute("""UPDATE applications SET hiring_manager_name=?,hiring_manager_url=?,referral_name=?,referral_url=?,updated_at=? WHERE id=?""",
        (item.hiring_manager_name,item.hiring_manager_url,item.referral_name,item.referral_url,datetime.utcnow().isoformat(timespec="seconds"),app_id))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"ok": True}


@app.delete("/api/applications/{app_id}")
def delete_application(app_id: int):
    conn = connect(); cur = conn.execute("DELETE FROM applications WHERE id=?", (app_id,)); conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"ok": True}


@app.post("/api/ats-score")
def score_application(payload: dict):
    return ats_analysis(payload.get("resume_text", ""), payload.get("job_description", ""))


@app.get("/api/report")
def report():
    conn = connect()
    rows = conn.execute("SELECT * FROM applications").fetchall(); conn.close()
    apps = [row_to_dict(r) for r in rows]
    total = len(apps)
    applied = sum(1 for x in apps if x["status"] != "Saved")
    active = sum(1 for x in apps if x["status"] in {"Applied","Recruiter Screen","Interview","Final Round"})
    interviews = sum(1 for x in apps if x["status"] in {"Interview","Final Round","Offer"})
    offers = sum(1 for x in apps if x["status"] == "Offer")
    avg_ats = round(sum(x["ats_score"] for x in apps) / total) if total else 0
    status_counts = Counter(x["status"] for x in apps)
    source_counts = Counter(x["source"] or "Unknown" for x in apps)
    return {
        "total": total, "applied": applied, "active": active, "interviews": interviews, "offers": offers,
        "avg_ats": avg_ats,
        "interview_rate": round((interviews / applied * 100), 1) if applied else 0,
        "offer_rate": round((offers / applied * 100), 1) if applied else 0,
        "status_counts": status_counts,
        "source_counts": source_counts,
    }
