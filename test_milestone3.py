"""Milestone 3 verification tests — run against a live Flask server on port 5000."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5000"
DB_PATH = Path(__file__).resolve().parent / "library.db"
SESSION = requests.Session()
PASS = "[PASS]"
FAIL = "[FAIL]"
results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))
    tag = PASS if passed else FAIL
    print(f"  {tag} {name}" + (f"  ({detail})" if detail else ""))


def run_tests():
    print("\n=== Milestone 3 Verification ===\n")

    # ---- 1. Database: automation_logs table exists ----
    print("[1] Database schema")
    try:
        conn = sqlite3.connect(DB_PATH)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        record("automation_logs table exists", "automation_logs" in tables, f"tables={tables}")
        if "automation_logs" in tables:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(automation_logs)").fetchall()]
            expected = {"id", "run_at", "loan_id", "member_id", "book_id", "overdue_days", "fine", "status", "message"}
            record("automation_logs has correct columns", expected.issubset(set(cols)), f"cols={cols}")
        # Existing tables still present
        for t in ("books", "members", "loans", "users"):
            record(f"existing table '{t}' intact", t in tables)
        conn.close()
    except Exception as e:
        record("database schema check", False, str(e))

    # ---- 2. Login ----
    print("\n[2] Authentication")
    try:
        r = SESSION.post(f"{BASE}/login", data={"email": "admin@stacks.local", "password": "admin123"}, allow_redirects=False)
        record("admin login", r.status_code in (200, 302), f"status={r.status_code}")
        # Follow redirect to get session cookie
        if r.status_code == 302:
            SESSION.get(BASE + r.headers.get("Location", "/"))
    except Exception as e:
        record("admin login", False, str(e))

    # ---- 3. Existing pages still load ----
    print("\n[3] Existing pages")
    try:
        r = SESSION.get(f"{BASE}/")
        record("index page loads", r.status_code == 200, f"status={r.status_code}")
        r = SESSION.get(f"{BASE}/api/dashboard")
        record("dashboard API", r.status_code == 200, f"status={r.status_code}")
        r = SESSION.get(f"{BASE}/api/books")
        record("books API", r.status_code == 200, f"status={r.status_code}")
        r = SESSION.get(f"{BASE}/api/members")
        record("members API", r.status_code == 200, f"status={r.status_code}")
        r = SESSION.get(f"{BASE}/api/loans")
        record("loans API", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        record("existing pages", False, str(e))

    # ---- 4. Enhanced overdue endpoint ----
    print("\n[4] POST /api/automation/overdue")
    try:
        r = SESSION.post(f"{BASE}/api/automation/overdue", headers={"Content-Type": "application/json"})
        record("overdue endpoint responds", r.status_code == 200, f"status={r.status_code}")
        data = r.json()
        record("response has 'message'", "message" in data, data.get("message", ""))
        record("response has 'processed'", "processed" in data, f"processed={data.get('processed')}")
        record("response has 'results' list", isinstance(data.get("results"), list), f"type={type(data.get('results'))}")
        if data.get("results"):
            first = data["results"][0]
            for field in ("loan_id", "member_id", "member_name", "member_email",
                          "book_id", "book_title", "due_on", "overdue_days",
                          "projected_fine", "status", "message"):
                record(f"result contains '{field}'", field in first)
            record("status is SUCCESS", first.get("status") == "SUCCESS")
            record("projected_fine is numeric", isinstance(first.get("projected_fine"), (int, float)))
        else:
            record("(no overdue loans to verify detail fields)", True, "0 overdue loans found — seed data may have been returned already")
    except Exception as e:
        record("overdue endpoint", False, str(e))

    # ---- 5. automation_logs records created ----
    print("\n[5] automation_logs records")
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM automation_logs").fetchone()[0]
        record("automation_logs has records", count > 0, f"count={count}")
        if count:
            row = conn.execute("SELECT * FROM automation_logs ORDER BY id DESC LIMIT 1").fetchone()
            record("latest log has status", row is not None)
        conn.close()
    except Exception as e:
        record("automation_logs records", False, str(e))

    # ---- 6. GET /api/automation/logs ----
    print("\n[6] GET /api/automation/logs")
    try:
        r = SESSION.get(f"{BASE}/api/automation/logs")
        record("logs endpoint responds", r.status_code == 200, f"status={r.status_code}")
        data = r.json()
        record("returns a list", isinstance(data, list))
        if data:
            first = data[0]
            for field in ("id", "run_at", "loan_id", "overdue_days", "fine",
                          "status", "message", "member_name", "member_email", "book_title"):
                record(f"log contains '{field}'", field in first)
        else:
            record("(no logs yet — expected if no overdue loans)", True)
    except Exception as e:
        record("logs endpoint", False, str(e))

    # ---- 7. Existing issue/return behavior intact ----
    print("\n[7] Existing issue/return behavior")
    try:
        # Check that existing loans.fine column has NOT been modified by overdue scan
        conn = sqlite3.connect(DB_PATH)
        active_fines = conn.execute(
            "SELECT id, fine FROM loans WHERE returned_on IS NULL"
        ).fetchall()
        for loan_id, fine in active_fines:
            record(f"active loan {loan_id} fine unchanged (still {fine})", fine == 0.0, f"fine={fine}")
        conn.close()
    except Exception as e:
        record("issue/return behavior", False, str(e))

    # ---- 8. Auth guard on new endpoint ----
    print("\n[8] Auth guards")
    try:
        anon = requests.Session()
        r = anon.post(f"{BASE}/api/automation/overdue")
        record("overdue rejects unauthenticated", r.status_code == 401, f"status={r.status_code}")
        r = anon.get(f"{BASE}/api/automation/logs")
        record("logs rejects unauthenticated", r.status_code == 401, f"status={r.status_code}")
    except Exception as e:
        record("auth guards", False, str(e))

    # ---- Summary ----
    print("\n" + "=" * 50)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    failed = total - passed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed:
        print("\nFailed tests:")
        for name, p, detail in results:
            if not p:
                print(f"  {FAIL} {name}  ({detail})")
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
