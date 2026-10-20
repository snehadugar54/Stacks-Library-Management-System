import os
os.environ["SECRET_KEY"] = "test-secret-key-m4"
os.environ["LIBRARY_ADMIN_EMAIL"] = "admin@stacks.local"
os.environ["LIBRARY_ADMIN_PASSWORD"] = "admin123"
os.environ["EMAIL_MODE"] = "mock"

import csv
import io
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import email_service
from app import app, get_db, init_db, today

class TestMilestone4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.client = app.test_client()
        email_service.clear_sent_emails()

    def login_admin(self):
        return self.client.post("/login", data={
            "email": "admin@stacks.local",
            "password": "admin123"
        }, follow_redirects=True)

    def login_librarian(self):
        return self.client.post("/login", data={
            "email": "librarian@stacks.local",
            "password": "library123"
        }, follow_redirects=True)

    def login_student(self):
        return self.client.post("/login", data={
            "email": "student@stacks.local",
            "password": "student123"
        }, follow_redirects=True)

    def logout(self):
        return self.client.post("/logout", follow_redirects=True)

    def test_01_courtesy_email_composition(self):
        msg = email_service.compose_courtesy_email(
            member_name="Ishaan Verma",
            member_email="ishaan@example.com",
            book_title="Atomic Habits",
            due_on="2026-10-07",
            days_until_due=1,
        )
        self.assertEqual(msg["To"], "ishaan@example.com")
        self.assertIn("Courtesy Notice", msg["Subject"])
        self.assertIn("Atomic Habits", msg["Subject"])
        body = msg.get_content()
        self.assertIn("Ishaan Verma", body)
        self.assertIn("tomorrow", body)
        self.assertIn("2026-10-07", body)
        self.assertIn("Stacks Library Desk", body)

    def test_02_courtesy_email_mock_transport(self):
        email_service.clear_sent_emails()
        success, msg = email_service.send_courtesy_email(
            member_name="Ishaan Verma",
            member_email="ishaan@example.com",
            book_title="The Alchemist",
            due_on="2026-10-07",
            days_until_due=1,
        )
        self.assertTrue(success)
        self.assertIn("ishaan@example.com", msg)
        sent = email_service.get_sent_emails()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["to"], "ishaan@example.com")
        self.assertEqual(sent[0]["book_title"], "The Alchemist")
        self.assertEqual(sent[0]["email_type"], "courtesy")

    def test_03_courtesy_automation_scans_and_logs(self):
        # Insert a loan specifically due tomorrow to ensure test determinism
        with app.app_context():
            db = get_db()
            due_tomorrow = (today() + timedelta(days=1)).isoformat()
            db.execute(
                "INSERT INTO loans (book_id, member_id, issued_on, due_on) VALUES (1, 3, ?, ?)",
                (today().isoformat(), due_tomorrow)
            )
            db.commit()

        self.login_admin()
        res = self.client.post("/api/automation/courtesy")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("processed", data)
        self.assertGreater(data["processed"], 0)
        self.assertIn("results", data)

        first = data["results"][0]
        self.assertEqual(first["status"], "SUCCESS")
        self.assertIn("email_status", first)
        self.assertEqual(first["email_status"], "SENT")
        self.assertIn("[Email: SENT]", first["message"])

        # Verify record in GET /api/automation/logs
        logs_res = self.client.get("/api/automation/logs")
        self.assertEqual(logs_res.status_code, 200)
        logs = logs_res.get_json()
        courtesy_log = next((l for l in logs if "Courtesy reminder" in l["message"]), None)
        self.assertIsNotNone(courtesy_log)
        self.assertEqual(courtesy_log["status"], "SUCCESS")
        self.assertEqual(courtesy_log["fine"], 0.0)
        self.assertEqual(courtesy_log["overdue_days"], 0)
        self.logout()

    def test_04_courtesy_automation_email_failure_resilience(self):
        self.login_admin()
        with patch("app.send_courtesy_email", return_value=(False, "SMTP mock delivery failed")):
            res = self.client.post("/api/automation/courtesy")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            if data["processed"] > 0:
                first = data["results"][0]
                self.assertEqual(first["status"], "SUCCESS")
                self.assertEqual(first["email_status"], "FAILED")
                self.assertIn("[Email: FAILED]", first["message"])
        self.logout()

    def test_05_inventory_audit_endpoint_and_calculations(self):
        self.login_librarian()
        res = self.client.post("/api/automation/inventory-audit")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("total_titles", data)
        self.assertIn("depleted_titles", data)
        self.assertIn("low_stock_titles", data)
        self.assertIn("healthy_titles", data)
        self.assertIn("results", data)
        self.assertGreaterEqual(data["total_titles"], 4)

        first = data["results"][0]
        for field in ("book_id", "title", "author", "isbn", "category", "total_copies",
                      "available_copies", "active_loans", "utilization_pct", "stock_status",
                      "recommended_reorder"):
            self.assertIn(field, first)
        self.logout()

    def test_06_inventory_audit_csv_export(self):
        self.login_librarian()
        res = self.client.get("/api/reports/inventory-audit.csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        self.assertIn("library-inventory-audit.csv", res.headers.get("Content-Disposition", ""))

        csv_text = res.data.decode("utf-8")
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 2)
        header = rows[0]
        expected_cols = ["Book ID", "Title", "Author", "ISBN", "Category", "Total Copies", "Available Copies", "Utilization %", "Stock Status", "Recommended Reorder"]
        for col in expected_cols:
            self.assertIn(col, header)
        self.logout()

    def test_07_staff_activity_logging_for_m4_actions(self):
        self.login_admin()
        self.client.post("/api/automation/courtesy")
        self.client.post("/api/automation/inventory-audit")

        act_res = self.client.get("/api/activity-logs")
        self.assertEqual(act_res.status_code, 200)
        logs = act_res.get_json()

        courtesy_act = next((l for l in logs if l["action"] == "run_courtesy_check"), None)
        self.assertIsNotNone(courtesy_act)
        self.assertEqual(courtesy_act["user_role"], "admin")

        audit_act = next((l for l in logs if l["action"] == "run_inventory_audit"), None)
        self.assertIsNotNone(audit_act)
        self.assertEqual(audit_act["user_role"], "admin")
        self.logout()

    def test_08_role_permissions_for_m4_endpoints(self):
        # 1. Student permissions
        self.login_student()
        self.assertEqual(self.client.post("/api/automation/courtesy").status_code, 403)
        self.assertEqual(self.client.post("/api/automation/inventory-audit").status_code, 403)
        self.assertEqual(self.client.get("/api/reports/inventory-audit.csv").status_code, 403)
        self.logout()

        # 2. Unauthenticated permissions
        self.assertEqual(self.client.post("/api/automation/courtesy").status_code, 401)
        self.assertEqual(self.client.post("/api/automation/inventory-audit").status_code, 401)
        self.assertEqual(self.client.get("/api/reports/inventory-audit.csv").status_code, 401)

        # 3. Librarian permissions (allowed inventory audit & CSV, blocked from admin-only courtesy scan)
        self.login_librarian()
        self.assertEqual(self.client.post("/api/automation/courtesy").status_code, 403)
        self.assertEqual(self.client.post("/api/automation/inventory-audit").status_code, 200)
        self.assertEqual(self.client.get("/api/reports/inventory-audit.csv").status_code, 200)
        self.logout()

    def test_09_daily_reconciliation_digest_endpoint_and_email(self):
        email_service.clear_sent_emails()
        self.login_admin()
        res = self.client.post("/api/automation/daily-reconciliation")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("message", data)
        self.assertIn("summary", data)
        self.assertEqual(data["email_status"], "SENT")
        self.assertIn("recipient", data)

        summary = data["summary"]
        for key in ("books_issued_today", "books_returned_today", "fines_assessed_today",
                    "total_pending_fines", "active_overdue_count", "total_active_loans", "new_members_today"):
            self.assertIn(key, summary)

        sent = email_service.get_sent_emails()
        digest_emails = [e for e in sent if e.get("email_type") == "reconciliation_digest"]
        self.assertEqual(len(digest_emails), 1)
        self.assertIn("Daily Circulation & Reconciliation Digest", digest_emails[0]["subject"])
        self.assertIn("Summary of Operations", digest_emails[0]["body"])

        act_res = self.client.get("/api/activity-logs")
        logs = act_res.get_json()
        rec_log = next((l for l in logs if l["action"] == "run_daily_reconciliation"), None)
        self.assertIsNotNone(rec_log)
        self.assertEqual(rec_log["user_role"], "admin")
        self.logout()

    def test_10_member_invitations_endpoint_and_email(self):
        email_service.clear_sent_emails()
        import time
        email = f"unactivated_{int(time.time() * 1000) % 1000000}@example.com"
        with app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)",
                ("Test Unactivated", email, "+91 99999 11111", today().isoformat())
            )
            db.commit()

        self.login_librarian()
        res = self.client.post("/api/automation/member-invitations")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("processed", data)
        self.assertGreater(data["processed"], 0)
        self.assertIn("emails_sent", data)
        self.assertGreater(data["emails_sent"], 0)
        self.assertIn("results", data)

        target_res = next((r for r in data["results"] if r["member_email"] == email), None)
        self.assertIsNotNone(target_res)
        self.assertEqual(target_res["status"], "SUCCESS")
        self.assertEqual(target_res["email_status"], "SENT")

        sent = email_service.get_sent_emails()
        invite_emails = [e for e in sent if e.get("email_type") == "activation_invitation" and e.get("to") == email]
        self.assertEqual(len(invite_emails), 1)
        self.assertIn("Activate Your Stacks Library", invite_emails[0]["subject"])
        self.assertIn("/activate", invite_emails[0]["body"])

        act_res = self.client.get("/api/activity-logs")
        logs = act_res.get_json()
        invite_log = next((l for l in logs if l["action"] == "run_member_invitations"), None)
        self.assertIsNotNone(invite_log)
        self.assertEqual(invite_log["user_role"], "librarian")
        self.logout()

    def test_11_role_permissions_for_new_automations(self):
        self.login_student()
        self.assertEqual(self.client.post("/api/automation/daily-reconciliation").status_code, 403)
        self.assertEqual(self.client.post("/api/automation/member-invitations").status_code, 403)
        self.logout()

        self.assertEqual(self.client.post("/api/automation/daily-reconciliation").status_code, 401)
        self.assertEqual(self.client.post("/api/automation/member-invitations").status_code, 401)

        self.login_librarian()
        self.assertEqual(self.client.post("/api/automation/daily-reconciliation").status_code, 403)
        self.assertEqual(self.client.post("/api/automation/member-invitations").status_code, 200)
        self.logout()

    def test_12_books_csv_template_download(self):
        self.login_librarian()
        res = self.client.get("/api/templates/books-template.csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        self.assertIn("library-books-template.csv", res.headers.get("Content-Disposition", ""))
        text = res.data.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0], ["Title", "Author", "ISBN", "Category", "Copies"])
        self.logout()

    def test_13_bulk_catalogue_csv_ingestion(self):
        self.login_librarian()
        import time
        unique_isbn = f"978999{int(time.time() * 1000) % 1000000:06d}"
        existing_isbn = "9780132350884" # Clean Code

        # Check existing Clean Code copies before ingestion
        with app.app_context():
            db = get_db()
            before_row = db.execute("SELECT total_copies, available_copies FROM books WHERE isbn = ?", (existing_isbn,)).fetchone()
            before_total = before_row["total_copies"]
            before_avail = before_row["available_copies"]

        csv_content = (
            "Title,Author,ISBN,Category,Copies\n"
            f"Automated Testing Patterns,Gerard Meszaros,{unique_isbn},Engineering,4\n"
            f"Clean Code,Robert C. Martin,{existing_isbn},Software Engineering,2\n"
        )

        res = self.client.post("/api/automation/books/import-csv", json={"csv_data": csv_content})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("inserted_count", data)
        self.assertEqual(data["inserted_count"], 1)
        self.assertEqual(data["updated_count"], 1)
        self.assertEqual(data["skipped_count"], 0)

        with app.app_context():
            db = get_db()
            new_book = db.execute("SELECT * FROM books WHERE isbn = ?", (unique_isbn,)).fetchone()
            self.assertIsNotNone(new_book)
            self.assertEqual(new_book["title"], "Automated Testing Patterns")
            self.assertEqual(new_book["total_copies"], 4)
            self.assertEqual(new_book["available_copies"], 4)

            updated_book = db.execute("SELECT * FROM books WHERE isbn = ?", (existing_isbn,)).fetchone()
            self.assertEqual(updated_book["total_copies"], before_total + 2)
            self.assertEqual(updated_book["available_copies"], before_avail + 2)

        act_res = self.client.get("/api/activity-logs")
        logs = act_res.get_json()
        import_log = next((l for l in logs if l["action"] == "bulk_book_import"), None)
        self.assertIsNotNone(import_log)
        self.assertEqual(import_log["user_role"], "librarian")
        self.logout()

    def test_14_bulk_catalogue_csv_validation_and_skips(self):
        self.login_librarian()
        csv_content = (
            "Title,Author,ISBN,Category,Copies\n"
            ",Missing Author & Title,9781111111111,Category,2\n"
            "Bad Copies Book,Some Author,9782222222222,Tech,-5\n"
            "Invalid Copies String,Some Author,9783333333333,Tech,abc\n"
        )
        res = self.client.post("/api/automation/books/import-csv", json={"csv_data": csv_content})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["inserted_count"], 0)
        self.assertEqual(data["updated_count"], 0)
        self.assertEqual(data["skipped_count"], 3)
        self.assertEqual(len(data["skipped"]), 3)
        self.logout()

    def test_15_bulk_catalogue_rbac(self):
        # Student: blocked
        self.login_student()
        self.assertEqual(self.client.get("/api/templates/books-template.csv").status_code, 403)
        self.assertEqual(self.client.post("/api/automation/books/import-csv", json={"csv_data": ""}).status_code, 403)
        self.logout()

        # Unauthenticated: blocked
        self.assertEqual(self.client.get("/api/templates/books-template.csv").status_code, 401)
        self.assertEqual(self.client.post("/api/automation/books/import-csv", json={"csv_data": ""}).status_code, 401)

        # Admin: allowed
        self.login_admin()
        self.assertEqual(self.client.get("/api/templates/books-template.csv").status_code, 200)
        res = self.client.post("/api/automation/books/import-csv", json={"csv_data": "Title,Author,ISBN,Category,Copies\n"})
        self.assertEqual(res.status_code, 200)
        self.logout()

if __name__ == "__main__":
    unittest.main()
