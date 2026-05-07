# database.py - SQLite database layer for the entire system

import sqlite3
import hashlib
import os
from datetime import datetime
from config import DB_PATH, DATA_DIR


def get_connection():
    """Return a new SQLite connection with row_factory set."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ─── Schema Initialisation ────────────────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist and seed initial data."""
    conn = get_connection()
    c = conn.cursor()

    # Students table
    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            department  TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Exam sessions
    c.execute("""
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id      TEXT NOT NULL,
            start_time      TEXT NOT NULL,
            end_time        TEXT,
            status          TEXT DEFAULT 'active',
            score           REAL DEFAULT 0,
            risk_score      REAL DEFAULT 0,
            risk_level      TEXT DEFAULT 'Low Risk',
            FOREIGN KEY (student_id) REFERENCES students(student_id)
        )
    """)

    # Violations log
    c.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            student_id      TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            violation_type  TEXT NOT NULL,
            details         TEXT,
            FOREIGN KEY (session_id) REFERENCES exam_sessions(id)
        )
    """)

    # Exam questions
    c.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question    TEXT NOT NULL,
            option_a    TEXT NOT NULL,
            option_b    TEXT NOT NULL,
            option_c    TEXT NOT NULL,
            option_d    TEXT NOT NULL,
            answer      TEXT NOT NULL,
            category    TEXT DEFAULT 'General',
            difficulty  TEXT DEFAULT 'Medium'
        )
    """)

    # Student answers
    c.execute("""
        CREATE TABLE IF NOT EXISTS student_answers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            student_id  TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            answer      TEXT,
            is_correct  INTEGER DEFAULT 0,
            UNIQUE (session_id, question_id),
            FOREIGN KEY (session_id) REFERENCES exam_sessions(id)
        )
    """)

    conn.commit()
    _seed_data(c, conn)
    conn.close()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _seed_data(c, conn):
    """Insert demo students and 20 real questions if tables are empty."""

    # ── Demo Students ─────────────────────────────────────────────────────────
    demo_students = [
        ("STU001", "Aarav Shah",     "aarav@exam.com",    "pass123",  "Computer Science"),
        ("STU002", "Priya Patel",    "priya@exam.com",    "pass123",  "Information Technology"),
        ("STU003", "Rohan Mehta",    "rohan@exam.com",    "pass123",  "Electronics"),
        ("STU004", "Sneha Joshi",    "sneha@exam.com",    "pass123",  "Mathematics"),
        ("STU005", "Kiran Desai",    "kiran@exam.com",    "pass123",  "Computer Science"),
    ]
    for sid, name, email, pwd, dept in demo_students:
        c.execute(
            "INSERT OR IGNORE INTO students (student_id, name, email, password, department) VALUES (?,?,?,?,?)",
            (sid, name, email, _hash_password(pwd), dept)
        )

    # ── 20 Real Exam Questions ────────────────────────────────────────────────
    c.execute("SELECT COUNT(*) FROM questions")
    if c.fetchone()[0] == 0:
        questions = [
            # Python / Programming
            ("What does the acronym 'OOP' stand for?",
             "Object Oriented Programming", "Open Object Protocol",
             "Operational Online Process", "Optional Object Params",
             "A", "Programming", "Easy"),

            ("Which data structure follows LIFO order?",
             "Queue", "Stack", "Array", "Linked List",
             "B", "Data Structures", "Easy"),

            ("What is the time complexity of binary search?",
             "O(n)", "O(n²)", "O(log n)", "O(1)",
             "C", "Algorithms", "Medium"),

            ("Which keyword is used to handle exceptions in Python?",
             "catch", "try", "handle", "except",
             "D", "Python", "Easy"),

            ("What is a primary key in a relational database?",
             "A key that can have duplicate values",
             "A key that uniquely identifies each record",
             "A foreign reference key",
             "A key used for indexing only",
             "B", "Database", "Easy"),

            ("Which sorting algorithm has the best average-case time complexity?",
             "Bubble Sort", "Selection Sort", "Merge Sort", "Insertion Sort",
             "C", "Algorithms", "Medium"),

            ("What does SQL stand for?",
             "Structured Query Language", "Simple Query Logic",
             "Standard Question Library", "Sequential Query Layer",
             "A", "Database", "Easy"),

            ("Which of the following is NOT a Python built-in data type?",
             "List", "Dictionary", "Array", "Tuple",
             "C", "Python", "Easy"),

            ("In networking, what does HTTP stand for?",
             "HyperText Transfer Protocol", "High Traffic Transfer Process",
             "HyperText Transmission Path", "Host Transfer Text Protocol",
             "A", "Networking", "Easy"),

            ("What is the output of: print(type([]))?",
             "<class 'dict'>", "<class 'tuple'>",
             "<class 'list'>", "<class 'set'>",
             "C", "Python", "Easy"),

            ("Which concept allows a class to inherit properties from another class?",
             "Polymorphism", "Encapsulation", "Inheritance", "Abstraction",
             "C", "OOP", "Easy"),

            ("What is a deadlock in operating systems?",
             "A process using 100% CPU",
             "Two processes each waiting for the other to release resources",
             "Memory overflow error",
             "A crashed system process",
             "B", "Operating Systems", "Medium"),

            ("Which layer of the OSI model handles routing?",
             "Data Link", "Transport", "Network", "Session",
             "C", "Networking", "Medium"),

            ("What does RAM stand for?",
             "Random Access Memory", "Read Accessible Module",
             "Rapid Action Memory", "Random Array Module",
             "A", "Computer Hardware", "Easy"),

            ("In Python, what does the 'self' keyword refer to?",
             "The module itself", "The parent class",
             "The current instance of the class", "A global variable",
             "C", "Python", "Easy"),

            ("Which protocol is used to send emails?",
             "FTP", "HTTP", "SMTP", "SSH",
             "C", "Networking", "Medium"),

            ("What is Big O notation used to describe?",
             "Memory allocation size",
             "Algorithm efficiency / time complexity",
             "Network bandwidth",
             "Database query size",
             "B", "Algorithms", "Medium"),

            ("Which of the following is a NoSQL database?",
             "MySQL", "PostgreSQL", "MongoDB", "SQLite",
             "C", "Database", "Medium"),

            ("What is the purpose of a compiler?",
             "Run code line by line",
             "Translate high-level language to machine code",
             "Debug source code",
             "Manage memory allocation",
             "B", "Computer Science", "Easy"),

            ("Which design pattern ensures only one instance of a class exists?",
             "Factory Pattern", "Observer Pattern",
             "Singleton Pattern", "Decorator Pattern",
             "C", "Design Patterns", "Hard"),
        ]
        c.executemany(
            """INSERT INTO questions
               (question, option_a, option_b, option_c, option_d, answer, category, difficulty)
               VALUES (?,?,?,?,?,?,?,?)""",
            questions
        )
    conn.commit()


# ─── Student CRUD ─────────────────────────────────────────────────────────────

def authenticate_student(student_id: str, password: str):
    """Return student row if credentials match, else None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM students WHERE student_id=? AND password=?",
        (student_id, _hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_student(student_id, name, email, password, department=""):
    """Insert a new student. Returns (True, msg) or (False, error)."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO students (student_id, name, email, password, department) VALUES (?,?,?,?,?)",
            (student_id, name, email, _hash_password(password), department)
        )
        conn.commit()
        conn.close()
        return True, "Student added successfully."
    except sqlite3.IntegrityError as e:
        return False, f"Duplicate entry: {e}"


def get_all_students():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_student(student_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM students WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()


# ─── Session Management ───────────────────────────────────────────────────────

def start_session(student_id: str) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO exam_sessions (student_id, start_time) VALUES (?,?)",
        (student_id, datetime.now().isoformat())
    )
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id: int, score: float, risk_score: float, risk_level: str):
    conn = get_connection()
    conn.execute(
        """UPDATE exam_sessions SET end_time=?, status='completed',
           score=?, risk_score=?, risk_level=? WHERE id=?""",
        (datetime.now().isoformat(), score, risk_score, risk_level, session_id)
    )
    conn.commit()
    conn.close()


def get_all_sessions():
    conn = get_connection()
    rows = conn.execute("""
        SELECT es.*, s.name, s.department
        FROM exam_sessions es
        JOIN students s ON es.student_id = s.student_id
        ORDER BY es.start_time DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Violations ───────────────────────────────────────────────────────────────

def log_violation(session_id: int, student_id: str, violation_type: str, details: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO violations (session_id, student_id, timestamp, violation_type, details) VALUES (?,?,?,?,?)",
        (session_id, student_id, datetime.now().isoformat(), violation_type, details)
    )
    conn.commit()
    conn.close()


def get_violations(student_id: str = None, session_id: int = None):
    conn = get_connection()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM violations WHERE session_id=? ORDER BY timestamp",
            (session_id,)
        ).fetchall()
    elif student_id:
        rows = conn.execute(
            "SELECT * FROM violations WHERE student_id=? ORDER BY timestamp DESC",
            (student_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM violations ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_violation_counts(session_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT violation_type, COUNT(*) as cnt FROM violations WHERE session_id=? GROUP BY violation_type",
        (session_id,)
    ).fetchall()
    conn.close()
    return {r["violation_type"]: r["cnt"] for r in rows}


# ─── Questions & Answers ──────────────────────────────────────────────────────

def get_all_questions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM questions ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_answer(session_id: int, student_id: str, question_id: int, answer: str, is_correct: bool):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO student_answers
           (session_id, student_id, question_id, answer, is_correct) VALUES (?,?,?,?,?)""",
        (session_id, student_id, question_id, answer, int(is_correct))
    )
    conn.commit()
    conn.close()


def get_student_score(session_id: int) -> tuple:
    """Returns (correct_count, total_answered)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT SUM(is_correct) as correct, COUNT(*) as total FROM student_answers WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()
    correct = row["correct"] or 0
    total = row["total"] or 0
    return correct, total


# ─── Exam Configuration (Teacher Settings) ───────────────────────────────────

def init_exam_config():
    """Create exam_config and exam_questions_config tables if not present."""
    conn = get_connection()
    c = conn.cursor()

    # Global exam settings
    c.execute("""
        CREATE TABLE IF NOT EXISTS exam_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Which question IDs are active for the exam
    c.execute("""
        CREATE TABLE IF NOT EXISTS exam_question_selection (
            question_id INTEGER PRIMARY KEY,
            is_active   INTEGER DEFAULT 1
        )
    """)

    # Seed defaults if empty
    defaults = {
        "exam_duration_minutes": "30",
        "exam_title": "General Knowledge Exam",
        "max_violations_before_alert": "5",
        "randomize_questions": "0",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO exam_config (key, value) VALUES (?,?)", (k, v))

    # Default: all questions active
    c.execute("SELECT id FROM questions")
    for row in c.fetchall():
        c.execute(
            "INSERT OR IGNORE INTO exam_question_selection (question_id, is_active) VALUES (?,1)",
            (row["id"],)
        )
    conn.commit()
    conn.close()


def get_exam_config() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM exam_config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_exam_config(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO exam_config (key, value) VALUES (?,?)",
        (key, value)
    )
    conn.commit()
    conn.close()


def get_active_questions() -> list:
    """Return only the questions marked active for the exam."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT q.* FROM questions q
        JOIN exam_question_selection eqs ON q.id = eqs.question_id
        WHERE eqs.is_active = 1
        ORDER BY q.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_question_active(question_id: int, is_active: bool):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO exam_question_selection (question_id, is_active) VALUES (?,?)",
        (question_id, int(is_active))
    )
    conn.commit()
    conn.close()


def set_all_questions_active(is_active: bool):
    conn = get_connection()
    conn.execute("UPDATE exam_question_selection SET is_active=?", (int(is_active),))
    conn.commit()
    conn.close()


def add_question(question, option_a, option_b, option_c, option_d, answer, category="General", difficulty="Medium"):
    """Insert a new question and mark it active."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """INSERT INTO questions
           (question, option_a, option_b, option_c, option_d, answer, category, difficulty)
           VALUES (?,?,?,?,?,?,?,?)""",
        (question, option_a, option_b, option_c, option_d, answer.upper(), category, difficulty)
    )
    qid = c.lastrowid
    c.execute("INSERT INTO exam_question_selection (question_id, is_active) VALUES (?,1)", (qid,))
    conn.commit()
    conn.close()
    return qid


def delete_question(question_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM questions WHERE id=?", (question_id,))
    conn.execute("DELETE FROM exam_question_selection WHERE question_id=?", (question_id,))
    conn.commit()
    conn.close()


def update_question(question_id, question, option_a, option_b, option_c, option_d, answer, category, difficulty):
    conn = get_connection()
    conn.execute("""
        UPDATE questions SET question=?, option_a=?, option_b=?, option_c=?,
        option_d=?, answer=?, category=?, difficulty=? WHERE id=?
    """, (question, option_a, option_b, option_c, option_d, answer.upper(), category, difficulty, question_id))
    conn.commit()
    conn.close()
