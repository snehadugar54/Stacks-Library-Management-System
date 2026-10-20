from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

# In-memory store for mock/test mode
_SENT_EMAILS: list[dict[str, Any]] = []


def get_email_config() -> dict[str, Any]:
    mode = os.getenv("EMAIL_MODE", "").strip().lower()
    smtp_server = os.getenv("SMTP_SERVER", "").strip()

    # Determine mode: default to 'mock' if not explicitly configured or if server is unset
    if not mode:
        mode = "smtp" if smtp_server else "mock"

    port_str = os.getenv("SMTP_PORT", "").strip()
    try:
        smtp_port = int(port_str) if port_str else 587
    except ValueError:
        smtp_port = 587

    use_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() in {"1", "true", "yes", "on"}
    use_ssl = os.getenv("SMTP_USE_SSL", "0").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "mode": mode,
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "smtp_username": os.getenv("SMTP_USERNAME", "").strip(),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "from_email": os.getenv("SMTP_FROM_EMAIL", "Stacks Library <library@stacks.local>").strip(),
        "test_recipient": os.getenv("EMAIL_TEST_RECIPIENT", "").strip(),
        "timeout": 10,
    }


def clear_sent_emails() -> None:
    _SENT_EMAILS.clear()


def get_sent_emails() -> list[dict[str, Any]]:
    return list(_SENT_EMAILS)


def compose_overdue_email(
    member_name: str,
    member_email: str,
    book_title: str,
    due_on: str,
    overdue_days: int,
    fine: float,
    recipient_override: str | None = None,
) -> EmailMessage:
    config = get_email_config()
    msg = EmailMessage()
    msg["Subject"] = f"Overdue Library Book Notice: {book_title}"
    msg["From"] = config["from_email"]
    msg["To"] = recipient_override or config.get("test_recipient") or member_email

    body_text = (
        f"Dear {member_name},\n\n"
        f"This is an automated overdue reminder from Stacks Library.\n\n"
        f"The following loan is currently overdue:\n"
        f"  - Book Title: {book_title}\n"
        f"  - Due Date: {due_on}\n"
        f"  - Overdue by: {overdue_days} day{'s' if overdue_days != 1 else ''}\n"
        f"  - Current Fine Assessed: ₹{fine:.2f}\n\n"
        f"Please return the book to the library desk and clear any outstanding dues as soon as possible.\n\n"
        f"Thank you,\n"
        f"Stacks Library Desk\n"
    )
    msg.set_content(body_text)
    return msg


def send_overdue_email(
    member_name: str,
    member_email: str,
    book_title: str,
    due_on: str,
    overdue_days: int,
    fine: float,
) -> tuple[bool, str]:
    if not member_email or "@" not in member_email:
        return False, "Missing or invalid recipient email address"

    config = get_email_config()
    mode = config["mode"]
    test_recipient = config.get("test_recipient", "")
    target_email = test_recipient if test_recipient else member_email

    if test_recipient and "@" not in test_recipient:
        return False, "Missing or invalid test recipient email address"

    try:
        msg = compose_overdue_email(
            member_name=member_name,
            member_email=member_email,
            book_title=book_title,
            due_on=due_on,
            overdue_days=overdue_days,
            fine=fine,
            recipient_override=target_email,
        )

        record = {
            "to": target_email,
            "member_name": member_name,
            "book_title": book_title,
            "due_on": due_on,
            "overdue_days": overdue_days,
            "fine": fine,
            "subject": msg["Subject"],
            "body": msg.get_content(),
            "mode": mode,
        }

        if mode in ("mock", "test"):
            _SENT_EMAILS.append(record)
            return True, f"Email queued in mock outbox for {target_email}"

        if mode == "console":
            _SENT_EMAILS.append(record)
            print(f"[EMAIL SERVICE - CONSOLE] To: {target_email} | Subject: {msg['Subject']}")
            return True, f"Email logged to console for {target_email}"

        if mode == "smtp":
            server = config["smtp_server"]
            if not server:
                return False, "SMTP server is not configured (SMTP_SERVER empty)"

            port = config["smtp_port"]
            timeout = config["timeout"]
            username = config["smtp_username"]
            password = config["smtp_password"]

            if config["use_ssl"]:
                smtp_cls = smtplib.SMTP_SSL
            else:
                smtp_cls = smtplib.SMTP

            with smtp_cls(server, port, timeout=timeout) as smtp:
                if not config["use_ssl"] and config["use_tls"]:
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            _SENT_EMAILS.append(record)
            return True, f"Email sent via SMTP to {target_email}"

        return False, f"Unknown email mode: {mode}"

    except Exception as exc:
        err_msg = str(exc)
        # Sanitize any password if inadvertently contained in error string
        pwd = config.get("smtp_password")
        if pwd and pwd in err_msg:
            err_msg = err_msg.replace(pwd, "******")
        return False, f"SMTP error: {err_msg}"


def compose_courtesy_email(
    member_name: str,
    member_email: str,
    book_title: str,
    due_on: str,
    days_until_due: int = 1,
    recipient_override: str | None = None,
) -> EmailMessage:
    config = get_email_config()
    msg = EmailMessage()
    msg["Subject"] = f"Courtesy Notice: Upcoming Due Date for {book_title}"
    msg["From"] = config["from_email"]
    msg["To"] = recipient_override or config.get("test_recipient") or member_email

    time_phrase = "today" if days_until_due == 0 else "tomorrow" if days_until_due == 1 else f"in {days_until_due} days"
    body_text = (
        f"Dear {member_name},\n\n"
        f"This is an automated courtesy reminder from Stacks Library.\n\n"
        f"The following loan is due {time_phrase}:\n"
        f"  - Book Title: {book_title}\n"
        f"  - Due Date: {due_on}\n\n"
        f"Please return or renew the book on or before the due date to avoid overdue charges (₹2.00/day).\n\n"
        f"Thank you,\n"
        f"Stacks Library Desk\n"
    )
    msg.set_content(body_text)
    return msg


def send_courtesy_email(
    member_name: str,
    member_email: str,
    book_title: str,
    due_on: str,
    days_until_due: int = 1,
) -> tuple[bool, str]:
    if not member_email or "@" not in member_email:
        return False, "Missing or invalid recipient email address"

    config = get_email_config()
    mode = config["mode"]
    test_recipient = config.get("test_recipient", "")
    target_email = test_recipient if test_recipient else member_email

    if test_recipient and "@" not in test_recipient:
        return False, "Missing or invalid test recipient email address"

    try:
        msg = compose_courtesy_email(
            member_name=member_name,
            member_email=member_email,
            book_title=book_title,
            due_on=due_on,
            days_until_due=days_until_due,
            recipient_override=target_email,
        )

        record = {
            "to": target_email,
            "member_name": member_name,
            "book_title": book_title,
            "due_on": due_on,
            "days_until_due": days_until_due,
            "subject": msg["Subject"],
            "body": msg.get_content(),
            "mode": mode,
            "email_type": "courtesy",
        }

        if mode in ("mock", "test"):
            _SENT_EMAILS.append(record)
            return True, f"Email queued in mock outbox for {target_email}"

        if mode == "console":
            _SENT_EMAILS.append(record)
            print(f"[EMAIL SERVICE - CONSOLE] To: {target_email} | Subject: {msg['Subject']}")
            return True, f"Email logged to console for {target_email}"

        if mode == "smtp":
            server = config["smtp_server"]
            if not server:
                return False, "SMTP server is not configured (SMTP_SERVER empty)"

            port = config["smtp_port"]
            timeout = config["timeout"]
            username = config["smtp_username"]
            password = config["smtp_password"]

            if config["use_ssl"]:
                smtp_cls = smtplib.SMTP_SSL
            else:
                smtp_cls = smtplib.SMTP

            with smtp_cls(server, port, timeout=timeout) as smtp:
                if not config["use_ssl"] and config["use_tls"]:
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            _SENT_EMAILS.append(record)
            return True, f"Email sent via SMTP to {target_email}"

        return False, f"Unknown email mode: {mode}"

    except Exception as exc:
        err_msg = str(exc)
        # Sanitize any password if inadvertently contained in error string
        pwd = config.get("smtp_password")
        if pwd and pwd in err_msg:
            err_msg = err_msg.replace(pwd, "******")
        return False, f"SMTP error: {err_msg}"


def compose_reconciliation_digest_email(
    admin_email: str,
    digest_date: str,
    summary_data: dict[str, Any],
    recipient_override: str | None = None,
) -> EmailMessage:
    config = get_email_config()
    msg = EmailMessage()
    msg["Subject"] = f"Stacks Library - Daily Circulation & Reconciliation Digest ({digest_date})"
    msg["From"] = config["from_email"]
    msg["To"] = recipient_override or config.get("test_recipient") or admin_email

    body_text = (
        f"Stacks Library Desk - Executive Daily Digest\n"
        f"Date: {digest_date}\n"
        f"--------------------------------------------------\n\n"
        f"Summary of Operations:\n"
        f"  - Books Issued Today: {summary_data.get('books_issued_today', 0)}\n"
        f"  - Books Returned Today: {summary_data.get('books_returned_today', 0)}\n"
        f"  - New Members Registered Today: {summary_data.get('new_members_today', 0)}\n"
        f"  - Active Loans in Circulation: {summary_data.get('total_active_loans', 0)}\n\n"
        f"Financial & Risk Health:\n"
        f"  - Overdue Loans Pending: {summary_data.get('active_overdue_count', 0)}\n"
        f"  - Fines Assessed Today: ₹{summary_data.get('fines_assessed_today', 0.0):.2f}\n"
        f"  - Total Outstanding Pending Fines: ₹{summary_data.get('total_pending_fines', 0.0):.2f}\n\n"
        f"This is an automated administrative report generated by Stacks RPA Subsystem.\n"
    )
    msg.set_content(body_text)
    return msg


def send_reconciliation_digest_email(
    admin_email: str,
    digest_date: str,
    summary_data: dict[str, Any],
) -> tuple[bool, str]:
    if not admin_email or "@" not in admin_email:
        return False, "Missing or invalid admin recipient email address"

    config = get_email_config()
    mode = config["mode"]
    test_recipient = config.get("test_recipient", "")
    target_email = test_recipient if test_recipient else admin_email

    if test_recipient and "@" not in test_recipient:
        return False, "Missing or invalid test recipient email address"

    try:
        msg = compose_reconciliation_digest_email(
            admin_email=admin_email,
            digest_date=digest_date,
            summary_data=summary_data,
            recipient_override=target_email,
        )

        record = {
            "to": target_email,
            "digest_date": digest_date,
            "summary": summary_data,
            "subject": msg["Subject"],
            "body": msg.get_content(),
            "mode": mode,
            "email_type": "reconciliation_digest",
        }

        if mode in ("mock", "test"):
            _SENT_EMAILS.append(record)
            return True, f"Digest email queued in mock outbox for {target_email}"

        if mode == "console":
            _SENT_EMAILS.append(record)
            print(f"[EMAIL SERVICE - CONSOLE] To: {target_email} | Subject: {msg['Subject']}")
            return True, f"Digest email logged to console for {target_email}"

        if mode == "smtp":
            server = config["smtp_server"]
            if not server:
                return False, "SMTP server is not configured (SMTP_SERVER empty)"

            port = config["smtp_port"]
            timeout = config["timeout"]
            username = config["smtp_username"]
            password = config["smtp_password"]

            smtp_cls = smtplib.SMTP_SSL if config["use_ssl"] else smtplib.SMTP

            with smtp_cls(server, port, timeout=timeout) as smtp:
                if not config["use_ssl"] and config["use_tls"]:
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            _SENT_EMAILS.append(record)
            return True, f"Digest email sent via SMTP to {target_email}"

        return False, f"Unknown email mode: {mode}"

    except Exception as exc:
        err_msg = str(exc)
        pwd = config.get("smtp_password")
        if pwd and pwd in err_msg:
            err_msg = err_msg.replace(pwd, "******")
        return False, f"SMTP error: {err_msg}"


def compose_activation_invitation_email(
    member_name: str,
    member_email: str,
    recipient_override: str | None = None,
) -> EmailMessage:
    config = get_email_config()
    msg = EmailMessage()
    msg["Subject"] = f"Action Required: Activate Your Stacks Library Student Portal Account"
    msg["From"] = config["from_email"]
    msg["To"] = recipient_override or config.get("test_recipient") or member_email

    body_text = (
        f"Dear {member_name},\n\n"
        f"Welcome to Stacks Library!\n\n"
        f"Your library membership has been registered by desk staff, but your online portal login has not yet been activated.\n\n"
        f"To activate your account and view your active loans, due dates, and catalogue items:\n"
        f"  1. Go to the Account Activation page (/activate)\n"
        f"  2. Enter your registered email: {member_email}\n"
        f"  3. Set your secure password (minimum 6 characters)\n\n"
        f"Once activated, you can sign in directly and manage your borrowing desk history.\n\n"
        f"Best regards,\n"
        f"Stacks Library Administration\n"
    )
    msg.set_content(body_text)
    return msg


def send_activation_invitation_email(
    member_name: str,
    member_email: str,
) -> tuple[bool, str]:
    if not member_email or "@" not in member_email:
        return False, "Missing or invalid recipient email address"

    config = get_email_config()
    mode = config["mode"]
    test_recipient = config.get("test_recipient", "")
    target_email = test_recipient if test_recipient else member_email

    if test_recipient and "@" not in test_recipient:
        return False, "Missing or invalid test recipient email address"

    try:
        msg = compose_activation_invitation_email(
            member_name=member_name,
            member_email=member_email,
            recipient_override=target_email,
        )

        record = {
            "to": target_email,
            "member_name": member_name,
            "member_email": member_email,
            "subject": msg["Subject"],
            "body": msg.get_content(),
            "mode": mode,
            "email_type": "activation_invitation",
        }

        if mode in ("mock", "test"):
            _SENT_EMAILS.append(record)
            return True, f"Invitation email queued in mock outbox for {target_email}"

        if mode == "console":
            _SENT_EMAILS.append(record)
            print(f"[EMAIL SERVICE - CONSOLE] To: {target_email} | Subject: {msg['Subject']}")
            return True, f"Invitation email logged to console for {target_email}"

        if mode == "smtp":
            server = config["smtp_server"]
            if not server:
                return False, "SMTP server is not configured (SMTP_SERVER empty)"

            port = config["smtp_port"]
            timeout = config["timeout"]
            username = config["smtp_username"]
            password = config["smtp_password"]

            smtp_cls = smtplib.SMTP_SSL if config["use_ssl"] else smtplib.SMTP

            with smtp_cls(server, port, timeout=timeout) as smtp:
                if not config["use_ssl"] and config["use_tls"]:
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            _SENT_EMAILS.append(record)
            return True, f"Invitation email sent via SMTP to {target_email}"

        return False, f"Unknown email mode: {mode}"

    except Exception as exc:
        err_msg = str(exc)
        pwd = config.get("smtp_password")
        if pwd and pwd in err_msg:
            err_msg = err_msg.replace(pwd, "******")
        return False, f"SMTP error: {err_msg}"
