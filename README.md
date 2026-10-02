# backend-fastapi

FastAPI backend of **Smart Class** (Smart Virtual Classroom & Intelligent
Attendance Management System). The Flutter app lives in the
`Smart-Virtual-Classroom-and-Intelligent-Attendance-Management-System` repo
(`scra/`); its `docs/api.md` documents every endpoint the app uses.

## Configuration

All settings come from **environment variables** (locally: a `.env` file,
git-ignored; see `.env.example`). Nothing secret is written in the code.

| Variable | Required | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql+psycopg2://user:password@host:5432/smart_classroom` |
| `JWT_SECRET_KEY` | yes | Signs login tokens; at least 32 random characters |
| `ADMIN_REGISTRATION_CODE` | no | Needed to register further admins |
| `CORS_ORIGINS` | in production | Web app address(es) allowed to call the API, comma separated (e.g. `https://smartclass.example.edu`) |
| `CORS_ALLOW_LOCALHOST` | no | `true` (default) also allows `http://localhost:*` for development |

The app refuses to start, with a clear message, if a required value is missing.

## Run (development)

```bash
venv\Scripts\activate
alembic upgrade head          # after pulling changes that add migrations
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive docs: http://localhost:8000/docs
- `--host 0.0.0.0` lets Android phones on the same Wi-Fi connect.
- Password-reset codes are printed in this console (no e-mail service yet).
  A code stops working after 5 wrong attempts; request a new one.

## Run (production)

Without `--reload`, and with **one worker**: live-class rooms (WebRTC
signaling, whiteboard) live in memory, so all participants of a class must
reach the same process.

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
```

Or with Docker (runs the migrations, then the server):

```bash
docker build -t smart-class-api .
docker run -p 8000:8000 -e DATABASE_URL=... -e JWT_SECRET_KEY=... -e CORS_ORIGINS=... smart-class-api
```

`docker compose up --build` starts PostgreSQL and the API together (set
`POSTGRES_PASSWORD` and `JWT_SECRET_KEY` in `.env`).

## Database & migrations

PostgreSQL with **Alembic** migrations (`alembic/versions/`). The app does not
create or change PostgreSQL tables itself; it logs a warning on start if the
database is behind (`alembic upgrade head`).

- Change a model, then: `alembic revision --autogenerate -m "what changed"`,
  review the file in `alembic/versions/`, then `alembic upgrade head`.
- `alembic check` tells whether the models and the migrations match.
- SQLite still works for the test suite and quick experiments (tables are
  created automatically there).

### First-time PostgreSQL setup

With a local PostgreSQL (e.g. PostgreSQL 18 installed with pgAdmin):

```bash
venv\Scripts\activate
python scripts/postgres_setup.py --show-password
```

It asks for the password of the `postgres` superuser (the one used in
pgAdmin), creates the app user `smart_class` and the database
`smart_classroom`, creates the tables, copies everything from `dev.db`, marks
the database as migrated, and writes `DATABASE_URL` to `.env`. Then restart
uvicorn. Options: `--port`, `--database`, `--app-user`, `--skip-copy`,
`--force` (see `--help`). Forgot the `postgres` password? Run
`scripts/reset_postgres_password.ps1` in an administrator PowerShell.

Tests run on SQLite by default; to run them on PostgreSQL point
`TEST_DATABASE_URL` at an empty test database (it is wiped):

```bash
set TEST_DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/smart_classroom_test
python -m pytest
```

## Live classes

- Joining a class marks attendance automatically (admin setting
  "Automatic Join / Leave Recording").
- A class ends when the lecturer taps **End class**. If everyone has left
  (e.g. the lecturer closed the tab) it ends automatically **15 minutes** after
  the last person left; any class still open long after its planned end
  (duration, or 2 h, plus 1 h) is closed too.

## First setup

1. Register the first admin from the app (Admin login → **Register as admin**)
   or `POST /auth/register` with `role: admin`; no code is needed while no
   admin exists.
2. Further admins register the same way with the admin registration code
   (`ADMIN_REGISTRATION_CODE` in `.env`; leave it empty to close admin
   self-registration), or an admin adds them under **Users → Add User**.
3. As admin: create a faculty, a department and courses; assign lecturers to
   courses; put students in departments (students take every course of their
   department, plus explicit enrolments via `POST /courses/{id}/enrollments`).
4. Admin-created accounts without a password are activated by their owner
   from the app (student / lecturer / admin registration with the same email).

## Modules

| Module | Responsibility |
| --- | --- |
| `app/auth` | Accounts, JWT login/refresh, profile, password change/reset |
| `app/courses` | Faculties, departments, courses, enrolment rules, rosters |
| `app/classes` | Scheduling, live classes, participants/raised hands, chat |
| `app/attendance` | Attendance records, student history, summaries, appeals |
| `app/participation` | Live MCQ questions, drafts, responses |
| `app/signaling` | WebRTC signaling socket (records attendance on join) |
| `app/campus` | Notifications, academic terms, system settings, activity log |
| `app/reports` | Dashboards/analytics and PDF/Excel/CSV exports |
| `app/admin` | User administration |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```
