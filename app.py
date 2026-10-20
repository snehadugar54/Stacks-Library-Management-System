from __future__ import annotations

import csv
import io
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

from email_service import (
    send_activation_invitation_email,
    send_courtesy_email,
    send_overdue_email,
    send_reconciliation_digest_email,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE = BASE_DIR / "library.db"
FINE_PER_DAY = 2.0

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is required. Set the SECRET_KEY environment variable before starting Flask."
    )

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY


@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    if request.path.startswith("/api/"):
        return jsonify({"error": exc.description}), exc.code
    return exc.get_response()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def today() -> date:
    return date.today()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_db().execute("SELECT id, name, email, role, member_id FROM users WHERE id=?", (user_id,)).fetchone()
    return row_to_dict(row) if row else None


def login_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return error("Please log in to continue.", 401)
            if roles and user["role"] not in roles:
                return error("Your role does not have permission for this action.", 403)
            g.current_user = user
            return view(*args, **kwargs)
        return wrapped
    return decorator


def log_activity(user_id: int, user_name: str, user_role: str, action: str, details: str = "") -> None:
    if user_role not in ("admin", "librarian"):
        return
    try:
        db = get_db()
        now_str = datetime.now().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO user_activity_log (user_id, user_name, user_role, action, details, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, user_name, user_role, action, details, now_str),
        )
        db.commit()
    except Exception as exc:
        app.logger.warning("Failed to log user activity: %s", exc)


def init_db() -> None:
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            total_copies INTEGER NOT NULL DEFAULT 1 CHECK(total_copies > 0),
            available_copies INTEGER NOT NULL DEFAULT 1 CHECK(available_copies >= 0)
        );
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            joined_on TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id),
            member_id INTEGER NOT NULL REFERENCES members(id),
            issued_on TEXT NOT NULL,
            due_on TEXT NOT NULL,
            returned_on TEXT,
            fine REAL NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'librarian', 'student')),
            member_id INTEGER UNIQUE REFERENCES members(id)
        );
        CREATE TABLE IF NOT EXISTS automation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            loan_id INTEGER NOT NULL REFERENCES loans(id),
            member_id INTEGER NOT NULL REFERENCES members(id),
            book_id INTEGER NOT NULL REFERENCES books(id),
            overdue_days INTEGER NOT NULL,
            fine REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL CHECK(status IN ('SUCCESS', 'FAILED')),
            message TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS user_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            user_name TEXT NOT NULL,
            user_role TEXT NOT NULL CHECK(user_role IN ('admin', 'librarian')),
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL
        );
        """
    )
    has_books = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    if not has_books:
        db.executemany(
            "INSERT INTO books (title, author, isbn, category, total_copies, available_copies) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Atomic Habits", "James Clear", "9780735211292", "Self Help", 4, 3),
                ("The Alchemist", "Paulo Coelho", "9780061122415", "Fiction", 3, 3),
                ("Clean Code", "Robert C. Martin", "9780132350884", "Technology", 2, 1),
                ("The Psychology of Money", "Morgan Housel", "9780857197689", "Finance", 3, 3),
            ],
        )
        db.executemany(
            "INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)",
            [
                ("Aarav Sharma", "aarav@example.com", "+91 98765 43210", today().isoformat()),
                ("Maya Patel", "maya@example.com", "+91 98765 43211", today().isoformat()),
                ("Ishaan Verma", "ishaan@example.com", "+91 98765 43212", today().isoformat()),
            ],
        )
        db.executemany(
            "INSERT INTO loans (book_id, member_id, issued_on, due_on) VALUES (?, ?, ?, ?)",
            [
                (1, 1, (today() - timedelta(days=5)).isoformat(), (today() + timedelta(days=9)).isoformat()),
                (3, 2, (today() - timedelta(days=21)).isoformat(), (today() - timedelta(days=7)).isoformat()),
            ],
        )
    has_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if not has_users:
        student_member = db.execute("SELECT id FROM members WHERE email=?", ("aarav@example.com",)).fetchone()[0]
        db.executemany(
            "INSERT INTO users (name, email, password_hash, role, member_id) VALUES (?, ?, ?, ?, ?)",
            [
                ("Aditi Rao", "admin@stacks.local", generate_password_hash("admin123"), "admin", None),
                ("Lina Thomas", "librarian@stacks.local", generate_password_hash("library123"), "librarian", None),
                ("Aarav Sharma", "student@stacks.local", generate_password_hash("student123"), "student", student_member),
            ],
        )
    db.commit()
    db.close()


def error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def validate_password(password: str) -> str | None:
    if len(password) < 6:
        return "Password must contain at least 6 characters."
    return None


@app.get("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    return render_template("index.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    message = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            if user["role"] in ("admin", "librarian"):
                log_activity(user["id"], user["name"], user["role"], "login", f"Signed in as {user['role']}")
            return redirect(url_for("index"))
        message = "Incorrect email or password. Please try again."
    return render_template("login.html", message=message)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("index"))
    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        message = validate_password(password)
        if not name or not email:
            message = "Name and email are required."
        if not message:
            db = get_db()
            member_exists = db.execute("SELECT id FROM members WHERE email=?", (email,)).fetchone()
            user_exists = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if member_exists or user_exists:
                message = "An account or member record already uses this email. Try account activation instead."
            else:
                try:
                    with db:
                        member_id = db.execute("INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)", (name, email, phone, today().isoformat())).lastrowid
                        user_id = db.execute("INSERT INTO users (name, email, password_hash, role, member_id) VALUES (?, ?, ?, 'student', ?)", (name, email, generate_password_hash(password), member_id)).lastrowid
                    session.clear()
                    session["user_id"] = user_id
                    return redirect(url_for("index"))
                except sqlite3.IntegrityError:
                    message = "Could not create the account. Please use a different email."
    return render_template("account_form.html", mode="register", message=message)


@app.route("/activate", methods=["GET", "POST"])
def activate_account():
    if current_user():
        return redirect(url_for("index"))
    message = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        message = validate_password(password)
        if not email:
            message = "Email is required."
        if not message:
            db = get_db()
            member = db.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
            existing_user = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing_user:
                message = "This member already has an account. Please sign in instead."
            elif not member:
                message = "No staff-created member record was found for this email. Register as a student instead."
            else:
                user_id = db.execute("INSERT INTO users (name, email, password_hash, role, member_id) VALUES (?, ?, ?, 'student', ?)", (member["name"], email, generate_password_hash(password), member["id"])).lastrowid
                db.commit()
                session.clear()
                session["user_id"] = user_id
                return redirect(url_for("index"))
    return render_template("account_form.html", mode="activate", message=message)


@app.post("/logout")
def logout():
    user = current_user()
    if user and user["role"] in ("admin", "librarian"):
        log_activity(user["id"], user["name"], user["role"], "logout", "Signed out")
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/dashboard")
@login_required()
def dashboard():
    db = get_db()
    user = g.current_user
    if user["role"] == "student":
        recent = db.execute(
            """SELECT l.id, b.title, m.name AS member, l.issued_on, l.due_on
               FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
               WHERE l.member_id=? AND l.returned_on IS NULL ORDER BY l.due_on""",
            (user["member_id"],),
        ).fetchall()
        overdue = sum(date.fromisoformat(loan["due_on"]) < today() for loan in recent)
        fines = db.execute("SELECT COALESCE(SUM(fine), 0) FROM loans WHERE member_id=? AND paid=0", (user["member_id"],)).fetchone()[0]
        return jsonify({"stats": {"titles": db.execute("SELECT COUNT(*) FROM books").fetchone()[0], "available": db.execute("SELECT COALESCE(SUM(available_copies), 0) FROM books").fetchone()[0], "active_loans": len(recent), "overdue": overdue, "pending_fines": fines}, "recent": [row_to_dict(row) for row in recent]})
    active_loans = db.execute("SELECT COUNT(*) FROM loans WHERE returned_on IS NULL").fetchone()[0]
    overdue = db.execute("SELECT COUNT(*) FROM loans WHERE returned_on IS NULL AND due_on < ?", (today().isoformat(),)).fetchone()[0]
    stats = {
        "titles": db.execute("SELECT COUNT(*) FROM books").fetchone()[0],
        "available": db.execute("SELECT COALESCE(SUM(available_copies), 0) FROM books").fetchone()[0],
        "members": db.execute("SELECT COUNT(*) FROM members").fetchone()[0],
        "active_loans": active_loans,
        "overdue": overdue,
        "pending_fines": db.execute("SELECT COALESCE(SUM(fine), 0) FROM loans WHERE paid = 0").fetchone()[0],
    }
    recent = db.execute(
        """SELECT l.id, b.title, m.name AS member, l.issued_on, l.due_on
           FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
           WHERE l.returned_on IS NULL ORDER BY l.issued_on DESC LIMIT 5"""
    ).fetchall()
    return jsonify({"stats": stats, "recent": [row_to_dict(row) for row in recent]})


@app.get("/api/books")
@login_required()
def list_books():
    query = request.args.get("q", "").strip()
    db = get_db()
    if query:
        value = f"%{query}%"
        rows = db.execute("SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? ORDER BY title", (value, value, value)).fetchall()
    else:
        rows = db.execute("SELECT * FROM books ORDER BY title").fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/books")
@login_required("admin", "librarian")
def create_book():
    data = request.get_json() or {}
    required = ["title", "author", "isbn", "category", "total_copies"]
    if any(not str(data.get(field, "")).strip() for field in required):
        return error("Please complete all book fields.")
    try:
        copies = int(data["total_copies"])
        if copies < 1:
            raise ValueError
        db = get_db()
        db.execute("INSERT INTO books (title, author, isbn, category, total_copies, available_copies) VALUES (?, ?, ?, ?, ?, ?)", (data["title"].strip(), data["author"].strip(), data["isbn"].strip(), data["category"].strip(), copies, copies))
        db.commit()
        user = g.current_user
        log_activity(user["id"], user["name"], user["role"], "add_book", f"Added '{data['title'].strip()}' ({copies} copies, ISBN: {data['isbn'].strip()})")
    except (ValueError, sqlite3.IntegrityError):
        return error("Use a unique ISBN and at least one copy.")
    return jsonify({"message": "Book added to the catalogue."}), 201


@app.get("/api/members")
@login_required("admin", "librarian")
def list_members():
    rows = get_db().execute(
        """SELECT m.*, CASE WHEN u.id IS NULL THEN 0 ELSE 1 END AS account_active
           FROM members m LEFT JOIN users u ON u.member_id=m.id ORDER BY m.name"""
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/members")
@login_required("admin", "librarian")
def create_member():
    data = request.get_json() or {}
    if not data.get("name", "").strip() or not data.get("email", "").strip():
        return error("Member name and email are required.")
    try:
        db = get_db()
        db.execute("INSERT INTO members (name, email, phone, joined_on) VALUES (?, ?, ?, ?)", (data["name"].strip(), data["email"].strip(), data.get("phone", "").strip(), today().isoformat()))
        db.commit()
        user = g.current_user
        log_activity(user["id"], user["name"], user["role"], "add_member", f"Registered member '{data['name'].strip()}' ({data['email'].strip()})")
    except sqlite3.IntegrityError:
        return error("That email already belongs to a member.")
    return jsonify({"message": "Member registered."}), 201


@app.delete("/api/members/<int:member_id>")
@login_required("admin", "librarian")
def delete_member(member_id: int):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    member = db.execute(
        "SELECT id, name, email FROM members WHERE id=?", (member_id,)
    ).fetchone()
    if not member:
        db.rollback()
        return error("Member not found.", 404)

    active_loan = db.execute(
        "SELECT 1 FROM loans WHERE member_id=? AND returned_on IS NULL LIMIT 1",
        (member_id,),
    ).fetchone()
    if active_loan:
        db.rollback()
        return error("This member has active loans and cannot be deleted.", 409)

    loan_history = db.execute(
        "SELECT 1 FROM loans WHERE member_id=? LIMIT 1", (member_id,)
    ).fetchone()
    if loan_history:
        db.rollback()
        return error("This member has loan history and cannot be deleted.", 409)

    linked_account = db.execute(
        "SELECT 1 FROM users WHERE member_id=? LIMIT 1", (member_id,)
    ).fetchone()
    if linked_account:
        db.rollback()
        return error(
            "This member has a linked login account and cannot be deleted.", 409
        )

    automation_history = db.execute(
        "SELECT 1 FROM automation_logs WHERE member_id=? LIMIT 1", (member_id,)
    ).fetchone()
    if automation_history:
        db.rollback()
        return error("This member has automation history and cannot be deleted.", 409)

    try:
        deleted = db.execute("DELETE FROM members WHERE id=?", (member_id,)).rowcount
        if not deleted:
            db.rollback()
            return error("Member not found.", 404)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return error("This member has related records and cannot be deleted.", 409)

    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "delete_member",
        f"Deleted member #{member['id']} '{member['name']}' ({member['email']})",
    )
    return jsonify({"message": "Member deleted."})


@app.get("/api/loans")
@login_required()
def list_loans():
    user = g.current_user
    query = (
        """SELECT l.*, b.title, m.name AS member, m.email
           FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
           WHERE l.member_id=? ORDER BY l.returned_on IS NOT NULL, l.due_on"""
        if user["role"] == "student" else
        """SELECT l.*, b.title, m.name AS member, m.email
           FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
           ORDER BY l.returned_on IS NOT NULL, l.due_on"""
    )
    rows = get_db().execute(query, (user["member_id"],) if user["role"] == "student" else ()).fetchall()
    result = []
    for row in rows:
        item = row_to_dict(row)
        item["overdue_days"] = max(0, (today() - date.fromisoformat(item["due_on"])).days) if not item["returned_on"] else 0
        result.append(item)
    return jsonify(result)


@app.post("/api/loans")
@login_required("admin", "librarian")
def issue_book():
    data = request.get_json() or {}
    try:
        book_id, member_id = int(data["book_id"]), int(data["member_id"])
    except (KeyError, ValueError, TypeError):
        return error("Select a book and member.")
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    member = db.execute("SELECT id, name FROM members WHERE id=?", (member_id,)).fetchone()
    if not book or not member:
        return error("Selected book or member is not available.")
    if book["available_copies"] < 1:
        return error("No copies of this book are available.")
    issued = today()
    due = issued + timedelta(days=1)
    db.execute("INSERT INTO loans (book_id, member_id, issued_on, due_on) VALUES (?, ?, ?, ?)", (book_id, member_id, issued.isoformat(), due.isoformat()))
    db.execute("UPDATE books SET available_copies=available_copies-1 WHERE id=?", (book_id,))
    db.commit()
    user = g.current_user
    log_activity(user["id"], user["name"], user["role"], "issue_book", f"Issued '{book['title']}' to {member['name']}")
    return jsonify({"message": f"Book issued. Due on {due.strftime('%d %b %Y')}."}), 201


@app.post("/api/loans/<int:loan_id>/return")
@login_required("admin", "librarian")
def return_book(loan_id: int):
    db = get_db()
    loan = db.execute(
        """SELECT l.*, b.title AS book_title, m.name AS member_name
           FROM loans l
           JOIN books b ON b.id=l.book_id
           JOIN members m ON m.id=l.member_id
           WHERE l.id=?""",
        (loan_id,)
    ).fetchone()
    if not loan or loan["returned_on"]:
        return error("This loan has already been returned.")
    overdue_days = max(0, (today() - date.fromisoformat(loan["due_on"])).days)
    fine = round(overdue_days * FINE_PER_DAY, 2)
    db.execute("UPDATE loans SET returned_on=?, fine=? WHERE id=?", (today().isoformat(), fine, loan_id))
    db.execute("UPDATE books SET available_copies=available_copies+1 WHERE id=?", (loan["book_id"],))
    db.commit()
    detail = f" Fine assessed: ₹{fine:.2f}." if fine else " No fine due."
    user = g.current_user
    log_activity(user["id"], user["name"], user["role"], "return_book", f"Returned '{loan['book_title']}' for {loan['member_name']}.{detail}")
    return jsonify({"message": "Book returned." + detail})


@app.post("/api/loans/<int:loan_id>/pay")
@login_required("admin", "librarian")
def pay_fine(loan_id: int):
    db = get_db()
    loan = db.execute(
        """SELECT l.*, b.title AS book_title, m.name AS member_name
           FROM loans l
           JOIN books b ON b.id=l.book_id
           JOIN members m ON m.id=l.member_id
           WHERE l.id=?""",
        (loan_id,)
    ).fetchone()
    updated = db.execute("UPDATE loans SET paid=1 WHERE id=? AND fine > 0", (loan_id,)).rowcount
    db.commit()
    if not updated:
        return error("There is no outstanding fine for this loan.")
    user = g.current_user
    fine_str = f"₹{loan['fine']:.2f}" if loan and loan["fine"] else ""
    log_activity(user["id"], user["name"], user["role"], "pay_fine", f"Marked fine {fine_str} paid for loan #{loan_id} ({loan['member_name'] if loan else ''})")
    return jsonify({"message": "Fine marked as paid."})


@app.post("/api/automation/overdue")
@login_required("admin")
def run_overdue_check():
    db = get_db()
    run_at = datetime.now().isoformat(timespec="seconds")
    current_date = today()
    rows = db.execute(
        """SELECT l.id AS loan_id, l.due_on,
                  m.id AS member_id, m.name AS member_name, m.email AS member_email,
                  b.id AS book_id, b.title AS book_title
           FROM loans l
           JOIN members m ON m.id = l.member_id
           JOIN books b ON b.id = l.book_id
           WHERE l.returned_on IS NULL AND l.due_on < ?""",
        (current_date.isoformat(),),
    ).fetchall()
    results = []
    for row in rows:
        try:
            overdue_days = max(0, (current_date - date.fromisoformat(row["due_on"])).days)
            projected_fine = round(overdue_days * FINE_PER_DAY, 2)

            email_sent, email_detail = send_overdue_email(
                member_name=row["member_name"],
                member_email=row["member_email"],
                book_title=row["book_title"],
                due_on=row["due_on"],
                overdue_days=overdue_days,
                fine=projected_fine,
            )
            email_status_str = "SENT" if email_sent else "FAILED"
            email_suffix = f" [Email: {email_status_str}]"

            message = (
                f"Overdue reminder processed for {row['member_name']}"
                f" \u2014 {row['book_title']}"
                f" ({overdue_days} day{'s' if overdue_days != 1 else ''} overdue,"
                f" projected fine \u20b9{projected_fine:.2f})."
                f"{email_suffix}"
            )
            db.execute(
                """INSERT INTO automation_logs
                   (run_at, loan_id, member_id, book_id, overdue_days, fine, status, message)
                   VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', ?)""",
                (run_at, row["loan_id"], row["member_id"], row["book_id"],
                 overdue_days, projected_fine, message),
            )
            results.append({
                "loan_id": row["loan_id"],
                "member_id": row["member_id"],
                "member_name": row["member_name"],
                "member_email": row["member_email"],
                "book_id": row["book_id"],
                "book_title": row["book_title"],
                "due_on": row["due_on"],
                "overdue_days": overdue_days,
                "projected_fine": projected_fine,
                "status": "SUCCESS",
                "message": message,
                "email_status": email_status_str,
                "email_message": email_detail,
            })
        except Exception as exc:
            error_message = f"Failed to process loan {row['loan_id']}: {exc}"
            db.execute(
                """INSERT INTO automation_logs
                   (run_at, loan_id, member_id, book_id, overdue_days, fine, status, message)
                   VALUES (?, ?, ?, ?, 0, 0, 'FAILED', ?)""",
                (run_at, row["loan_id"], row["member_id"], row["book_id"], error_message),
            )
            results.append({
                "loan_id": row["loan_id"],
                "status": "FAILED",
                "message": error_message,
            })
    db.commit()
    processed = len(results)
    emails_sent = sum(1 for r in results if r.get("email_status") == "SENT")
    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "run_overdue_check",
        f"Ran overdue check: {processed} loan{'s' if processed != 1 else ''} processed ({emails_sent} email{'s' if emails_sent != 1 else ''} sent)",
    )
    return jsonify({
        "message": f"Overdue reminder processing completed. {processed} loan{'s' if processed != 1 else ''} processed.",
        "processed": processed,
        "results": results,
    })


@app.post("/api/automation/courtesy")
@login_required("admin")
def run_courtesy_check():
    db = get_db()
    run_at = datetime.now().isoformat(timespec="seconds")
    current_date = today()
    target_date = current_date + timedelta(days=1)
    rows = db.execute(
        """SELECT l.id AS loan_id, l.due_on,
                  m.id AS member_id, m.name AS member_name, m.email AS member_email,
                  b.id AS book_id, b.title AS book_title
           FROM loans l
           JOIN members m ON m.id = l.member_id
           JOIN books b ON b.id = l.book_id
           WHERE l.returned_on IS NULL AND l.due_on >= ? AND l.due_on <= ?""",
        (current_date.isoformat(), target_date.isoformat()),
    ).fetchall()
    results = []
    for row in rows:
        try:
            days_until_due = max(0, (date.fromisoformat(row["due_on"]) - current_date).days)
            email_sent, email_detail = send_courtesy_email(
                member_name=row["member_name"],
                member_email=row["member_email"],
                book_title=row["book_title"],
                due_on=row["due_on"],
                days_until_due=days_until_due,
            )
            email_status_str = "SENT" if email_sent else "FAILED"
            email_suffix = f" [Email: {email_status_str}]"
            due_phrase = "due today" if days_until_due == 0 else "due tomorrow" if days_until_due == 1 else f"due in {days_until_due} days"

            message = (
                f"Courtesy reminder processed for {row['member_name']}"
                f" \u2014 {row['book_title']}"
                f" ({due_phrase}: {row['due_on']})."
                f"{email_suffix}"
            )
            db.execute(
                """INSERT INTO automation_logs
                   (run_at, loan_id, member_id, book_id, overdue_days, fine, status, message)
                   VALUES (?, ?, ?, ?, 0, 0, 'SUCCESS', ?)""",
                (run_at, row["loan_id"], row["member_id"], row["book_id"], message),
            )
            results.append({
                "loan_id": row["loan_id"],
                "member_id": row["member_id"],
                "member_name": row["member_name"],
                "member_email": row["member_email"],
                "book_id": row["book_id"],
                "book_title": row["book_title"],
                "due_on": row["due_on"],
                "days_until_due": days_until_due,
                "status": "SUCCESS",
                "message": message,
                "email_status": email_status_str,
                "email_message": email_detail,
            })
        except Exception as exc:
            error_message = f"Failed to process loan {row['loan_id']}: {exc}"
            db.execute(
                """INSERT INTO automation_logs
                   (run_at, loan_id, member_id, book_id, overdue_days, fine, status, message)
                   VALUES (?, ?, ?, ?, 0, 0, 'FAILED', ?)""",
                (run_at, row["loan_id"], row["member_id"], row["book_id"], error_message),
            )
            results.append({
                "loan_id": row["loan_id"],
                "status": "FAILED",
                "message": error_message,
            })
    db.commit()
    processed = len(results)
    emails_sent = sum(1 for r in results if r.get("email_status") == "SENT")
    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "run_courtesy_check",
        f"Ran courtesy reminder check: {processed} loan{'s' if processed != 1 else ''} processed ({emails_sent} email{'s' if emails_sent != 1 else ''} sent)",
    )
    return jsonify({
        "message": f"Courtesy reminder processing completed. {processed} loan{'s' if processed != 1 else ''} processed.",
        "processed": processed,
        "results": results,
    })


def find_robot_command() -> list[str]:
    # 1. Look in active python's bin/Scripts directory
    py_dir = Path(sys.executable).parent
    for name in ("robot", "robot.exe"):
        cand = py_dir / name
        if cand.exists():
            return [str(cand)]

    # 2. Look in local project virtual environments
    for cand in [
        BASE_DIR / ".venv" / "bin" / "robot",
        BASE_DIR / ".venv" / "Scripts" / "robot.exe",
        BASE_DIR / ".venv-windows" / "Scripts" / "robot.exe",
        BASE_DIR / ".venv-windows" / "bin" / "robot",
    ]:
        if cand.exists():
            return [str(cand)]

    # 3. Check system PATH
    which_robot = shutil.which("robot")
    if which_robot:
        return [which_robot]

    # 4. Universal Python module invocation
    return [sys.executable, "-m", "robot"]


@app.post("/api/automation/overdue/run-bot")
@login_required("admin")
def run_overdue_reminder_bot():
    bot_env = os.environ.copy()
    if not bot_env.get("LIBRARY_ADMIN_EMAIL"):
        bot_env["LIBRARY_ADMIN_EMAIL"] = "admin@stacks.local"
    if not bot_env.get("LIBRARY_ADMIN_PASSWORD"):
        bot_env["LIBRARY_ADMIN_PASSWORD"] = "admin123"

    bot_file = BASE_DIR / "rpa" / "bots" / "overdue_reminder_bot.robot"
    results_directory = BASE_DIR / "rpa" / "results"
    results_directory.mkdir(parents=True, exist_ok=True)
    if not bot_file.exists():
        return error("The overdue reminder bot script is unavailable.", 503)

    robot_cmd = find_robot_command()

    try:
        completed = subprocess.run(
            robot_cmd + ["--outputdir", str(results_directory), str(bot_file)],
            cwd=BASE_DIR,
            env=bot_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return error("The overdue reminder bot timed out.", 504)
    except OSError as exc:
        return error(f"The overdue reminder bot could not be started: {exc}", 500)

    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        return jsonify({
            "error": "The overdue reminder bot failed.",
            "robot_output": output[-4000:],
            "returncode": completed.returncode,
        }), 502
    user = g.current_user
    log_activity(user["id"], user["name"], user["role"], "run_overdue_bot", f"Ran overdue reminder bot (exit code {completed.returncode})")
    return jsonify({
        "message": "Overdue reminder bot completed successfully. Automation logs are ready to view.",
        "robot_output": output[-4000:],
        "returncode": completed.returncode,
    })


@app.get("/api/automation/logs")
@login_required("admin")
def automation_logs():
    rows = get_db().execute(
        """SELECT al.id, al.run_at, al.loan_id, al.overdue_days, al.fine,
                  al.status, al.message,
                  m.name AS member_name, m.email AS member_email,
                  b.title AS book_title, l.due_on
           FROM automation_logs al
           JOIN members m ON m.id = al.member_id
           JOIN books b ON b.id = al.book_id
           JOIN loans l ON l.id = al.loan_id
           ORDER BY al.id DESC LIMIT 200"""
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/activity-logs")
@app.get("/api/activity-log")
@login_required("admin", "librarian")
def activity_logs():
    db = get_db()
    rows = db.execute(
        """SELECT id, user_id, user_name, user_role, action, details, timestamp
           FROM user_activity_log
           ORDER BY id DESC LIMIT 200"""
    ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/reports/loans.csv")
@login_required("admin")
def loan_report():
    rows = get_db().execute(
        """SELECT b.title, m.name AS member, l.issued_on, l.due_on, l.returned_on, l.fine, l.paid
           FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id ORDER BY l.id DESC"""
    ).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Book", "Member", "Issued", "Due", "Returned", "Fine", "Paid"])
    writer.writerows([[row[key] for key in row.keys()] for row in rows])
    return Response(buffer.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=library-loans-report.csv"})


@app.post("/api/automation/inventory-audit")
@login_required("admin", "librarian")
def run_inventory_audit():
    db = get_db()
    books = db.execute("SELECT * FROM books ORDER BY title").fetchall()
    active_loans_map = {
        row["book_id"]: row["cnt"]
        for row in db.execute("SELECT book_id, COUNT(*) AS cnt FROM loans WHERE returned_on IS NULL GROUP BY book_id").fetchall()
    }
    all_loans_map = {
        row["book_id"]: row["cnt"]
        for row in db.execute("SELECT book_id, COUNT(*) AS cnt FROM loans GROUP BY book_id").fetchall()
    }

    audited_books = []
    depleted_count = 0
    low_stock_count = 0
    healthy_count = 0

    for b in books:
        book_id = b["id"]
        total = b["total_copies"]
        available = b["available_copies"]
        active_loans = active_loans_map.get(book_id, 0)
        total_loans = all_loans_map.get(book_id, 0)
        utilization = round(((total - available) / total) * 100, 1) if total > 0 else 0.0

        if available == 0:
            status = "CRITICAL_DEPLETED"
            depleted_count += 1
            recommended_reorder = max(2, active_loans)
        elif available == 1 and total > 1:
            status = "LOW_STOCK"
            low_stock_count += 1
            recommended_reorder = 1
        else:
            status = "HEALTHY"
            healthy_count += 1
            recommended_reorder = 0

        audited_books.append({
            "book_id": book_id,
            "title": b["title"],
            "author": b["author"],
            "isbn": b["isbn"],
            "category": b["category"],
            "total_copies": total,
            "available_copies": available,
            "active_loans": active_loans,
            "total_historical_loans": total_loans,
            "utilization_pct": utilization,
            "stock_status": status,
            "recommended_reorder": recommended_reorder,
        })

    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "run_inventory_audit",
        f"Ran inventory audit: {len(audited_books)} titles checked ({depleted_count} depleted, {low_stock_count} low stock)",
    )

    return jsonify({
        "message": f"Inventory audit completed. {len(audited_books)} titles audited.",
        "total_titles": len(audited_books),
        "depleted_titles": depleted_count,
        "low_stock_titles": low_stock_count,
        "healthy_titles": healthy_count,
        "results": audited_books,
    })


@app.get("/api/reports/inventory-audit.csv")
@login_required("admin", "librarian")
def inventory_audit_report():
    db = get_db()
    books = db.execute("SELECT * FROM books ORDER BY title").fetchall()
    active_loans_map = {
        row["book_id"]: row["cnt"]
        for row in db.execute("SELECT book_id, COUNT(*) AS cnt FROM loans WHERE returned_on IS NULL GROUP BY book_id").fetchall()
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Book ID", "Title", "Author", "ISBN", "Category",
        "Total Copies", "Available Copies", "Active Loans",
        "Utilization %", "Stock Status", "Recommended Reorder"
    ])

    for b in books:
        book_id = b["id"]
        total = b["total_copies"]
        available = b["available_copies"]
        active = active_loans_map.get(book_id, 0)
        utilization = round(((total - available) / total) * 100, 1) if total > 0 else 0.0

        if available == 0:
            status = "CRITICAL_DEPLETED"
            reorder = max(2, active)
        elif available == 1 and total > 1:
            status = "LOW_STOCK"
            reorder = 1
        else:
            status = "HEALTHY"
            reorder = 0

        writer.writerow([
            book_id, b["title"], b["author"], b["isbn"], b["category"],
            total, available, active, f"{utilization:.1f}%", status, reorder
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=library-inventory-audit.csv"},
    )


@app.post("/api/automation/daily-reconciliation")
@login_required("admin")
def run_daily_reconciliation():
    db = get_db()
    current_date = today().isoformat()

    # Books issued today
    issued_today = db.execute(
        "SELECT COUNT(*) FROM loans WHERE issued_on = ?", (current_date,)
    ).fetchone()[0]

    # Books returned today
    returned_today = db.execute(
        "SELECT COUNT(*) FROM loans WHERE returned_on = ?", (current_date,)
    ).fetchone()[0]

    # Fines assessed on loans returned today
    fines_assessed_today = db.execute(
        "SELECT COALESCE(SUM(fine), 0) FROM loans WHERE returned_on = ?", (current_date,)
    ).fetchone()[0]

    # Total pending / unpaid fines
    pending_fines = db.execute(
        "SELECT COALESCE(SUM(fine), 0) FROM loans WHERE paid = 0"
    ).fetchone()[0]

    # Active overdue count
    active_overdue = db.execute(
        "SELECT COUNT(*) FROM loans WHERE returned_on IS NULL AND due_on < ?", (current_date,)
    ).fetchone()[0]

    # Total active loans
    active_loans = db.execute(
        "SELECT COUNT(*) FROM loans WHERE returned_on IS NULL"
    ).fetchone()[0]

    # New members registered today
    new_members_today = db.execute(
        "SELECT COUNT(*) FROM members WHERE joined_on = ?", (current_date,)
    ).fetchone()[0]

    summary_data = {
        "books_issued_today": issued_today,
        "books_returned_today": returned_today,
        "fines_assessed_today": round(float(fines_assessed_today), 2),
        "total_pending_fines": round(float(pending_fines), 2),
        "active_overdue_count": active_overdue,
        "total_active_loans": active_loans,
        "new_members_today": new_members_today,
    }

    admin_email = os.getenv("LIBRARY_ADMIN_EMAIL", "admin@stacks.local").strip() or "admin@stacks.local"
    email_sent, email_detail = send_reconciliation_digest_email(
        admin_email=admin_email,
        digest_date=current_date,
        summary_data=summary_data,
    )
    email_status_str = "SENT" if email_sent else "FAILED"

    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "run_daily_reconciliation",
        f"Reconciled daily activity: {issued_today} issued, {returned_today} returned, {active_overdue} overdue, ₹{fines_assessed_today:.2f} fines assessed. [Email: {email_status_str}]",
    )

    return jsonify({
        "message": f"Daily reconciliation completed and digest dispatched to {admin_email}.",
        "date": current_date,
        "summary": summary_data,
        "email_status": email_status_str,
        "email_message": email_detail,
        "recipient": admin_email,
    })


@app.post("/api/automation/member-invitations")
@login_required("admin", "librarian")
def run_member_invitations():
    db = get_db()
    unactivated_members = db.execute(
        """SELECT m.id, m.name, m.email, m.phone, m.joined_on
           FROM members m
           LEFT JOIN users u ON u.member_id = m.id
           WHERE u.id IS NULL
           ORDER BY m.name"""
    ).fetchall()

    results = []
    for member in unactivated_members:
        try:
            email_sent, email_detail = send_activation_invitation_email(
                member_name=member["name"],
                member_email=member["email"],
            )
            email_status_str = "SENT" if email_sent else "FAILED"
            results.append({
                "member_id": member["id"],
                "member_name": member["name"],
                "member_email": member["email"],
                "status": "SUCCESS",
                "email_status": email_status_str,
                "message": f"Invitation sent to {member['name']} ({member['email']}). [Email: {email_status_str}]",
                "email_detail": email_detail,
            })
        except Exception as exc:
            results.append({
                "member_id": member["id"],
                "member_name": member["name"],
                "member_email": member["email"],
                "status": "FAILED",
                "email_status": "FAILED",
                "message": f"Failed to invite {member['name']}: {exc}",
            })

    processed = len(results)
    emails_sent = sum(1 for r in results if r.get("email_status") == "SENT")
    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "run_member_invitations",
        f"Ran member invitation bot: {processed} unactivated member{'s' if processed != 1 else ''} processed ({emails_sent} email{'s' if emails_sent != 1 else ''} sent)",
    )

    return jsonify({
        "message": f"Member invitation processing completed. {processed} unactivated member{'s' if processed != 1 else ''} processed.",
        "processed": processed,
        "emails_sent": emails_sent,
        "results": results,
    })


@app.get("/api/templates/books-template.csv")
@login_required("admin", "librarian")
def download_books_template():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Title", "Author", "ISBN", "Category", "Copies"])
    writer.writerow(["Introduction to Algorithms", "Thomas H. Cormen", "9780262033848", "Technology", "3"])
    writer.writerow(["Design Patterns", "Erich Gamma", "9780201633610", "Technology", "2"])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=library-books-template.csv"},
    )


@app.post("/api/automation/books/import-csv")
@login_required("admin", "librarian")
def bulk_import_books():
    csv_content = ""
    if "file" in request.files:
        uploaded = request.files["file"]
        if uploaded.filename:
            csv_content = uploaded.read().decode("utf-8", errors="replace")
    elif request.is_json and "csv_data" in request.json:
        csv_content = request.json["csv_data"]
    else:
        raw_data = request.get_data(as_text=True)
        if raw_data:
            csv_content = raw_data

    if not csv_content.strip():
        return error("No CSV content provided for ingestion.", 400)

    try:
        reader = csv.DictReader(io.StringIO(csv_content))
    except Exception as exc:
        return error(f"Invalid CSV format: {exc}", 400)

    if not reader.fieldnames:
        return error("CSV file appears to be empty or missing header row.", 400)

    header_map = {fn.strip().lower(): fn for fn in reader.fieldnames if fn}
    title_col = header_map.get("title")
    author_col = header_map.get("author")
    isbn_col = header_map.get("isbn")
    cat_col = header_map.get("category")
    copies_col = header_map.get("copies") or header_map.get("total_copies") or header_map.get("total copies")

    if not all([title_col, author_col, isbn_col, cat_col]):
        return error("CSV header must include at least: Title, Author, ISBN, Category, Copies", 400)

    db = get_db()
    inserted_titles = []
    updated_titles = []
    skipped_rows = []

    for row_idx, row in enumerate(reader, start=2):
        title = (row.get(title_col) or "").strip()
        author = (row.get(author_col) or "").strip()
        isbn = (row.get(isbn_col) or "").strip()
        category = (row.get(cat_col) or "").strip()
        copies_raw = (row.get(copies_col) or "1").strip() if copies_col else "1"

        if not title or not author or not isbn or not category:
            skipped_rows.append({
                "row": row_idx,
                "title": title or "(empty)",
                "reason": "Missing required fields (title, author, isbn, or category)."
            })
            continue

        try:
            copies = int(copies_raw)
            if copies < 1:
                raise ValueError
        except ValueError:
            skipped_rows.append({
                "row": row_idx,
                "title": title,
                "reason": f"Invalid copies count: '{copies_raw}'. Must be integer >= 1."
            })
            continue

        existing = db.execute("SELECT id, title, total_copies, available_copies FROM books WHERE isbn = ?", (isbn,)).fetchone()
        if existing:
            db.execute(
                "UPDATE books SET total_copies = total_copies + ?, available_copies = available_copies + ? WHERE id = ?",
                (copies, copies, existing["id"])
            )
            updated_titles.append({
                "row": row_idx,
                "title": existing["title"],
                "isbn": isbn,
                "copies_added": copies,
                "new_total": existing["total_copies"] + copies,
            })
        else:
            db.execute(
                "INSERT INTO books (title, author, isbn, category, total_copies, available_copies) VALUES (?, ?, ?, ?, ?, ?)",
                (title, author, isbn, category, copies, copies)
            )
            inserted_titles.append({
                "row": row_idx,
                "title": title,
                "author": author,
                "isbn": isbn,
                "category": category,
                "copies": copies,
            })

    db.commit()

    user = g.current_user
    log_activity(
        user["id"],
        user["name"],
        user["role"],
        "bulk_book_import",
        f"Ingested catalogue CSV: {len(inserted_titles)} new titles added, {len(updated_titles)} stock updated, {len(skipped_rows)} skipped",
    )

    return jsonify({
        "message": f"Catalogue ingestion completed: {len(inserted_titles)} added, {len(updated_titles)} updated, {len(skipped_rows)} skipped.",
        "total_processed": len(inserted_titles) + len(updated_titles) + len(skipped_rows),
        "inserted_count": len(inserted_titles),
        "updated_count": len(updated_titles),
        "skipped_count": len(skipped_rows),
        "inserted": inserted_titles,
        "updated": updated_titles,
        "skipped": skipped_rows,
    })


if __name__ == "__main__":
    init_db()
    debug_enabled = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug_enabled, use_reloader=False)
