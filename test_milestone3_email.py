import os
os.environ["SECRET_KEY"] = "test-secret-key-m3"
os.environ["LIBRARY_ADMIN_EMAIL"] = "admin@stacks.local"
os.environ["LIBRARY_ADMIN_PASSWORD"] = "admin123"
os.environ["EMAIL_MODE"] = "mock"

import unittest
from unittest.mock import patch
import email_service
from app import app, init_db

class TestMilestone3Email(unittest.TestCase):
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

    def logout(self):
        return self.client.post("/logout", follow_redirects=True)

    def test_01_email_configuration_reading(self):
        with patch.dict(os.environ, {
            "EMAIL_MODE": "smtp",
            "SMTP_SERVER": "smtp.example.com",
            "SMTP_PORT": "2525",
            "SMTP_USERNAME": "testuser",
            "SMTP_PASSWORD": "secretpassword123",
            "SMTP_USE_TLS": "1",
            "SMTP_FROM_EMAIL": "Library <noreply@example.com>"
        }):
            config = email_service.get_email_config()
            self.assertEqual(config["mode"], "smtp")
            self.assertEqual(config["smtp_server"], "smtp.example.com")
            self.assertEqual(config["smtp_port"], 2525)
            self.assertEqual(config["smtp_username"], "testuser")
            self.assertEqual(config["smtp_password"], "secretpassword123")
            self.assertTrue(config["use_tls"])
            self.assertEqual(config["from_email"], "Library <noreply@example.com>")

    def test_02_email_composition_content(self):
        msg = email_service.compose_overdue_email(
            member_name="Maya Patel",
            member_email="maya@example.com",
            book_title="Clean Code",
            due_on="2026-09-01",
            overdue_days=10,
            fine=20.0,
        )
        self.assertEqual(msg["To"], "maya@example.com")
        self.assertIn("Clean Code", msg["Subject"])
        body = msg.get_content()
        self.assertIn("Maya Patel", body)
        self.assertIn("Clean Code", body)
        self.assertIn("2026-09-01", body)
        self.assertIn("10 days", body)
        self.assertIn("₹20.00", body)
        self.assertIn("Stacks Library Desk", body)

    def test_03_mock_transport_sends_and_stores_email(self):
        email_service.clear_sent_emails()
        success, msg = email_service.send_overdue_email(
            member_name="Maya Patel",
            member_email="maya@example.com",
            book_title="Clean Code",
            due_on="2026-09-01",
            overdue_days=5,
            fine=10.0,
        )
        self.assertTrue(success)
        self.assertIn("maya@example.com", msg)
        sent = email_service.get_sent_emails()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["to"], "maya@example.com")
        self.assertEqual(sent[0]["book_title"], "Clean Code")
        self.assertEqual(sent[0]["fine"], 10.0)

    def test_04_overdue_scan_triggers_email_and_logs(self):
        email_service.clear_sent_emails()
        self.login_admin()

        res = self.client.post("/api/automation/overdue")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("processed", data)
        self.assertIn("results", data)

        if data["processed"] > 0:
            first = data["results"][0]
            self.assertEqual(first["status"], "SUCCESS")
            self.assertIn("email_status", first)
            self.assertEqual(first["email_status"], "SENT")
            self.assertIn("[Email: SENT]", first["message"])

            # Verify email was captured in email_service mock store
            sent = email_service.get_sent_emails()
            self.assertGreaterEqual(len(sent), 1)
            self.assertEqual(sent[0]["to"], first["member_email"])

            # Verify in GET /api/automation/logs
            logs_res = self.client.get("/api/automation/logs")
            self.assertEqual(logs_res.status_code, 200)
            logs = logs_res.get_json()
            self.assertTrue(len(logs) > 0)
            self.assertIn("[Email: SENT]", logs[0]["message"])

        self.logout()

    def test_05_email_failure_resilience_does_not_break_rpa(self):
        # Force email sending to fail
        self.login_admin()
        with patch("app.send_overdue_email", return_value=(False, "Connection refused by mail server")):
            res = self.client.post("/api/automation/overdue")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("results", data)
            if data["processed"] > 0:
                first = data["results"][0]
                # Core RPA must NOT be broken: loan status is still SUCCESS and fine is calculated!
                self.assertEqual(first["status"], "SUCCESS")
                self.assertGreater(first["overdue_days"], 0)
                self.assertGreater(first["projected_fine"], 0)
                self.assertEqual(first["email_status"], "FAILED")
                self.assertIn("[Email: FAILED]", first["message"])

                # Check log record in DB
                logs_res = self.client.get("/api/automation/logs")
                logs = logs_res.get_json()
                self.assertIn("[Email: FAILED]", logs[0]["message"])
        self.logout()

    def test_06_no_credentials_leaked_in_logs_or_messages(self):
        # Even with secret password configured, it should never appear in messages
        with patch.dict(os.environ, {
            "EMAIL_MODE": "smtp",
            "SMTP_SERVER": "invalid.nonexistent.domain",
            "SMTP_PASSWORD": "supersecretpassword999"
        }):
            success, msg = email_service.send_overdue_email(
                member_name="Maya Patel",
                member_email="maya@example.com",
                book_title="Clean Code",
                due_on="2026-09-01",
                overdue_days=5,
                fine=10.0,
            )
            self.assertFalse(success)
            self.assertNotIn("supersecretpassword999", msg)

    def test_07_invalid_email_handled_gracefully(self):
        success, msg = email_service.send_overdue_email(
            member_name="Invalid User",
            member_email="not-an-email",
            book_title="Test Book",
            due_on="2026-09-01",
            overdue_days=3,
            fine=6.0,
        )
        self.assertFalse(success)
        self.assertIn("invalid", msg.lower())

    def test_08_staff_activity_log_includes_email_count(self):
        self.login_admin()
        res = self.client.post("/api/automation/overdue")
        self.assertEqual(res.status_code, 200)

        activity_res = self.client.get("/api/activity-logs")
        self.assertEqual(activity_res.status_code, 200)
        logs = activity_res.get_json()
        overdue_activity = next((l for l in logs if l["action"] == "run_overdue_check"), None)
        self.assertIsNotNone(overdue_activity)
        self.assertIn("processed", overdue_activity["details"])
        self.assertIn("email", overdue_activity["details"])
        self.logout()

    def test_09_test_recipient_override_and_normal_behavior(self):
        # 1. Normal behavior when EMAIL_TEST_RECIPIENT is unset or empty
        email_service.clear_sent_emails()
        with patch.dict(os.environ, {"EMAIL_TEST_RECIPIENT": ""}):
            config = email_service.get_email_config()
            self.assertEqual(config["test_recipient"], "")

            success, msg = email_service.send_overdue_email(
                member_name="Maya Patel",
                member_email="maya@example.com",
                book_title="Clean Code",
                due_on="2026-09-01",
                overdue_days=5,
                fine=10.0,
            )
            self.assertTrue(success)
            self.assertIn("maya@example.com", msg)
            sent = email_service.get_sent_emails()
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["to"], "maya@example.com")
            self.assertEqual(sent[0]["member_name"], "Maya Patel")
            self.assertIn("Dear Maya Patel", sent[0]["body"])

        # 2. Override behavior when EMAIL_TEST_RECIPIENT is non-empty
        email_service.clear_sent_emails()
        override_address = "tester-personal@example.com"
        with patch.dict(os.environ, {"EMAIL_TEST_RECIPIENT": override_address}):
            config = email_service.get_email_config()
            self.assertEqual(config["test_recipient"], override_address)

            success, msg = email_service.send_overdue_email(
                member_name="Maya Patel",
                member_email="maya@example.com",
                book_title="Clean Code",
                due_on="2026-09-01",
                overdue_days=5,
                fine=10.0,
            )
            self.assertTrue(success)
            self.assertIn(override_address, msg)
            sent = email_service.get_sent_emails()
            self.assertEqual(len(sent), 1)
            # Recipient is overridden to EMAIL_TEST_RECIPIENT
            self.assertEqual(sent[0]["to"], override_address)
            # Email body still preserves member and overdue details exactly
            self.assertEqual(sent[0]["member_name"], "Maya Patel")
            self.assertIn("Dear Maya Patel", sent[0]["body"])
            self.assertIn("Clean Code", sent[0]["body"])
            self.assertIn("₹10.00", sent[0]["body"])

        # 3. Invalid EMAIL_TEST_RECIPIENT handled gracefully
        with patch.dict(os.environ, {"EMAIL_TEST_RECIPIENT": "invalid-override-recipient"}):
            success, msg = email_service.send_overdue_email(
                member_name="Maya Patel",
                member_email="maya@example.com",
                book_title="Clean Code",
                due_on="2026-09-01",
                overdue_days=5,
                fine=10.0,
            )
            self.assertFalse(success)
            self.assertIn("invalid", msg.lower())

if __name__ == "__main__":
    unittest.main()
