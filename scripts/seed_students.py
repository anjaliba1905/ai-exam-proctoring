#!/usr/bin/env python3
"""
scripts/seed_students.py
========================
Creates student accounts on the deployed backend via the admin API.

Usage:
    export PROCTORING_API_URL=https://ai-exam-proctoring-api.onrender.com
    export ADMIN_PASSWORD=your_admin_password
    python scripts/seed_students.py

Or edit STUDENTS list below and run directly.

You can also pass a CSV file:
    python scripts/seed_students.py --csv students.csv
    (CSV columns: student_id,name,email,password,department)
"""

import os
import sys
import csv
import argparse
import requests

API_URL        = os.environ.get("PROCTORING_API_URL", "").rstrip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ── Hardcoded student list (edit or replace with --csv) ───────────────────────
STUDENTS = [
    # {"student_id": "S001", "name": "Alice Patel",  "email": "alice@example.com",  "password": "SecurePass1!", "department": "CS"},
    # {"student_id": "S002", "name": "Bob Sharma",   "email": "bob@example.com",    "password": "SecurePass2!", "department": "IT"},
]


def create_student(session: requests.Session, student: dict) -> bool:
    try:
        resp = session.post(
            f"{API_URL}/admin/students",
            json=student,
            timeout=15,
        )
        if resp.status_code == 201:
            print(f"  ✓ Created: {student['student_id']} ({student['name']})")
            return True
        elif resp.status_code == 409:
            print(f"  ⚠ Already exists: {student['student_id']}")
            return True
        else:
            print(f"  ✗ Failed {student['student_id']}: HTTP {resp.status_code} — {resp.text[:120]}")
            return False
    except Exception as e:
        print(f"  ✗ Error {student['student_id']}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Seed student accounts into proctoring API")
    parser.add_argument("--csv", help="Path to CSV file with student data")
    parser.add_argument("--api-url", help="Override PROCTORING_API_URL")
    parser.add_argument("--admin-password", help="Override ADMIN_PASSWORD")
    args = parser.parse_args()

    api_url = (args.api_url or API_URL).rstrip("/")
    admin_pw = args.admin_password or ADMIN_PASSWORD

    if not api_url:
        print("ERROR: Set PROCTORING_API_URL or pass --api-url")
        sys.exit(1)
    if not admin_pw:
        print("ERROR: Set ADMIN_PASSWORD or pass --admin-password")
        sys.exit(1)

    students = list(STUDENTS)
    if args.csv:
        with open(args.csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            students = list(reader)
        print(f"Loaded {len(students)} students from {args.csv}")

    if not students:
        print("No students to create. Edit STUDENTS list or pass --csv.")
        sys.exit(0)

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {admin_pw}"

    print(f"\nSeeding {len(students)} student(s) → {api_url}\n")
    ok = sum(create_student(session, s) for s in students)
    print(f"\nDone: {ok}/{len(students)} succeeded.")


if __name__ == "__main__":
    main()
