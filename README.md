# Stacks Library Management System

A web-based Library Management System built with **Python, Flask, SQLite, HTML, CSS, and JavaScript**, enhanced with **Robot Framework and Robotic Process Automation (RPA)** to automate routine library operations.

The system supports catalogue management, member registration, book issue and return workflows, overdue tracking, fine calculation, role-based access, email notifications, inventory auditing, and operational reporting.

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [User Roles](#user-roles)
- [Project Setup](#project-setup)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [Registration and Account Activation](#registration-and-account-activation)
- [RPA Automations](#rpa-automations)
- [Email Configuration](#email-configuration)
- [Running Automated Tests](#running-automated-tests)
- [Windows Task Scheduler](#windows-task-scheduler)
- [Security and Data Protection](#security-and-data-protection)
- [Troubleshooting](#troubleshooting)

## Project Overview

Stacks is designed to simplify everyday library operations through a centralized web application and a set of automated workflows.

The application combines standard library management functions with RPA-based processes that reduce repetitive manual work, support timely borrower notifications, monitor inventory, and generate administrative reports.

The project includes both interactive workflows performed through the web interface and automations that can be triggered manually or scheduled on Windows.

## Features

### Library Management

- Book catalogue management and bulk CSV catalogue import.
- Member registration and member record management.
- Protected member deletion that blocks deletion when related records or history must be preserved.
- Book issue and return workflows.
- Automatic 14-day loan due dates.
- Overdue loan detection and fine calculation at ₹2 per overdue day.
- Dashboard metrics and lending reports in CSV format.

### Authentication and Authorization

- Login and logout.
- Role-based access for Admin, Librarian, and Student.
- Student self-registration.
- Account activation for staff-created members.
- Access restrictions for administrative operations.

### RPA and Reporting

- Automated overdue reminders.
- Courtesy due-date notifications.
- Inventory health and restocking advisories.
- Daily managerial reconciliation digest.
- Invitations for unactivated member accounts.
- Bulk catalogue ingestion from CSV files.
- Automation activity logging and email delivery status tracking.
- Robot Framework execution reports.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic and automation integration |
| Flask | Web application and REST API |
| SQLite | Local relational database |
| HTML, CSS, JavaScript | User interface |
| Robot Framework | Automated overdue reminder workflow |
| SMTP | Email delivery |
| Windows Task Scheduler | Scheduled automation |
| CSV | Catalogue import and operational reports |

## User Roles

| Role | Purpose |
|---|---|
| Admin | Administrative operations, automation execution, reporting, and management |
| Librarian | Day-to-day library operations, subject to assigned permissions |
| Student | Student account access and permitted self-service functionality |

Access to individual actions is enforced by the application. Available operations depend on the user's role and the relevant authorization rules.

## Project Setup

### Prerequisites

Install the following before running the application:

- Windows 10 or later.
- Python 3.13, or another version compatible with the project's dependencies.
- Git, if cloning the repository.
- A web browser.
- A Gmail account and Gmail App Password if testing email delivery through Gmail SMTP.

### 1. Clone the repository

Clone your GitHub repository and navigate to the project directory:

```powershell
git clone <YOUR_GITHUB_REPOSITORY_URL>
Set-Location '<YOUR_PROJECT_DIRECTORY>'
```

Replace the placeholders with your actual repository URL and local project path.

### 2. Create a virtual environment

```powershell
py -3.13 -m venv .venv-windows
```

If your installed Python version differs, use a compatible installed version.

### 3. Install dependencies

```powershell
.\.venv-windows\Scripts\python.exe -m pip install --upgrade pip
.\.venv-windows\Scripts\python.exe -m pip install -r requirements.txt
```

The dependency file should include all packages required by the application, including `python-dotenv` if it is used to load `.env`.

### 4. Configure environment variables

Create a local `.env` file in the project root. See the next section for the configuration template.

**Do not upload your real `.env` file to GitHub.**

### 5. Start the application

```powershell
.\.venv-windows\Scripts\python.exe app.py
```

Open the application in your browser:

http://127.0.0.1:5000

Keep the Flask terminal running while using the application.

## Environment Configuration

The application uses environment variables for configuration and sensitive values. The local `.env` file should remain private and should be excluded by `.gitignore`.

### Example `.env` template

Create your own `.env` file using the following template. Replace placeholder values locally; never commit actual credentials.

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
EMAIL_MODE=smtp

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_USE_TLS=1
SMTP_USE_SSL=0
SMTP_FROM_EMAIL=Stacks Library <your-email@gmail.com>

# Optional: redirect test emails to your own inbox.
EMAIL_TEST_RECIPIENT=your-test-email@example.com
```

The SMTP and email settings are optional when email functionality is not being tested. Configure the settings required for the chosen email mode.

Generate a unique, random secret for `SECRET_KEY`. Do not reuse the example value or share your actual secret.

### Environment variable reference

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session and security configuration |
| `EMAIL_MODE` | Selects `mock`, `console`, or `smtp` email delivery |
| `SMTP_SERVER` | SMTP server hostname |
| `SMTP_PORT` | SMTP server port; commonly `587` for Gmail TLS |
| `SMTP_USERNAME` | SMTP account username |
| `SMTP_PASSWORD` | SMTP password or provider-specific app password |
| `SMTP_USE_TLS` | Enables SMTP STARTTLS when configured |
| `SMTP_USE_SSL` | Enables SMTP SSL when configured |
| `SMTP_FROM_EMAIL` | Sender address displayed in outgoing emails |
| `EMAIL_TEST_RECIPIENT` | Optional test-only recipient override |
| `LIBRARY_ADMIN_EMAIL` | Admin login used by the Robot Framework bot |
| `LIBRARY_ADMIN_PASSWORD` | Admin password used by the Robot Framework bot |

The application loads its local `.env` configuration when started. The Robot Framework launcher also requires `LIBRARY_ADMIN_EMAIL` and `LIBRARY_ADMIN_PASSWORD` to be available to its process; configure these for the relevant Windows account as described in [Windows Task Scheduler](#windows-task-scheduler).

Do not place real credentials in source code, README examples, batch files, Robot files, screenshots, or Git-tracked configuration.

## Running the Application

1. Activate the virtual environment implicitly by using its Python executable.
2. Confirm that the local configuration is present.
3. Start Flask using the command above.
4. Open `http://127.0.0.1:5000`.
5. Sign in with an appropriate local account.
6. Use the available pages according to your role.

### Local demonstration accounts

The existing project README documents these demonstration credentials:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@stacks.local` | `admin123` |
| Librarian | `librarian@stacks.local` | `library123` |
| Student | `student@stacks.local` | `student123` |

These credentials are intended for local demonstration only. They are not production credentials. Verify that the accounts are created or seeded in your local database before relying on them.

## Registration and Account Activation

The application supports two member registration workflows:

- **Student self-registration:** Students use `/register` to create a member record and linked student login.
- **Staff-created members:** Staff add member records through the Members page without immediately creating login credentials.
- **Account activation:** Staff-created members can use `/activate` with their registered email address to set a password and create their student login.

Member deletion includes safeguards intended to preserve associated loans, accounts, activity logs, and automation history. Records with protected relationships may not be eligible for deletion.

## RPA Automations

The project includes five documented Milestone 4 workflows in addition to the overdue reminder automation.

### 1. Overdue Reminder Automation

**Purpose:** Detect overdue loans and send reminder emails.

- Manual execution through **Automation Centre → Run overdue check**.
- Uses Robot Framework to authenticate with the Flask API, execute the overdue workflow, and verify its logged result.
- Records execution and email delivery status.
- Can be configured to run daily through Windows Task Scheduler.

### 2. Courtesy Due-Date Reminder

**Endpoint:** `POST /api/automation/courtesy`

**Purpose:** Identify active loans due today or tomorrow and send advance notifications before overdue fines accrue.

- Admin-authorized execution.
- Robot bot: `rpa/bots/courtesy_reminder_bot.robot`.
- Records item-level execution and email delivery status.
- Records batch execution activity.

### 3. Catalogue Inventory Health and Restock Advisory

**Endpoint:** `POST /api/automation/inventory-audit`

**Report:** `GET /api/reports/inventory-audit.csv`

**Purpose:** Assess available book inventory and identify stock that may need replenishment.

- Identifies depleted stock using `CRITICAL_DEPLETED`.
- Identifies low available stock using `LOW_STOCK`.
- Generates inventory audit and replenishment information.
- Supports Admin and Librarian roles, subject to authorization.

### 4. Daily Managerial Digest and Financial Reconciliation

**Endpoint:** `POST /api/automation/daily-reconciliation`

**Purpose:** Compile a daily operational summary for library management.

The digest includes available summary metrics such as:

- Books issued and returned.
- Fines assessed and outstanding dues.
- Active loans and related operational figures.
- A summary email for the configured library administrator.

Execution details are recorded in the activity log.

### 5. Unactivated Member Account Invitation

**Endpoint:** `POST /api/automation/member-invitations`

**Purpose:** Identify staff-created members whose student accounts have not been activated and send invitation emails with activation instructions.

- Supports Admin and Librarian roles, subject to authorization.
- Records invitation counts and delivery statuses.
- Uses the configured email delivery system.

### 6. Bulk Catalogue CSV Import

**Endpoint:** `POST /api/automation/books/import-csv`

**Template:** `GET /api/templates/books-template.csv`

**Purpose:** Import multiple catalogue entries from a CSV file rather than adding every book individually.

The documented import workflow validates required fields, including Title, Author, ISBN, Category, and Copies. It skips malformed rows, checks for duplicate ISBNs, increments existing stock where applicable, and adds new catalogue entries.

The import operation records added, updated, and skipped counts in the activity log.

## Email Configuration

The application uses `email_service.py` and supports three documented email modes:

| Mode | Behaviour |
|---|---|
| `mock` | Captures email messages in memory for development and testing |
| `console` | Prints email messages to the terminal and captures them in memory |
| `smtp` | Sends email using the configured SMTP server |

When `EMAIL_MODE` is not explicitly set, the existing configuration can select a default based on whether `SMTP_SERVER` is configured.

### Gmail SMTP

1. Enable the appropriate account security settings for your Gmail account.
2. Generate a Gmail App Password if required.
3. Store the App Password in your private `.env` file.
4. Set `SMTP_SERVER=smtp.gmail.com` and `SMTP_PORT=587`.
5. Use `SMTP_USE_TLS=1` and `SMTP_USE_SSL=0`.
6. Restart Flask after changing the configuration.
7. Test delivery using your own test inbox.

Never use your regular Gmail account password in place of an App Password when an App Password is required.

### Safe testing with a recipient override

Set `EMAIL_TEST_RECIPIENT` to an inbox you control when testing SMTP. The application can redirect notification emails to that address, depending on the configured email service behaviour.

The notification content may still reflect the corresponding member or loan record. Use test records and avoid sharing sensitive information in test emails.

Remove the override only when you intentionally want to restore normal recipient delivery. Verify the application's recipient handling before testing against real member addresses.

### Email delivery failures

An SMTP failure can result from an invalid address, incorrect configuration, authentication problems, or a network issue.

The overdue workflow is designed to record email delivery status such as `[Email: SENT]` or `[Email: FAILED]`. Review the application logs and Automation Log view when diagnosing a failure.

## Running Automated Tests

Run commands from the project root.

### Milestone 3 email tests

```powershell
$env:EMAIL_MODE = 'mock'
.\.venv-windows\Scripts\python.exe -m unittest test_milestone3_email -v
```

These tests cover email configuration and composition, mock transport, overdue workflow integration, email failure handling, credential sanitization, invalid addresses, activity-log counts, and recipient override behaviour.

### Milestone 4 tests

```powershell
$env:EMAIL_MODE = 'mock'
.\.venv-windows\Scripts\python.exe -m unittest test_milestone4 -v
```

### Legacy milestone verifier

```powershell
.\.venv-windows\Scripts\python.exe -m unittest test_milestone3.py -v
```

`test_milestone3.py` is retained as a legacy verifier. It calls the live Flask application directly and may require the application to be running.

**Testing note:** Run tests using the project virtual environment. Tests that call a live API require a running server and appropriate local configuration. Use an isolated test database for destructive or record-changing tests. Do not run destructive tests against the database containing your existing project records.

## Windows Task Scheduler

The overdue reminder can be scheduled to run daily using Windows Task Scheduler.

### Workflow

```text
Windows Task Scheduler
        |
        v
rpa\run_overdue_bot.bat
        |
        v
Robot Framework
        |
        v
Flask API
        |
        v
Automation logs and email delivery
```

### Requirements

- Flask must already be running at `http://127.0.0.1:5000`.
- The scheduled task must run under the Windows account configured for the automation.
- `LIBRARY_ADMIN_EMAIL` and `LIBRARY_ADMIN_PASSWORD` must be available to the Robot process.
- The project virtual environment and Robot Framework dependencies must be installed.
- The application must have the required local configuration.

The batch launcher does not start Flask automatically.

### Configure the task

1. Open Windows Task Scheduler.
2. Choose **Create Task**.
3. Give the task the name `Library RPA - Daily Overdue Reminder`.
4. Under **Triggers**, create a daily trigger at the desired time. For example, 09:00.
5. Under **Actions**, choose **Start a program**.
6. Use `C:\Windows\System32\cmd.exe` as the program.
7. Set the arguments to `/c ""<absolute project path>\rpa\run_overdue_bot.bat""`.
8. Set **Start in** to the absolute project directory.
9. Select the Windows account under which the required environment variables are configured.
10. Save the task and test it using **Run**.

Configure the two `LIBRARY_ADMIN_*` variables in the Windows user environment for the scheduled-task account. Do not place the values in Git-tracked files. Restart or sign out and back in as necessary so the scheduled process receives updated environment variables.

### Run the Robot bot manually

With Flask running and the two admin variables available in the current PowerShell session:

```powershell
.\.venv-windows\Scripts\robot.exe --outputdir rpa\results rpa\bots\overdue_reminder_bot.robot
```

Alternatively, run the launcher:

```powershell
& .\rpa\run_overdue_bot.bat
$LASTEXITCODE
```

Robot Framework writes its reports to:

- `rpa\results\output.xml`
- `rpa\results\log.html`
- `rpa\results\report.html`

The application's Automation Log view and `GET /api/automation/logs` provide access to recorded automation activity.

## Security and Data Protection

Before publishing the project to a public GitHub repository:

- Keep `.env` out of version control.
- Ensure `.gitignore` excludes `.env` and other private configuration files.
- Never commit real SMTP credentials, App Passwords, Flask secrets, or administrator passwords.
- Do not publish private database records or personal member information.
- Do not commit a populated local database unless it has been intentionally sanitized and is safe to share.
- Treat demonstration credentials as local-only and change or disable them for any deployment beyond a controlled demo.
- Keep authorization checks and member deletion safeguards intact.
- Use isolated databases for tests that create, update, or delete records.
- Review staged files before committing.

Useful pre-commit checks:

```powershell
git status --short
git check-ignore .env
git diff --check
git diff --cached --stat
```

`git check-ignore .env` should confirm that the file is ignored. If `.env` or a secret was committed previously, adding it to `.gitignore` does not remove it from Git history. Rotate exposed credentials and clean up the repository history when necessary.

## Troubleshooting

### Flask does not start

- Confirm that the terminal is in the project root.
- Confirm that `.venv-windows` exists.
- Install dependencies from `requirements.txt`.
- Check the terminal for the Python traceback.
- Confirm that port `5000` is not already in use.

### Configuration changes are not applied

- Confirm that `.env` is in the project root.
- Confirm that `python-dotenv` is installed and the application loads the file.
- Restart Flask after changing environment variables.
- Avoid sharing the contents of `.env` when requesting help.

### Email is not delivered

- Verify the selected `EMAIL_MODE`.
- Check SMTP host, port, TLS/SSL configuration, username, and App Password.
- Check whether `EMAIL_TEST_RECIPIENT` is redirecting messages.
- Review the application terminal and Automation Log for delivery errors.
- Test using an inbox you control.

### The Robot automation fails

- Start Flask before running the bot.
- Confirm the Flask URL is `http://127.0.0.1:5000`.
- Verify that the scheduled-task account has the required admin environment variables.
- Confirm the virtual environment and Robot Framework are installed.
- Review the files in `rpa\results`.
- Check the Windows Task Scheduler history and last-run result.

### An API request returns 404

- Check the URL, HTTP method, and requested record ID.
- Confirm Flask is running the latest application code from the correct project directory.
- Restart Flask after source changes when the reloader is disabled.
- Review the Flask terminal for the corresponding request and error.

---

## Project Status

This repository contains a Flask-based library management application with documented RPA workflows for overdue notifications, courtesy reminders, inventory auditing, daily reconciliation, member invitations, and bulk catalogue import.

Refer to the source code, tests, and local configuration for the exact behaviour supported by the current version.

## License

No license is specified in this README. Add an appropriate license file if you intend to permit reuse or distribution of the project.