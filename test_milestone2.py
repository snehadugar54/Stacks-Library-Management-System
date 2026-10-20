import os
os.environ["SECRET_KEY"] = "test-secret-key-m2"
os.environ["LIBRARY_ADMIN_EMAIL"] = "admin@stacks.local"
os.environ["LIBRARY_ADMIN_PASSWORD"] = "admin123"

import unittest
from datetime import date
from app import app, get_db, init_db

class TestMilestone2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.client = app.test_client()

    def login(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    def logout(self):
        return self.client.post("/logout", follow_redirects=True)

    def test_01_admin_login_and_logout_recorded(self):
        self.login("admin@stacks.local", "admin123")
        res = self.client.get("/api/activity-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()
        self.assertTrue(len(logs) > 0)
        latest = logs[0]
        self.assertEqual(latest["user_role"], "admin")
        self.assertEqual(latest["user_name"], "Aditi Rao")
        self.assertEqual(latest["action"], "login")
        self.assertTrue("timestamp" in latest)
        self.logout()

        # Check logout logged
        self.login("admin@stacks.local", "admin123")
        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        logout_log = next((l for l in logs if l["action"] == "logout" and l["user_role"] == "admin"), None)
        self.assertIsNotNone(logout_log)
        self.logout()

    def test_02_librarian_login_recorded(self):
        self.login("librarian@stacks.local", "library123")
        res = self.client.get("/api/activity-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()
        self.assertTrue(len(logs) > 0)
        latest = logs[0]
        self.assertEqual(latest["user_role"], "librarian")
        self.assertEqual(latest["user_name"], "Lina Thomas")
        self.assertEqual(latest["action"], "login")
        self.logout()

    def test_03_librarian_add_book_recorded(self):
        self.login("librarian@stacks.local", "library123")
        import time
        isbn = f"9780000{int(time.time() * 1000) % 1000000:06d}"
        res = self.client.post("/api/books", json={
            "title": "Librarian Novel",
            "author": "Lina T",
            "isbn": isbn,
            "category": "Fiction",
            "total_copies": 3
        })
        self.assertEqual(res.status_code, 201)

        res = self.client.get("/api/activity-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()
        book_log = next((l for l in logs if l["action"] == "add_book" and isbn in l["details"]), None)
        self.assertIsNotNone(book_log)
        self.assertEqual(book_log["user_role"], "librarian")
        self.assertEqual(book_log["user_name"], "Lina Thomas")
        self.logout()

    def test_04_librarian_add_member_recorded(self):
        self.login("librarian@stacks.local", "library123")
        import time
        email = f"member_{int(time.time() * 1000) % 1000000}@example.com"
        res = self.client.post("/api/members", json={
            "name": "New Student",
            "email": email,
            "phone": "+91 99999 88888"
        })
        self.assertEqual(res.status_code, 201)

        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        member_log = next((l for l in logs if l["action"] == "add_member" and email in l["details"]), None)
        self.assertIsNotNone(member_log)
        self.assertEqual(member_log["user_role"], "librarian")
        self.logout()

    def test_05_librarian_issue_and_return_book_recorded(self):
        self.login("librarian@stacks.local", "library123")
        # Issue book 1 to member 1
        res = self.client.post("/api/loans", json={"book_id": 1, "member_id": 1})
        self.assertEqual(res.status_code, 201)

        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        issue_log = next((l for l in logs if l["action"] == "issue_book"), None)
        self.assertIsNotNone(issue_log)
        self.assertEqual(issue_log["user_role"], "librarian")
        self.assertIn("Atomic Habits", issue_log["details"])

        # Find the active loan id to return
        loans_res = self.client.get("/api/loans")
        loans = loans_res.get_json()
        active_loan = next((l for l in loans if l["book_id"] == 1 and not l["returned_on"]), None)
        self.assertIsNotNone(active_loan)

        # Return the book
        ret_res = self.client.post(f"/api/loans/{active_loan['id']}/return")
        self.assertEqual(ret_res.status_code, 200)

        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        return_log = next((l for l in logs if l["action"] == "return_book"), None)
        self.assertIsNotNone(return_log)
        self.assertEqual(return_log["user_role"], "librarian")
        self.logout()

    def test_06_admin_run_overdue_check_recorded(self):
        self.login("admin@stacks.local", "admin123")
        res = self.client.post("/api/automation/overdue")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        overdue_log = next((l for l in logs if l["action"] == "run_overdue_check"), None)
        self.assertIsNotNone(overdue_log)
        self.assertEqual(overdue_log["user_role"], "admin")
        self.logout()

    def test_07_student_cannot_access_activity_log(self):
        self.login("student@stacks.local", "student123")
        res = self.client.get("/api/activity-logs")
        self.assertEqual(res.status_code, 403)
        res_alias = self.client.get("/api/activity-log")
        self.assertEqual(res_alias.status_code, 403)
        self.logout()

    def test_08_unauthenticated_cannot_access_activity_log(self):
        res = self.client.get("/api/activity-logs")
        self.assertEqual(res.status_code, 401)
        res_alias = self.client.get("/api/activity-log")
        self.assertEqual(res_alias.status_code, 401)

    def test_09_student_actions_not_logged_in_staff_history(self):
        self.login("student@stacks.local", "student123")
        # Student views dashboard and loans
        self.client.get("/api/dashboard")
        self.client.get("/api/loans")
        self.logout()

        self.login("admin@stacks.local", "admin123")
        res = self.client.get("/api/activity-logs")
        logs = res.get_json()
        student_logs = [l for l in logs if l["user_role"] == "student"]
        self.assertEqual(len(student_logs), 0)
        self.logout()

    def test_10_existing_automation_logs_intact(self):
        self.login("admin@stacks.local", "admin123")
        res = self.client.get("/api/automation/logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()
        self.assertTrue(isinstance(logs, list))
        # Verify automation_logs columns are still original schema
        if logs:
            first = logs[0]
            for col in ("id", "run_at", "loan_id", "overdue_days", "fine", "status", "message"):
                self.assertIn(col, first)
        self.logout()

if __name__ == "__main__":
    unittest.main()
