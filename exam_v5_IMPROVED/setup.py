#!/usr/bin/env python3
"""
setup.py - One-click setup: installs deps, verifies DB, and launches the app.
Run: python setup.py
"""
import subprocess, sys, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def pip_install():
    print("Installing dependencies from requirements.txt ...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r",
        os.path.join(BASE_DIR, "requirements.txt")
    ])

def verify_db():
    sys.path.insert(0, BASE_DIR)
    from database import init_db
    print("Initialising database ...")
    init_db()
    print("Database ready.")

def launch():
    print("\nLaunching AI Exam Proctoring System ...\n")
    os.chdir(BASE_DIR)
    subprocess.call([sys.executable, "main_app.py"])

if __name__ == "__main__":
    pip_install()
    verify_db()
    launch()
