#!/usr/bin/env python3
"""
LinkedIn DS — Seed Script (Python)

Usage:
    python databases/seed.py            # fresh wipe + full dataset
    python databases/seed.py --keep     # skip wipe, add missing records only
    python databases/seed.py --fast     # smaller dataset, seeds quickly

Demo login credentials (password: Demo@1234):
  MEMBER ACCOUNTS:
    alice@demo.com   bob@demo.com   carol@demo.com
    david@demo.com   emma@demo.com

  RECRUITER ACCOUNTS:
    recruiter1@google.com   recruiter1@meta.com   recruiter1@amazon.com
"""

import csv
import json
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Auto-install dependencies ─────────────────────────────────────────────────
import subprocess
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "mysql-connector-python", "pymongo", "bcrypt"],
    check=True,
)

import bcrypt
import mysql.connector
from pymongo import MongoClient

# ── Flags ─────────────────────────────────────────────────────────────────────
KEEP_EXISTING = "--keep" in sys.argv
FAST_MODE     = "--fast" in sys.argv

# ── Scale ─────────────────────────────────────────────────────────────────────
if FAST_MODE:
    NUM_EXTRA_MEMBERS    = 495
    NUM_EXTRA_RECRUITERS = 497
    NUM_JOBS             = 500
    APPS_PER_MEMBER      = 1
    NUM_EVENTS           = 1500
    BENCHMARK_PAIR_COUNT = 1000
else:
    NUM_EXTRA_MEMBERS    = 9995
    NUM_EXTRA_RECRUITERS = 9997
    NUM_JOBS             = 10000
    APPS_PER_MEMBER      = 2
    NUM_EVENTS           = 10000
    BENCHMARK_PAIR_COUNT = 5000

# ── DB config ─────────────────────────────────────────────────────────────────
MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST",     "127.0.0.1"),
    "port":     int(os.getenv("MYSQL_PORT", "3307")),
    "user":     os.getenv("MYSQL_USER",     "appuser"),
    "password": os.getenv("MYSQL_PASSWORD", "apppassword"),
    "database": os.getenv("MYSQL_DATABASE", "linkedin_ds"),
}

MONGO_URI = (
    os.getenv("MONGO_URI")
    or (
        f"mongodb://{os.getenv('MONGO_USER', 'appuser')}:"
        f"{os.getenv('MONGO_PASSWORD', 'apppassword')}@"
        f"{os.getenv('MONGO_HOST', '127.0.0.1')}:"
        f"{os.getenv('MONGO_PORT', '27019')}/"
        f"linkedin_ds_logs?authSource=admin"
    )
)

# ── Dataset paths ──────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent.parent
DATASETS_DIR  = ROOT / "datasets" / "raw"
JOBS_CSV      = Path(os.getenv("SEED_JOBS_CSV",    str(DATASETS_DIR / "jobs.csv")))
RESUMES_CSV   = Path(os.getenv("SEED_RESUMES_CSV", str(DATASETS_DIR / "resumes.csv")))

# ── Static data ───────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Alice","Bob","Carol","David","Emma","Frank","Grace","Henry","Ivy","Jack",
    "Karen","Liam","Maya","Noah","Olivia","Paul","Quinn","Rachel","Sam","Tara",
    "Uma","Victor","Wendy","Xander","Yara","Zoe","Aaron","Bella","Carlos","Diana",
    "Ethan","Fiona","George","Hannah","Ian","Julia","Kevin","Luna","Marcus","Nina",
    "Oscar","Priya","Ryan","Sofia","Tyler","Uma","Vance","Whitney","Xena","Yasmin",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Wilson","Anderson","Thomas",
    "Taylor","Moore","Jackson","Martin","Lee","Perez","White","Harris","Clark",
    "Lewis","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen",
    "Hill","Flores","Green","Adams","Nelson","Baker","Hall","Rivera","Campbell",
    "Mitchell","Carter","Roberts","Evans","Turner","Parker","Collins","Edwards",
]
CITIES = [
    {"city": "San Jose",      "state": "CA"},
    {"city": "San Francisco", "state": "CA"},
    {"city": "Seattle",       "state": "WA"},
    {"city": "Austin",        "state": "TX"},
    {"city": "New York",      "state": "NY"},
    {"city": "Boston",        "state": "MA"},
    {"city": "Chicago",       "state": "IL"},
    {"city": "Los Angeles",   "state": "CA"},
    {"city": "Denver",        "state": "CO"},
    {"city": "Atlanta",       "state": "GA"},
    {"city": "Portland",      "state": "OR"},
    {"city": "Raleigh",       "state": "NC"},
]
SKILLS = [
    "Python","JavaScript","TypeScript","Java","Go","Rust","C++",
    "React","Node.js","Vue.js","Angular","Next.js",
    "MySQL","PostgreSQL","MongoDB","Redis","Elasticsearch",
    "Kafka","RabbitMQ","Docker","Kubernetes","AWS","GCP","Azure",
    "Machine Learning","TensorFlow","PyTorch","Spark","Scala",
    "GraphQL","REST APIs","gRPC","Microservices","System Design",
    "Git","Linux","CI/CD","Terraform","Ansible","Jenkins",
    "Data Engineering","ETL","Tableau","Figma","Agile","Scrum",
]
COMPANIES = [
    {"name": "Google",     "industry": "Technology"},
    {"name": "Meta",       "industry": "Technology"},
    {"name": "Amazon",     "industry": "Technology"},
    {"name": "Microsoft",  "industry": "Technology"},
    {"name": "Apple",      "industry": "Technology"},
    {"name": "Netflix",    "industry": "Media"},
    {"name": "Uber",       "industry": "Technology"},
    {"name": "Airbnb",     "industry": "Technology"},
    {"name": "Stripe",     "industry": "Finance"},
    {"name": "Salesforce", "industry": "Technology"},
]
JOB_TITLES = [
    "Software Engineer","Senior Software Engineer","Staff Engineer",
    "Backend Engineer","Frontend Engineer","Full Stack Engineer",
    "Data Engineer","ML Engineer","DevOps Engineer",
    "Site Reliability Engineer","Platform Engineer",
    "Data Scientist","Data Analyst","Product Manager",
    "Solutions Architect","Security Engineer",
]
WORK_MODES       = ["onsite", "remote", "hybrid"]
SENIORITY_LEVELS = ["Internship","Entry level","Associate","Mid-Senior level","Director","Executive"]
EMPLOYMENT_TYPES = ["Full-time","Full-time","Full-time","Contract","Part-time","Internship"]
SALARY_RANGES = {
    "Internship":       {"min": 40000,  "max": 80000},
    "Entry level":      {"min": 80000,  "max": 120000},
    "Associate":        {"min": 100000, "max": 150000},
    "Mid-Senior level": {"min": 130000, "max": 200000},
    "Director":         {"min": 200000, "max": 320000},
    "Executive":        {"min": 280000, "max": 450000},
}
JOB_DESC_TEMPLATES = [
    (
        "About the Role:\n"
        "We are looking for a talented {title} to join our growing engineering team at {company}.\n\n"
        "What you'll do:\n"
        "• Design and build high-performance, scalable {skill1} systems\n"
        "• Collaborate with cross-functional teams to define and ship features\n"
        "• Write clean, maintainable code with strong test coverage\n"
        "• Participate in code reviews and mentor junior engineers\n\n"
        "What we're looking for:\n"
        "• 3+ years of experience with {skill1} and {skill2}\n"
        "• Strong understanding of distributed systems and microservices\n"
        "• BS/MS in Computer Science or equivalent practical experience\n\n"
        "We offer competitive salary, equity, and great benefits."
    ),
    (
        "{company} is hiring a {title}!\n\n"
        "You'll be joining a world-class team working on problems that impact millions of users.\n\n"
        "Responsibilities:\n"
        "• Build and maintain production {skill1} services\n"
        "• Improve system reliability, scalability, and performance\n"
        "• Work with data using {skill2}\n"
        "• Drive technical decisions from design to deployment\n\n"
        "Requirements:\n"
        "• Proficiency in {skill1} and {skill2}\n"
        "• Experience with cloud platforms (AWS / GCP / Azure)\n"
        "• Strong problem-solving skills and attention to detail\n\n"
        "This is a {work_mode} position based in our {city} office."
    ),
]
CHAT_MESSAGES = [
    "Hi! I saw you're hiring for a {role} position. I'd love to learn more.",
    "Thanks for reaching out! Yes, we have an opening. Can you share your resume?",
    "Absolutely, I've attached it. I have 4 years of experience with {skill}.",
    "Great background! Would you be available for a 30-minute call this week?",
    "Sure! Thursday at 2pm works for me. Looking forward to it.",
    "Perfect, I'll send a calendar invite. See you then!",
    "Just wanted to follow up on my application for the {role} role.",
    "We're still reviewing candidates. We'll be in touch by end of week.",
    "Sounds good, thank you for the update!",
    "I wanted to congratulate you — we'd like to move forward to the next round!",
    "That's amazing news! I'm very excited about this opportunity.",
    "We were really impressed with your {skill} experience in the interview.",
]
FEED_POSTS = [
    {"type": "career_update", "content": "Excited to share that I joined Nimbus Labs as a Software Engineer this week.\nHuge thanks to everyone who helped with prep and referrals.\nLooking forward to building products that impact real customers."},
    {"type": "hiring",        "content": "We're hiring 3 backend engineers in Seattle and Austin.\nIf you enjoy distributed systems, Kafka, and high-scale APIs, let's talk.\nPlease DM me or apply through our careers page. #hiring #backend"},
    {"type": "project",       "content": "Shipped a real-time alerting pipeline using Kafka + Redis Streams.\nWe reduced event processing latency from 2.4s to under 300ms.\nGreat reminder that small architecture choices compound fast. #dataengineering"},
    {"type": "learning",      "content": "Spent the weekend revisiting system design fundamentals.\nA simple takeaway: optimize for debuggability before micro-optimizations.\nBetter logs saved us more than any fancy abstraction."},
    {"type": "general",       "content": "Consistency beats intensity.\n30 focused minutes every day on your craft adds up faster than occasional all-nighters.\nWhat habit helped your career the most?"},
    {"type": "job_update",    "content": "Looking for Summer 2026 software engineering internships.\nStrong with React, Node.js, and SQL. Open to remote or Bay Area roles.\nWould appreciate referrals. #internship #opentowork"},
]
FEED_COMMENTS = [
    "Congrats! Wishing you the best in the new role.",
    "This is a great breakdown. Thanks for sharing.",
    "Would love to learn more about how you approached this.",
    "Thanks for posting this - very relevant right now.",
    "Strong insights here. Saving this for my team.",
]
HEADLINE_TEMPLATES = [
    "Software Engineer | {skill} & {skill2}",
    "Senior {role} at {company}",
    "{role} | Building scalable systems with {skill}",
    "Full Stack Engineer | {skill} enthusiast",
    "{role} | Open to new opportunities",
    "Passionate {role} | {skill} & {skill2}",
    "Ex-{company} · Now {role} at {company2}",
    "{role} | {city} | {skill} expert",
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def pick(lst):
    return random.choice(lst)

def pick_n(lst, n):
    return random.sample(lst, min(n, len(lst)))

def rand_int(lo, hi):
    return random.randint(lo, hi)

def make_email(first, last, suffix=""):
    domain = pick(["gmail.com","yahoo.com","outlook.com","hotmail.com"])
    return f"{first.lower()}.{last.lower()}{suffix}@{domain}"

def make_headline(role, skills, location):
    tpl = pick(HEADLINE_TEMPLATES)
    return (
        tpl
        .replace("{role}",     role)
        .replace("{skill}",    skills[0] if skills else "Python")
        .replace("{skill2}",   skills[1] if len(skills) > 1 else "JavaScript")
        .replace("{company}",  pick(COMPANIES)["name"])
        .replace("{company2}", pick(COMPANIES)["name"])
        .replace("{city}",     location["city"])
    )

def make_job_desc(title, company_name, skills, work_mode, city):
    tpl = pick(JOB_DESC_TEMPLATES)
    return (
        tpl
        .replace("{title}",     title)
        .replace("{company}",   company_name)
        .replace("{skill1}",    skills[0] if skills else "Python")
        .replace("{skill2}",    skills[1] if len(skills) > 1 else "SQL")
        .replace("{work_mode}", work_mode)
        .replace("{city}",      city)
    )

def show_progress(label, current, total):
    pct    = round(current / total * 100)
    filled = round(pct / 5)
    bar    = "█" * filled + "░" * (20 - filled)
    end    = "\n" if current == total else ""
    print(f"\r  {label}: {current}/{total} [{bar}] {pct}%", end=end, flush=True)

def uid():
    return str(uuid.uuid4())

def utcnow():
    return datetime.now(timezone.utc)

def days_ago(n):
    return utcnow() - timedelta(days=n)

def hours_ago(n):
    return utcnow() - timedelta(hours=n)

# ── CSV loading ───────────────────────────────────────────────────────────────
def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            if any(v for v in normalized.values()):
                rows.append(normalized)
    return rows

def first_non_empty(row, keys, fallback=""):
    for k in keys:
        v = row.get(k, "")
        if v:
            return v
    return fallback

def normalize_skill_tokens(raw):
    if not raw:
        return []
    cleaned = re.sub(r"[\r\n|;/]", ",", str(raw))
    tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
    return list(dict.fromkeys(tokens))[:15]

def extract_skills_from_text(text, fallback_count=6):
    lower = (text or "").lower()
    matches = [s for s in SKILLS if s.lower() in lower]
    if matches:
        return matches[:10]
    return pick_n(SKILLS, fallback_count)

def map_resume_row(row, idx):
    resume_text = first_non_empty(row, ["resume","resume_text","resume_str","resume content","cleaned_resume","text"])
    category    = first_non_empty(row, ["category","job_category","label"], pick(JOB_TITLES))
    listed      = normalize_skill_tokens(first_non_empty(row, ["skills","key skills","keywords"]))
    skills      = listed if listed else extract_skills_from_text(resume_text or category)
    m           = re.search(r"(\d{1,2})\+?\s+years?", resume_text or "", re.IGNORECASE)
    years_exp   = int(m.group(1)) if m else rand_int(1, 10)
    about       = (resume_text or f"{category} profile").replace("\s+", " ").strip()[:420]
    resume_full = (resume_text or f"Category: {category}\nSkills: {', '.join(skills)}")[:5000]
    return {"category": category, "skills": skills, "years_experience": years_exp,
            "about": about or f"{category} profile with experience in {', '.join(skills[:3])}.",
            "resume_text": resume_full}

def map_job_row(row, fallback_recruiter, idx):
    title    = first_non_empty(row, ["title","job title","job_title","position"], pick(JOB_TITLES))
    desc     = first_non_empty(row, ["description","job description","job_description","desc"])
    company  = first_non_empty(row, ["company","company_name","company name"], fallback_recruiter["company"]["name"])
    city_raw = first_non_empty(row, ["city","location_city"])
    state_raw= first_non_empty(row, ["state","location_state"])
    loc      = {"city": city_raw, "state": state_raw} if city_raw and state_raw else pick(CITIES)
    country  = first_non_empty(row, ["country"], "USA")
    wm_raw   = first_non_empty(row, ["work_mode","work mode","job_type","workplace_type"]).lower()
    work_mode= "remote" if "remote" in wm_raw else ("hybrid" if "hybrid" in wm_raw else "onsite")
    sal_min  = int(first_non_empty(row, ["salary_min","min_salary","salary from"], "0") or 0) or None
    sal_max  = int(first_non_empty(row, ["salary_max","max_salary","salary to"],   "0") or 0) or None
    listed   = normalize_skill_tokens(first_non_empty(row, ["skills","required_skills","key skills","tags","technologies"]))
    skills   = listed if listed else extract_skills_from_text(f"{title} {desc}", 5)
    return {"title": title[:255],
            "description": (desc or make_job_desc(title, company, skills, work_mode, loc["city"]))[:12000],
            "city": loc["city"], "state": loc["state"], "country": country,
            "work_mode": work_mode, "salary_min": sal_min, "salary_max": sal_max, "skills": skills}

# ── Password hashing ──────────────────────────────────────────────────────────
def hash_password(plain):
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=10)).decode()

# ── MySQL helpers ─────────────────────────────────────────────────────────────
def ensure_recruiter_profile_columns(cur):
    fragments = [
        "ADD COLUMN headline VARCHAR(280) NULL DEFAULT NULL AFTER role",
        "ADD COLUMN about TEXT NULL AFTER headline",
        "ADD COLUMN location VARCHAR(200) NULL AFTER about",
        "ADD COLUMN specialties VARCHAR(800) NULL AFTER location",
        "ADD COLUMN hiring_highlights TEXT NULL AFTER specialties",
        "ADD COLUMN profile_photo_url LONGTEXT NULL",
    ]
    for frag in fragments:
        try:
            cur.execute(f"ALTER TABLE recruiters {frag}")
        except mysql.connector.errors.DatabaseError as e:
            if e.errno != 1060:  # ER_DUP_FIELDNAME
                raise

def ensure_member_photo_column(cur):
    try:
        cur.execute("ALTER TABLE members MODIFY COLUMN profile_photo_url LONGTEXT NULL")
    except Exception:
        pass

def ensure_post_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id        VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
            author_id      VARCHAR(36) NOT NULL,
            content        TEXT NOT NULL,
            post_type      ENUM('general','job_update','project','hiring','learning','career_update') DEFAULT 'general',
            likes_count    INT DEFAULT 0,
            comments_count INT DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (author_id) REFERENCES members(member_id) ON DELETE CASCADE,
            INDEX idx_author (author_id),
            INDEX idx_created_at (created_at),
            INDEX idx_post_type (post_type)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_likes (
            like_id    VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
            post_id    VARCHAR(36) NOT NULL,
            member_id  VARCHAR(36) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_post_member_like (post_id, member_id),
            FOREIGN KEY (post_id)   REFERENCES posts(post_id)     ON DELETE CASCADE,
            FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_comments (
            comment_id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
            post_id    VARCHAR(36) NOT NULL,
            author_id  VARCHAR(36) NOT NULL,
            content    TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id)   REFERENCES posts(post_id)     ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES members(member_id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_posts (
            save_id    VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
            post_id    VARCHAR(36) NOT NULL,
            member_id  VARCHAR(36) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_saved_post_member (post_id, member_id),
            FOREIGN KEY (post_id)   REFERENCES posts(post_id)     ON DELETE CASCADE,
            FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
        )
    """)

# ══════════════════════════════════════════════════════════════════════════════
def seed():
    print("\n🌱  LinkedIn DS — Seed Script (Python)")
    print("═" * 55)
    mode_str = ("FAST" if FAST_MODE else "FULL") + (" + KEEP" if KEEP_EXISTING else "")
    print(f"\n⚙️  Mode: {mode_str}")

    # ── Connect ───────────────────────────────────────────────────────────────
    print("\n📡 Connecting to databases...")
    sql_conn = mysql.connector.connect(**MYSQL_CONFIG, autocommit=True)
    cur = sql_conn.cursor()
    print("  ✓ MySQL connected")

    mongo = MongoClient(MONGO_URI)
    db    = mongo["linkedin_ds_logs"]
    print("  ✓ MongoDB connected")

    DEMO_HASH = hash_password("Demo@1234")
    jobs_dataset    = load_csv(JOBS_CSV)
    resumes_dataset = load_csv(RESUMES_CSV)
    print(f"\n🗂  Dataset rows: jobs={len(jobs_dataset)}, resumes={len(resumes_dataset)}")
    if not jobs_dataset or not resumes_dataset:
        print("  ℹ️  Tip: add CSVs at datasets/raw/jobs.csv and datasets/raw/resumes.csv")

    ensure_post_tables(cur)

    # ── Wipe ──────────────────────────────────────────────────────────────────
    if KEEP_EXISTING:
        print("\n⏭  Skipping clean — keeping existing data (--keep mode)")
    else:
        print("\n🧹 Cleaning existing data...")
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in [
            "application_status_history","application_notes","applications",
            "saved_posts","post_comments","post_likes","saved_jobs","job_skills","jobs",
            "posts","connections","connection_requests","profile_views",
            "member_education","member_experience","member_skills","recruiters","members",
        ]:
            try:
                cur.execute(f"TRUNCATE TABLE {table}")
            except Exception:
                pass
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        print("  ✓ MySQL tables cleared")
        for coll in ("threads", "messages", "event_logs", "ai_task_traces"):
            db[coll].delete_many({})
        print("  ✓ MongoDB collections cleared")

    # ── Demo members ──────────────────────────────────────────────────────────
    print("\n👤 Creating demo member accounts...")
    ensure_member_photo_column(cur)

    demo_member_specs = [
        {"email": "alice@demo.com", "first": "Alice", "last": "Johnson",
         "city": "San Francisco", "state": "CA",
         "headline": "Senior Software Engineer | Python & React | Building scalable APIs",
         "about": "Software engineer with 6 years of experience building full-stack web applications. Specializes in Python backends and React frontends.",
         "skills": ["Python","React","Node.js","MySQL","Docker","AWS","Redis","Kafka"]},
        {"email": "bob@demo.com", "first": "Bob", "last": "Chen",
         "city": "Seattle", "state": "WA",
         "headline": "Data Engineer at Amazon | Kafka, Spark & Python enthusiast",
         "about": "Data engineer with 4 years of experience building real-time data pipelines at scale. Expert in Apache Kafka and Spark.",
         "skills": ["Python","Kafka","Spark","SQL","AWS","Docker","Airflow","Scala"]},
        {"email": "carol@demo.com", "first": "Carol", "last": "Patel",
         "city": "Austin", "state": "TX",
         "headline": "ML Engineer | TensorFlow & PyTorch | Open to opportunities",
         "about": "Machine learning engineer with a passion for NLP and computer vision. Deployed production ML models serving 10M+ requests per day.",
         "skills": ["Python","Machine Learning","TensorFlow","PyTorch","SQL","Docker","Kubernetes","GCP"]},
        {"email": "david@demo.com", "first": "David", "last": "Kim",
         "city": "New York", "state": "NY",
         "headline": "Full Stack Engineer | TypeScript, React & Node.js",
         "about": "Full stack developer who loves building beautiful, performant UIs backed by robust Node.js APIs. 5 years in fintech.",
         "skills": ["TypeScript","React","Node.js","PostgreSQL","Redis","Docker","AWS","GraphQL"]},
        {"email": "emma@demo.com", "first": "Emma", "last": "Rodriguez",
         "city": "San Jose", "state": "CA",
         "headline": "DevOps Engineer | Kubernetes, Terraform & CI/CD pipelines",
         "about": "DevOps engineer specializing in cloud infrastructure and developer productivity. Automates everything from Terraform to zero-downtime deployments.",
         "skills": ["Kubernetes","Docker","Terraform","AWS","GCP","Jenkins","CI/CD","Linux","Python"]},
    ]

    demo_member_ids = []
    for m in demo_member_specs:
        mid = uid()
        try:
            cur.execute(
                "INSERT INTO members (member_id, first_name, last_name, email, password_hash, city, state, country, headline, about) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (mid, m["first"], m["last"], m["email"], DEMO_HASH, m["city"], m["state"], "USA", m["headline"], m["about"]),
            )
            for skill in m["skills"]:
                cur.execute("INSERT IGNORE INTO member_skills (member_id, skill) VALUES (%s,%s)", (mid, skill))
            demo_member_ids.append(mid)
            print(f"  ✓ {m['first']} {m['last']} — {m['email']}")
        except mysql.connector.errors.IntegrityError:
            row = cur.execute("SELECT member_id FROM members WHERE email = %s", (m["email"],)) or None
            result = cur.fetchone()
            if result:
                demo_member_ids.append(result[0])
            print(f"  ⚠ Skipped {m['email']} (already exists)")

    # ── Demo recruiters ───────────────────────────────────────────────────────
    print("\n🏢 Creating demo recruiter accounts...")
    ensure_recruiter_profile_columns(cur)

    demo_recruiter_specs = [
        {"email": "recruiter1@google.com", "first": "Priya", "last": "Sharma",
         "company": COMPANIES[0],
         "headline": "Senior Talent Acquisition Partner | Consumer Software & Platforms",
         "location": "Mountain View, CA · Hybrid",
         "about": "I lead engineering recruiting for consumer-facing teams — search relevance, monetization infra, developer productivity, and the platforms behind products used daily by billions.",
         "specialties": "Software Engineering,Distributed Systems,ML Infra,SRE / Production,University Recruiting",
         "hiring_highlights": json.dumps(["7+ years hiring L4–L7 engineers across Search, Ads, and shared infra","Designed interviewer enablement touched by 200+ engineers annually","Partner for Veterans in Technology programs"])},
        {"email": "recruiter1@meta.com", "first": "James", "last": "Wilson",
         "company": COMPANIES[1],
         "headline": "Technical Recruiting Lead | Reality Labs & Core Product Infrastructure",
         "location": "Menlo Park, CA · Hybrid",
         "about": "I specialize in sourcing and closing senior IC and manager roles where hardware, systems software, and product engineering intersect — from AR/VR to fleet-scale infra.",
         "specialties": "Systems Software,Mobile (iOS/Android),AR/VR,Data Engineering,Backend at Scale",
         "hiring_highlights": json.dumps(["Led hiring for orgs spanning 40–120 engineers","Built sourcing playbooks for specialized domains (graphics, low-latency networking)","Regular speaker at Grace Hopper on technical interview prep"])},
        {"email": "recruiter1@amazon.com", "first": "Sarah", "last": "Lee",
         "company": COMPANIES[2],
         "headline": "Principal Recruiter | AWS Consumer & Edge Networking",
         "location": "Seattle, WA · Remote-friendly",
         "about": "I partner with AWS service teams building customer-facing networking, edge, and reliability products. Amazon's leadership principles show up in how I build and run hiring loops.",
         "specialties": "Networking,AWS / Cloud Infra,Distributed Systems,Technical Program Management",
         "hiring_highlights": json.dumps(["10+ years in technical recruiting across retail tech and hyperscale cloud","Owns stakeholder relationships with principals and Sr. Principals","Advocate for relocation support for caregivers and military spouses"])},
    ]

    demo_recruiter_ids = []
    for r in demo_recruiter_specs:
        rid = uid()
        cid = uid()
        try:
            cur.execute(
                """INSERT INTO recruiters
                   (recruiter_id, company_id, first_name, last_name, email, password_hash,
                    company_name, company_industry, company_size, role,
                    headline, about, location, specialties, hiring_highlights)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rid, cid, r["first"], r["last"], r["email"], DEMO_HASH,
                 r["company"]["name"], r["company"]["industry"], "5000+", "recruiter",
                 r["headline"], r["about"], r["location"], r["specialties"], r["hiring_highlights"]),
            )
            demo_recruiter_ids.append({"id": rid, "company_id": cid, "company": r["company"]})
            print(f"  ✓ {r['first']} {r['last']} ({r['company']['name']}) — ID: {rid}")
        except mysql.connector.errors.IntegrityError:
            cur.execute("SELECT recruiter_id, company_id FROM recruiters WHERE email = %s", (r["email"],))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE recruiters SET password_hash=%s, headline=%s, about=%s, location=%s, specialties=%s, hiring_highlights=%s WHERE email=%s",
                    (DEMO_HASH, r["headline"], r["about"], r["location"], r["specialties"], r["hiring_highlights"], r["email"]),
                )
                demo_recruiter_ids.append({"id": row[0], "company_id": row[1], "company": r["company"]})
            print(f"  ⚠ {r['email']} already exists — updated")

    # ── Bulk members ──────────────────────────────────────────────────────────
    print(f"\n👥 Creating {NUM_EXTRA_MEMBERS} additional members...")
    all_member_ids    = list(demo_member_ids)
    all_member_entries = [
        {"member_id": m["id"] if "id" in m else demo_member_ids[i],
         "city": m.get("city", "San Francisco"), "state": m.get("state", "CA"), "country": "USA",
         "resume_text": f"{m['first']} {m['last']}\nSKILLS: {', '.join(m['skills'])}\nABOUT: {m['about']}"}
        for i, m in enumerate(demo_member_specs)
    ]
    # patch member_id from actual inserted ids
    for i, entry in enumerate(all_member_entries):
        entry["member_id"] = demo_member_ids[i]

    for i in range(NUM_EXTRA_MEMBERS):
        first  = pick(FIRST_NAMES)
        last   = pick(LAST_NAMES)
        mid    = uid()
        email  = make_email(first, last, f"_{i}")
        loc    = pick(CITIES)
        resume_row = resumes_dataset[i % len(resumes_dataset)] if resumes_dataset else None
        mapped = map_resume_row(resume_row, i) if resume_row else None
        role   = (mapped["category"] if mapped else pick(JOB_TITLES))[:120]
        skills = mapped["skills"] if (mapped and mapped["skills"]) else pick_n(SKILLS, rand_int(4, 9))
        years  = mapped["years_experience"] if mapped else rand_int(1, 12)
        about  = (mapped["about"] if mapped else
                  f"{years}-year {role.lower()} specializing in {', '.join(skills[:3])}. Based in {loc['city']}, {loc['state']}.")
        resume_text = (mapped["resume_text"] if mapped else
                       f"{first} {last} | {email}\nSKILLS: {', '.join(skills)}\nEXPERIENCE: {role} ({2024 - years}–present)\nEDUCATION: B.S. Computer Science")
        headline = make_headline(role, skills, loc)
        try:
            cur.execute(
                "INSERT INTO members (member_id, first_name, last_name, email, password_hash, city, state, country, headline, about, resume_text) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (mid, first, last, email, DEMO_HASH, loc["city"], loc["state"], "USA", headline, about[:420], resume_text[:5000]),
            )
            for skill in skills:
                cur.execute("INSERT IGNORE INTO member_skills (member_id, skill) VALUES (%s,%s)", (mid, skill))
            all_member_ids.append(mid)
            all_member_entries.append({"member_id": mid, "city": loc["city"], "state": loc["state"], "country": "USA", "resume_text": resume_text[:5000]})
        except mysql.connector.errors.IntegrityError:
            pass
        show_progress("Members", i + 1, NUM_EXTRA_MEMBERS)

    # ── Feed posts ────────────────────────────────────────────────────────────
    print(f"\n📰 Creating {len(FEED_POSTS)} feed posts...")
    extra_authors = pick_n([m for m in all_member_ids if m not in demo_member_ids], min(10, len(all_member_ids) - len(demo_member_ids)))
    feed_authors  = demo_member_ids + extra_authors
    seeded_post_ids = []
    for i, post in enumerate(FEED_POSTS):
        pid       = uid()
        author_id = feed_authors[i % len(feed_authors)]
        ts        = hours_ago(rand_int(1, 24 * 14))
        cur.execute(
            "INSERT INTO posts (post_id, author_id, content, post_type, likes_count, comments_count, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (pid, author_id, post["content"], post["type"], 0, 0, ts, ts),
        )
        seeded_post_ids.append(pid)
    print("  ✓ Feed posts created")

    print("\n💙 Seeding likes and comments for feed posts...")
    for pid in seeded_post_ids:
        liked = set()
        for _ in range(rand_int(3, 24)):
            mid2 = pick(all_member_ids)
            if mid2 in liked:
                continue
            liked.add(mid2)
            try:
                cur.execute("INSERT IGNORE INTO post_likes (like_id, post_id, member_id) VALUES (%s,%s,%s)", (uid(), pid, mid2))
            except Exception:
                pass
        for _ in range(rand_int(1, 4)):
            comment_ts = hours_ago(rand_int(1, 24 * 10))
            try:
                cur.execute(
                    "INSERT INTO post_comments (comment_id, post_id, author_id, content, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (uid(), pid, pick(all_member_ids), pick(FEED_COMMENTS), comment_ts, comment_ts),
                )
            except Exception:
                pass
        cur.execute(
            "UPDATE posts p SET likes_count=(SELECT COUNT(*) FROM post_likes pl WHERE pl.post_id=p.post_id), comments_count=(SELECT COUNT(*) FROM post_comments pc WHERE pc.post_id=p.post_id) WHERE p.post_id=%s",
            (pid,),
        )
    print("  ✓ Feed likes/comments seeded")

    # ── Bulk recruiters ───────────────────────────────────────────────────────
    print(f"\n📋 Creating {NUM_EXTRA_RECRUITERS} additional recruiters...")
    all_recruiter_entries = list(demo_recruiter_ids)
    for i in range(NUM_EXTRA_RECRUITERS):
        first = pick(FIRST_NAMES)
        last  = pick(LAST_NAMES)
        rid   = uid()
        cid   = uid()
        email = make_email(first, last, f"_rec{i}")
        co    = pick(COMPANIES)
        try:
            cur.execute(
                "INSERT INTO recruiters (recruiter_id, company_id, first_name, last_name, email, password_hash, company_name, company_industry, company_size, role) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (rid, cid, first, last, email, DEMO_HASH, co["name"], co["industry"],
                 pick(["50-200","200-500","500-1000","5000+"]), "recruiter"),
            )
            all_recruiter_entries.append({"id": rid, "company_id": cid, "company": co})
        except mysql.connector.errors.IntegrityError:
            pass
        show_progress("Recruiters", i + 1, NUM_EXTRA_RECRUITERS)

    # ── Jobs ──────────────────────────────────────────────────────────────────
    print(f"\n💼 Creating {NUM_JOBS} job postings...")
    job_ids            = []
    job_entries        = []
    demo_job_ids       = []
    seeded_job_count   = 0

    demo_job_blueprints = [
        {"title": "Senior Software Engineer",  "seniority": "Mid-Senior level", "employment": "Full-time",  "mode": "hybrid",  "city": "Mountain View", "state": "CA", "skills": ["JavaScript","React","Node.js","System Design"]},
        {"title": "Machine Learning Engineer", "seniority": "Mid-Senior level", "employment": "Full-time",  "mode": "remote",  "city": "Sunnyvale",     "state": "CA", "skills": ["Python","Machine Learning","TensorFlow","Kafka"]},
        {"title": "Software Engineer Intern",  "seniority": "Internship",        "employment": "Internship", "mode": "onsite",  "city": "San Francisco", "state": "CA", "skills": ["Python","JavaScript","Git","Docker"]},
        {"title": "Backend Engineer – Instagram","seniority": "Associate",       "employment": "Full-time",  "mode": "hybrid",  "city": "Menlo Park",    "state": "CA", "skills": ["Go","Kafka","MySQL","Redis"]},
        {"title": "Data Engineer – Analytics", "seniority": "Associate",         "employment": "Full-time",  "mode": "remote",  "city": "Seattle",       "state": "WA", "skills": ["Python","Spark","ETL","SQL"]},
        {"title": "Frontend Engineer – React",  "seniority": "Entry level",      "employment": "Full-time",  "mode": "hybrid",  "city": "New York",      "state": "NY", "skills": ["React","TypeScript","Figma","REST APIs"]},
        {"title": "Cloud Solutions Architect",  "seniority": "Director",         "employment": "Full-time",  "mode": "remote",  "city": "Austin",        "state": "TX", "skills": ["AWS","Terraform","Kubernetes","System Design"]},
        {"title": "Software Engineer – Azure",  "seniority": "Associate",        "employment": "Full-time",  "mode": "hybrid",  "city": "Redmond",       "state": "WA", "skills": ["C#","Azure","Docker","Microservices"]},
        {"title": "DevOps Engineer",            "seniority": "Mid-Senior level", "employment": "Contract",   "mode": "remote",  "city": "Boston",        "state": "MA", "skills": ["Docker","Kubernetes","Terraform","CI/CD"]},
    ]

    for ri, rec_entry in enumerate(demo_recruiter_ids):
        for bp in demo_job_blueprints[ri * 3:(ri * 3) + 3]:
            jid   = uid()
            sr    = SALARY_RANGES[bp["seniority"]]
            desc  = make_job_desc(bp["title"], rec_entry["company"]["name"], bp["skills"], bp["mode"], bp["city"])
            try:
                cur.execute(
                    "INSERT INTO jobs (job_id, company_id, recruiter_id, title, description, seniority_level, employment_type, city, state, country, work_mode, salary_min, salary_max, industry, status, views_count, saves_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (jid, rec_entry["company_id"], rec_entry["id"], bp["title"], desc,
                     bp["seniority"], bp["employment"], bp["city"], bp["state"], "USA", bp["mode"],
                     sr["min"], sr["max"], rec_entry["company"]["industry"], "open",
                     rand_int(80, 300), rand_int(10, 40)),
                )
                for skill in bp["skills"]:
                    cur.execute("INSERT IGNORE INTO job_skills (job_id, skill) VALUES (%s,%s)", (jid, skill))
                job_ids.append(jid)
                demo_job_ids.append(jid)
                job_entries.append({"job_id": jid, "recruiter_id": rec_entry["id"], "company_id": rec_entry["company_id"],
                                    "company_name": rec_entry["company"]["name"], "industry": rec_entry["company"]["industry"],
                                    "city": bp["city"], "state": bp["state"], "country": "USA", "status": "open", "skills": bp["skills"]})
                seeded_job_count += 1
            except mysql.connector.errors.IntegrityError:
                pass

    remaining = max(NUM_JOBS - seeded_job_count, 0)
    for i in range(remaining):
        jid          = uid()
        rec_entry    = pick(all_recruiter_entries)
        job_row      = jobs_dataset[i % len(jobs_dataset)] if jobs_dataset else None
        mapped_job   = map_job_row(job_row, rec_entry, i) if job_row else None
        title        = mapped_job["title"] if mapped_job else pick(JOB_TITLES)
        skills       = mapped_job["skills"] if (mapped_job and mapped_job["skills"]) else pick_n(SKILLS, rand_int(3, 7))
        loc          = {"city": mapped_job["city"], "state": mapped_job["state"]} if mapped_job else pick(CITIES)
        work_mode    = mapped_job["work_mode"] if mapped_job else pick(WORK_MODES)
        seniority    = pick(SENIORITY_LEVELS)
        sr           = SALARY_RANGES[seniority]
        sal_min      = mapped_job["salary_min"] or rand_int(sr["min"] // 1000, sr["max"] // 1000) * 1000
        sal_max      = mapped_job["salary_max"] or sal_min + rand_int(15, 50) * 1000
        status       = "open" if random.random() < 0.80 else "closed"
        emp_type     = "Internship" if seniority == "Internship" else pick(EMPLOYMENT_TYPES)
        desc         = (mapped_job["description"] if mapped_job else make_job_desc(title, rec_entry["company"]["name"], skills, work_mode, loc["city"]))
        country      = mapped_job["country"] if mapped_job else "USA"
        try:
            cur.execute(
                "INSERT INTO jobs (job_id, company_id, recruiter_id, title, description, seniority_level, employment_type, city, state, country, work_mode, salary_min, salary_max, industry, status, views_count, saves_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (jid, rec_entry["company_id"], rec_entry["id"], title, desc, seniority, emp_type,
                 loc["city"], loc["state"], country, work_mode, sal_min, sal_max,
                 rec_entry["company"]["industry"], status, rand_int(20, 800), rand_int(0, 40)),
            )
            for skill in skills:
                cur.execute("INSERT IGNORE INTO job_skills (job_id, skill) VALUES (%s,%s)", (jid, skill))
            job_ids.append(jid)
            job_entries.append({"job_id": jid, "recruiter_id": rec_entry["id"], "company_id": rec_entry["company_id"],
                                 "company_name": rec_entry["company"]["name"], "industry": rec_entry["company"]["industry"],
                                 "city": loc["city"], "state": loc["state"], "country": country, "status": status, "skills": skills})
        except mysql.connector.errors.IntegrityError:
            pass
        show_progress("Jobs", seeded_job_count + i + 1, NUM_JOBS)

    open_job_ids = [j["job_id"] for j in job_entries if j["status"] == "open"]

    # ── Applications ──────────────────────────────────────────────────────────
    print(f"\n📨 Creating ~{len(all_member_ids) * APPS_PER_MEMBER} applications...")
    app_count = 0
    WEIGHTED_STATUSES = (
        ["submitted"] * 35 + ["reviewing"] * 30 +
        ["interview"] * 20 + ["offer"] * 5 + ["rejected"] * 10
    )

    seeded_apps = [
        (demo_member_ids[0], demo_job_ids[0], "reviewing"),
        (demo_member_ids[1], demo_job_ids[0], "interview"),
        (demo_member_ids[2], demo_job_ids[1], "submitted"),
        (demo_member_ids[3], demo_job_ids[1], "offer"),
        (demo_member_ids[4], demo_job_ids[2], "submitted"),
        (demo_member_ids[0], demo_job_ids[3], "reviewing"),
        (demo_member_ids[1], demo_job_ids[4], "submitted"),
        (demo_member_ids[2], demo_job_ids[5], "rejected"),
        (demo_member_ids[3], demo_job_ids[6], "interview"),
        (demo_member_ids[4], demo_job_ids[7], "submitted"),
    ]
    for mid2, jid2, status in seeded_apps:
        if not mid2 or not jid2:
            continue
        try:
            cur.execute(
                "INSERT INTO applications (application_id, job_id, member_id, cover_letter, status, idempotency_key) VALUES (%s,%s,%s,%s,%s,%s)",
                (uid(), jid2, mid2, "Seeded demo application for the end-to-end walkthrough.", status, uid()),
            )
            cur.execute("UPDATE jobs SET applicants_count = applicants_count + 1 WHERE job_id = %s", (jid2,))
            app_count += 1
        except mysql.connector.errors.IntegrityError:
            pass

    # Benchmark CSV
    benchmark_dir = ROOT / "infrastructure" / "benchmarks" / "data"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    seen_pairs: set = set()
    benchmark_rows = []
    while len(benchmark_rows) < BENCHMARK_PAIR_COUNT:
        pair = (pick(all_member_ids), pick(open_job_ids))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            benchmark_rows.append(pair)
    with open(benchmark_dir / "application_pairs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["member_id", "job_id"])
        w.writerows(benchmark_rows)

    for i, mid2 in enumerate(all_member_ids):
        member_entry = next((e for e in all_member_entries if e["member_id"] == mid2), {})
        for jid2 in pick_n(open_job_ids, APPS_PER_MEMBER):
            try:
                cur.execute(
                    "INSERT INTO applications (application_id, job_id, member_id, resume_text, cover_letter, status, idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (uid(), jid2, mid2, (member_entry.get("resume_text", ""))[:5000],
                     "I am excited to apply for this position. I bring relevant experience and am confident I can make a meaningful contribution.",
                     pick(WEIGHTED_STATUSES), uid()),
                )
                cur.execute("UPDATE jobs SET applicants_count = applicants_count + 1 WHERE job_id = %s", (jid2,))
                app_count += 1
            except mysql.connector.errors.IntegrityError:
                pass
        show_progress("Applications", i + 1, len(all_member_ids))

    # ── Connections ───────────────────────────────────────────────────────────
    print("\n🤝 Creating connections between members...")
    conn_count = 0
    for a in range(len(demo_member_ids)):
        for b in range(a + 1, len(demo_member_ids)):
            ma, mb = sorted([demo_member_ids[a], demo_member_ids[b]])
            try:
                cur.execute("INSERT INTO connection_requests (request_id, requester_id, receiver_id, status, idempotency_key) VALUES (%s,%s,%s,'accepted',%s)", (uid(), demo_member_ids[a], demo_member_ids[b], uid()))
                cur.execute("INSERT IGNORE INTO connections (member_a, member_b) VALUES (%s,%s)", (ma, mb))
                conn_count += 1
            except mysql.connector.errors.IntegrityError:
                pass

    for demo_id in demo_member_ids:
        for other_id in pick_n([m for m in all_member_ids if m != demo_id], 10):
            ma, mb = sorted([demo_id, other_id])
            try:
                cur.execute("INSERT INTO connection_requests (request_id, requester_id, receiver_id, status, idempotency_key) VALUES (%s,%s,%s,'accepted',%s)", (uid(), demo_id, other_id, uid()))
                cur.execute("INSERT IGNORE INTO connections (member_a, member_b) VALUES (%s,%s)", (ma, mb))
                conn_count += 1
            except mysql.connector.errors.IntegrityError:
                pass

    cur.execute("""
        UPDATE members m
        SET connections_count = (
            SELECT COUNT(*) FROM connections c
            WHERE c.member_a = m.member_id OR c.member_b = m.member_id
        )
    """)
    print(f"  ✓ {conn_count} connections created")

    # ── Messages (MongoDB) ────────────────────────────────────────────────────
    print("\n💬 Seeding messages in MongoDB...")
    threads_col  = db["threads"]
    messages_col = db["messages"]
    msg_count    = 0

    for member_id in demo_member_ids:
        for rec_entry in demo_recruiter_ids:
            thread_id    = uid()
            participants = [member_id, rec_entry["id"]]
            role         = pick(JOB_TITLES)
            skill        = pick(SKILLS)
            num_msgs     = rand_int(4, 8)
            thread_msgs  = []
            for idx in range(num_msgs):
                sender_id = member_id if idx % 2 == 0 else rec_entry["id"]
                text      = CHAT_MESSAGES[idx % len(CHAT_MESSAGES)].replace("{role}", role).replace("{skill}", skill)
                thread_msgs.append({
                    "message_id":      uid(),
                    "thread_id":       thread_id,
                    "sender_id":       sender_id,
                    "message_text":    text,
                    "sent_at":         hours_ago((num_msgs - idx) * 3),
                    "idempotency_key": uid(),
                    "read":            idx < num_msgs - 1,
                })
                msg_count += 1
            threads_col.insert_one({
                "thread_id":       thread_id,
                "participant_ids": participants,
                "last_message":    thread_msgs[-1]["message_text"],
                "updated_at":      utcnow(),
                "created_at":      utcnow(),
            })
            messages_col.insert_many(thread_msgs)

    print(f"  ✓ {msg_count} messages across {len(demo_member_ids) * len(demo_recruiter_ids)} threads")

    # ── Analytics events (MongoDB) ────────────────────────────────────────────
    print("\n📊 Seeding analytics events in MongoDB...")
    event_logs = db["event_logs"]

    EVENT_TYPES = (
        ["job.viewed"] * 35 + ["job.saved"] * 18 + ["application.submitted"] * 22 +
        ["application.status.changed"] * 10 + ["profile.viewed"] * 10 +
        ["connection.requested"] * 3 + ["ai.requests"] * 1 + ["ai.results"] * 1
    )

    events_to_insert = []

    # Deterministic demo analytics
    for i, mid2 in enumerate(demo_member_ids):
        viewer_id = demo_member_ids[(i + 1) % len(demo_member_ids)]
        for d in range(6):
            events_to_insert.append({
                "trace_id": uid(), "timestamp": days_ago(d), "idempotency_key": uid(),
                "_topic": "profile.viewed", "event_type": "profile.viewed",
                "actor_id": viewer_id, "entity": {"entity_type": "member", "entity_id": mid2},
                "payload": {"viewer_id": viewer_id},
            })

    for idx, (mid2, jid2, status) in enumerate(seeded_apps):
        je = next((j for j in job_entries if j["job_id"] == jid2), None)
        me = next((e for e in all_member_entries if e["member_id"] == mid2), {"city": "Unknown", "state": "NA", "country": "USA"})
        if not je:
            continue
        events_to_insert.append({
            "trace_id": uid(), "timestamp": hours_ago((idx + 1) * 12), "idempotency_key": uid(),
            "_topic": "application.submitted", "event_type": "application.submitted",
            "actor_id": mid2, "entity": {"entity_type": "application", "entity_id": uid()},
            "payload": {"application_id": uid(), "job_id": jid2, "member_id": mid2,
                        "recruiter_id": je["recruiter_id"], "city": me["city"], "state": me["state"],
                        "country": me["country"], "location": f"{me['city']}, {me['state']}, {me['country']}", "status": "submitted"},
        })
        if status != "submitted":
            events_to_insert.append({
                "trace_id": uid(), "timestamp": hours_ago(idx * 6), "idempotency_key": uid(),
                "_topic": "application.status.changed", "event_type": "application.status.changed",
                "actor_id": je["recruiter_id"], "entity": {"entity_type": "application", "entity_id": uid()},
                "payload": {"application_id": uid(), "job_id": jid2, "member_id": mid2,
                            "recruiter_id": je["recruiter_id"], "old_status": "submitted", "new_status": status},
            })

    for i in range(NUM_EVENTS):
        ts         = days_ago(rand_int(0, 30)) - timedelta(hours=rand_int(0, 23))
        event_type = pick(EVENT_TYPES)
        me         = pick(all_member_entries)
        other_me   = pick([e for e in all_member_entries if e["member_id"] != me["member_id"]])
        je         = pick(job_entries) if job_entries else {"job_id": uid(), "recruiter_id": uid(), "company_id": uid(), "skills": pick_n(SKILLS, 4)}
        base       = {"trace_id": uid(), "timestamp": ts, "idempotency_key": uid(), "_topic": event_type}

        if event_type == "job.viewed":
            events_to_insert.append({**base, "event_type": event_type, "actor_id": me["member_id"],
                "entity": {"entity_type": "job", "entity_id": je["job_id"]},
                "payload": {"job_id": je["job_id"], "recruiter_id": je["recruiter_id"], "source": pick(["web","mobile"])}})
        elif event_type == "job.saved":
            events_to_insert.append({**base, "event_type": event_type, "actor_id": me["member_id"],
                "entity": {"entity_type": "job", "entity_id": je["job_id"]},
                "payload": {"job_id": je["job_id"], "recruiter_id": je["recruiter_id"]}})
        elif event_type == "application.submitted":
            aid = uid()
            events_to_insert.append({**base, "event_type": event_type, "actor_id": me["member_id"],
                "entity": {"entity_type": "application", "entity_id": aid},
                "payload": {"application_id": aid, "job_id": je["job_id"], "member_id": me["member_id"],
                            "recruiter_id": je["recruiter_id"], "city": me["city"], "state": me["state"],
                            "country": me["country"], "location": f"{me['city']}, {me['state']}, {me['country']}", "status": "submitted"}})
        elif event_type == "application.status.changed":
            aid = uid()
            new_status = pick(["reviewing","interview","offer","rejected"])
            events_to_insert.append({**base, "event_type": event_type, "actor_id": je["recruiter_id"],
                "entity": {"entity_type": "application", "entity_id": aid},
                "payload": {"application_id": aid, "job_id": je["job_id"], "member_id": me["member_id"],
                            "recruiter_id": je["recruiter_id"], "old_status": pick(["submitted","reviewing","interview"]), "new_status": new_status}})
        elif event_type == "profile.viewed":
            events_to_insert.append({**base, "event_type": event_type, "actor_id": other_me["member_id"],
                "entity": {"entity_type": "member", "entity_id": me["member_id"]},
                "payload": {"viewer_id": other_me["member_id"]}})
        elif event_type == "connection.requested":
            rid2 = uid()
            events_to_insert.append({**base, "event_type": event_type, "actor_id": me["member_id"],
                "entity": {"entity_type": "connection", "entity_id": rid2},
                "payload": {"requester_id": me["member_id"], "receiver_id": other_me["member_id"]}})
        elif event_type == "ai.requests":
            tid2 = uid()
            events_to_insert.append({**base, "trace_id": tid2, "event_type": event_type, "actor_id": je["recruiter_id"],
                "entity": {"entity_type": "ai_task", "entity_id": tid2},
                "payload": {"job_id": je["job_id"], "recruiter_id": je["recruiter_id"], "top_k": 5}})
        elif event_type == "ai.results":
            tid2   = uid()
            action = pick(["approve","edit","reject"])
            shortlist = [
                {"member_id": e["member_id"], "match_score": round(random.uniform(0.5, 0.9), 3),
                 "skills_overlap": pick_n(je.get("skills", SKILLS), min(3, len(je.get("skills", SKILLS)))),
                 "explanation": "Synthetic shortlist generated from seeded analytics data."}
                for e in pick_n(all_member_entries, rand_int(1, 3))
            ]
            events_to_insert.append({**base, "trace_id": tid2, "event_type": event_type, "actor_id": je["recruiter_id"],
                "entity": {"entity_type": "ai_task", "entity_id": tid2},
                "payload": {"job_id": je["job_id"], "recruiter_id": je["recruiter_id"],
                            "status": "rejected" if action == "reject" else "approved",
                            "approval_action": action, "shortlist_count": len(shortlist), "shortlist": shortlist}})

    BATCH = 500
    for i in range(0, len(events_to_insert), BATCH):
        event_logs.insert_many(events_to_insert[i:i + BATCH], ordered=False)
        show_progress("Events", min(i + BATCH, len(events_to_insert)), len(events_to_insert))

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n\n" + "═" * 55)
    print("✅  Seed complete! Here's what was created:\n")
    print(f"  👤 Demo members:      {len(demo_member_ids)}")
    print(f"  👥 Total members:     {len(all_member_ids)}")
    print(f"  🏢 Demo recruiters:   {len(demo_recruiter_ids)}")
    print(f"  📋 Total recruiters:  {len(all_recruiter_entries)}")
    print(f"  💼 Job postings:      {len(job_ids)}")
    print(f"  📨 Applications:      ~{app_count}")
    print(f"  🤝 Connections:       {conn_count}")
    print(f"  💬 Messages:          {msg_count}")
    print(f"  📊 Analytics events:  {NUM_EVENTS}")
    print("  📁 Benchmark CSV:     infrastructure/benchmarks/data/application_pairs.csv")
    print("\n" + "─" * 55)
    print("🔑  Demo Login Credentials (all use password: Demo@1234)\n")
    print("  MEMBER ACCOUNTS (job seeker view):")
    print("    alice@demo.com    → Senior Software Engineer")
    print("    bob@demo.com      → Data Engineer")
    print("    carol@demo.com    → ML Engineer")
    print("    david@demo.com    → Full Stack Engineer")
    print("    emma@demo.com     → DevOps Engineer")
    print("\n  RECRUITER ACCOUNTS:")
    print("    recruiter1@google.com  → Google")
    print("    recruiter1@meta.com    → Meta")
    print("    recruiter1@amazon.com  → Amazon")
    print("─" * 55)

    cur.close()
    sql_conn.close()
    mongo.close()


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:
        print(f"\n❌  Seed failed!\n\nError: {exc}")
        print("\n🔧 Troubleshooting checklist:")
        print("  1. Is Docker running?     → docker-compose up -d")
        print("  2. Wait ~15s for MySQL to finish starting up")
        print("  3. Check ports: MySQL on localhost:3307, MongoDB on localhost:27019")
        print("  4. Full error details below:\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
