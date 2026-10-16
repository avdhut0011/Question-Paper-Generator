# Ashoka Assessment Platform

Question paper and question bank generation for teachers and administrators at Ashoka Group of Schools. Developed by Avadhut Jagtap.

The platform includes staff login, school permissions, generation history, reviewed content libraries, administrator approval, and an academic AI assistant. The original QPG interface uses a shared Material-style theme.

The active `app.py` serves the authenticated school platform. The original QPG homepage, bank/paper forms, upload workflow, preview, and chat are active. Generation routes require login and queue school-scoped jobs. Filename-based URLs now accept authorized artifact IDs only; desktop-open endpoints remain disabled. The structured assessment builder remains an additional workflow. Legacy files are not automatically published or assigned to a teacher.

## Run the software on this Windows PC

Use PowerShell. This PC already has `.env`, the application database, and an administrator configured. PostgreSQL must be running. For normal use, you do not need to reinstall packages, recreate the database, or create another administrator.

### Open the Windows application

```powershell
Set-Location -LiteralPath 'C:\AVADHUT\Question-Paper-Generator-main'
.\start_desktop.bat
```

You can also double-click `start_desktop.bat` in File Explorer. The launcher starts or reuses the local web server and worker and opens QPG in its dedicated Windows application window. Sign in with your existing account.

### Open in a normal browser instead

```powershell
Set-Location -LiteralPath 'C:\AVADHUT\Question-Paper-Generator-main'
powershell.exe -NoProfile -File .\scripts\start_desktop.ps1 -CheckOnly
Start-Process 'http://127.0.0.1:8080/'
```

The `-CheckOnly` option checks and starts the backend if needed; it does not open the desktop window. Use this instead of starting another server manually when the launcher already manages the application.

### Restart after code changes

```powershell
Set-Location -LiteralPath 'C:\AVADHUT\Question-Paper-Generator-main'
powershell.exe -NoProfile -File .\scripts\restart_local.ps1
.\start_desktop.bat
```

Restart waits for you to finish active generation first: the script refuses to restart while a job is running. Closing the application window alone leaves the backend running so generation jobs can finish.

### Install or update Python dependencies when needed

```powershell
Set-Location -LiteralPath 'C:\AVADHUT\Question-Paper-Generator-main'
python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
```

This command uses the system Python's pip to install into the project's `.venv`, including when `.venv` has no pip module. Run it when dependencies change, then use the restart commands above. For a new PC, follow the setup sections below first and use its actual project folder.

### Check the application logs

```powershell
Get-Content 'C:\AVADHUT\Question-Paper-Generator-main\instance\web.stderr.log' -Tail 40
Get-Content 'C:\AVADHUT\Question-Paper-Generator-main\instance\worker.stderr.log' -Tail 40
```

### Recover a forgotten administrator password

From a trusted local PowerShell console on the application server:

```powershell
Set-Location -LiteralPath 'C:\AVADHUT\Question-Paper-Generator-main'
.\.venv\Scripts\python.exe -m flask --app school_platform:create_app reset-admin-password --email admin@ashoka.local
```

Enter a new password of at least 12 characters, then enter it again to confirm. Typing is hidden. The command updates the password immediately, clears the account's failed-login lock, signs out existing sessions, and records an audit event. It cannot create accounts or reactivate disabled accounts. It does not change papers or history. Sign in again with the new password; no server restart is needed. If repeated attempts have triggered the separate IP rate limit, wait 15 minutes before trying again. Keep server filesystem and database access restricted to trusted administrators.

## Install dependencies

Use Python 3.12 or newer (verified with Python 3.13 on Windows). From the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If Windows environment creation fails during ensurepip, use your working Python pip:

```powershell
python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
```

`requirements.txt` is the single dependency file for the server, original generation workflows, and test tools. It pins the versions verified in the working environment, including transitive dependencies. PostgreSQL, Microsoft Edge, Tesseract OCR, and PDFLaTeX are installed separately when needed.

## Configure PostgreSQL

Create a dedicated database and account using your existing PostgreSQL administration tool. Grant that account migration privileges in this application's dedicated schema; avoid using a PostgreSQL superuser for the running application. Use an empty dedicated database for the first migration, or inspect the migration SQL against your existing schema before applying it. Setup does not reset or drop existing databases.

Add the settings from `sample.env` to `.env` while preserving your existing AI key. Set `DATABASE_URL` for your intended PostgreSQL database. For example:

```dotenv
DATABASE_URL=postgresql+psycopg://qpg_user:URL_ENCODED_PASSWORD@localhost:5432/ashoka_qpg
FLASK_SECRET_KEY=YOUR_RANDOM_SECRET
QPG_HTTPS=false
QPG_REQUIRE_PDF=false
```

Generate a signing secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use `QPG_HTTPS=false` only for local HTTP development; production should use HTTPS and `QPG_HTTPS=true`. Keep private storage outside public folders. `QPG_STORAGE_ROOT` defaults to `instance/private` under the project. All workers and web processes must see the same durable storage. Do not serve this directory through a static web-server mapping.

Set `GEMINI_MODEL` to a model supported by your account when using AI drafts. The active pipeline uses the modern Google GenAI SDK. API keys are not required for login or approved-bank mode.

## Apply migrations and create the first administrator

Back up an existing database before applying migrations.

```powershell
.\.venv\Scripts\python.exe -m flask --app school_platform:create_app db upgrade
.\.venv\Scripts\python.exe -m flask --app school_platform:create_app bootstrap-admin
```

The administrator command prompts for name, email, school, and password without putting the password in shell history. It creates the first group administrator only. Use a different administrator to approve papers created by an administrator: self-approval is blocked.

## Start the web process and worker

### Windows application window

After completing the database and dependency setup, double-click `start_desktop.bat`. It starts the local web server and generation worker in the background, waits for the homepage, and opens the existing interface in a dedicated Microsoft Edge application window without browser tabs or an address bar. Edge must be installed. Existing managed processes are reused, so reopening the window does not interrupt generation or start another worker.

This launcher uses the installed Python environment and PostgreSQL; it is not a standalone installer. AI features need an internet connection. The window has its own sign-in session, stored under `instance/desktop-profile`.

Closing the window leaves the server and worker running so pending jobs can finish. `scripts/restart_local.ps1` can restart them when no generation job is active. Do not delete `instance/running_processes.json` while they are running.

To check/start the backend without opening a window:

```powershell
powershell.exe -NoProfile -File .\scripts\start_desktop.ps1 -CheckOnly
```

### Browser/server mode

Run these in separate terminals from the project directory:

```powershell
.\.venv\Scripts\python.exe serve.py --host 127.0.0.1 --port 8080
```

```powershell
.\.venv\Scripts\python.exe -m flask --app school_platform:create_app worker
```

Open `http://127.0.0.1:8080`. Production needs an HTTPS reverse proxy, secure cookies, persistent PostgreSQL/private storage, and supervised workers. Multiple workers claim jobs using PostgreSQL row locks with `SKIP LOCKED`.

PDF output requires a TeX distribution with `pdflatex`, `amsmath`, `amssymb`, `enumitem`, and `geometry`. With `QPG_REQUIRE_PDF=true`, missing or failed compilation fails the job rather than publishing a changed paper. With `false`, HTML and LaTeX are produced. HTML preserves formulas as source notation; PDF is the typeset output. Run compilation workers under an OS account/container with minimal filesystem access. Command filtering and `-no-shell-escape` are additional safeguards, not a full OS sandbox.

## School onboarding

1. Add schools and staff in **Staff & schools**. Temporary passwords must be changed at first login. Administrators can reset staff passwords; changes/resets revoke existing sessions.
2. Assign teachers a grade, subject, and board. Names must match paper allocations exactly.
3. Publish reviewed source text/PDF/TXT or import reviewed XLSX/JSON questions in **Approved library**. Download the provided spreadsheet template; old banks lacking answer keys or rubrics must be completed before import. Source versions are immutable and school-scoped. Bank questions require answers, solutions, classifications, and marking schemes.
4. Teachers choose source mode, assessment details, and question allocation in **Create paper**. Marks and counts must balance. Exact question repeats from the last 90 days are excluded.
5. Workers generate, validate, and save exact snapshots. Failures remain visible in **History**.
6. Teachers review drafts and keys, then submit. A different administrator checks the content and approves. Final downloads unlock after approval.
   The reviewer can optionally publish the checked questions into the school's approved bank; duplicate stems are not imported again.
7. **Create revision** preserves the original paper and queues a new draft requiring fresh approval.

Student HTML/LaTeX/PDF outputs omit answers. The separate answer artifact remains staff-only. No public student links are created.

## Current boundaries

- Structured allocations support compulsory MCQ, Short Answer, Long Answer, Numerical, and True/False questions. Internal choices, diagrams, and data-table structures need dedicated schema/rendering support before enabling them. Unsupported fields are rejected.
- Approved text passages use exact reference/quote validation. This is bounded source grounding, not indexed RAG. Factual/solution correctness and semantic evidence support still require human review.
- Arbitrary numerical solving and calibrated educational difficulty are not automated. Difficulty and Bloom labels are reviewed metadata.
- Local accounts are implemented. SSO, administrator MFA, multiple school memberships per user, and email password reset integrations are not included. Users currently have one home school.
- Jobs are durable; only queued jobs can be cancelled. Stop affected workers before `recover-jobs --older-than-minutes 120` marks abandoned running jobs failed. Recovery does not repeat paid AI requests; create a new attempt.
- Limits are three active jobs and thirty submissions per teacher per rolling day. AI slots allow three generation/validation attempts; provider timeouts are bounded.
- Run `flask --app school_platform:create_app prune-login-attempts` periodically to remove expired rate-limit counters; audit events remain intact.
- Existing loose Excel/PDF files have no trustworthy ownership or approval records and need explicit review/import. The original generation forms and chat are retained through authenticated adapters. Their outputs are staff-owned drafts, recorded in history, and must be reviewed by teachers. The additional structured-paper workflow retains its administrator approval gate.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use temporary SQLite storage for isolated behavior. For real PostgreSQL migrations and locking, set `TEST_DATABASE_URL` to an **empty disposable test database**:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://.../ashoka_qpg_test'
.\.venv\Scripts\python.exe -m pytest tests/test_postgresql.py -q
```

Never use production as the test database. PostgreSQL integration tests are opt-in and use a private temporary schema. No live PostgreSQL or AI verification is claimed without a configured connection/key. Back up both the database and private artifacts and verify restores before rollout.

## Project conventions

Legacy desktop configuration and uploaded papers found during cleanup are preserved under `instance/legacy-desktop-data`. They are not automatically imported into the school platform.

- Preserve the original homepage, generation forms, upload, preview, and chat workflows. Integrate account and administrator features into these screens.
- Use `templates/theme_head.html`, `static/qpg-theme.css`, and shared navigation for consistent styling.
- Keep generation authenticated and school-scoped, with authorized private artifact IDs for downloads.
- Preserve `.env`, user data, and private artifacts. Never print credentials in logs.
- Run relevant tests before restarting. `scripts/restart_local.ps1` restarts only recorded project processes and refuses while generation jobs are running.
- Creator/developer branding is Avadhut Jagtap. Do not invent personal contact or social links.

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Avadhut Jagtap <avadhutjagtap1341@gmail.com>.
