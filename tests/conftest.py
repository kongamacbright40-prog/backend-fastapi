import os
import tempfile

import pytest

# Point the app at a throwaway database before it is imported. Set
# TEST_DATABASE_URL (e.g. a PostgreSQL test database) to run against it; it
# is wiped at the start of the run.
_DB_DIR = tempfile.mkdtemp(prefix="smart_class_tests_")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_DB_DIR}/test.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-0123456789"
os.environ["CORS_ORIGINS"] = "https://smartclass.example.edu, https://admin.example.edu/"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

if os.environ.get("TEST_DATABASE_URL"):
    from app.database import Base, engine  # noqa: E402

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

PASSWORD = "Password123!"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, email, password=PASSWORD):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def world(client):
    """Admin, faculty, department, course, lecturer and student."""
    r = client.post(
        "/auth/register",
        json={"full_name": "Root Admin", "email": "admin@uni.edu", "password": PASSWORD, "role": "admin"},
    )
    assert r.status_code == 201, r.text
    admin = auth(client, "admin@uni.edu")

    faculty = client.post("/faculties", json={"name": "Science"}, headers=admin).json()
    dept = client.post("/departments", json={"name": "Computer Science", "faculty_id": faculty["id"]}, headers=admin).json()
    lecturer = client.post(
        "/auth/register",
        json={
            "full_name": "Kofi Mensah",
            "email": "lecturer@uni.edu",
            "password": PASSWORD,
            "role": "lecturer",
            "matricule_number": "FAC-1",
        },
    ).json()
    student = client.post(
        "/auth/register",
        json={
            "full_name": "Amina Bello",
            "email": "student@uni.edu",
            "password": PASSWORD,
            "role": "student",
            "matricule_number": "ICT-1",
            "department_id": dept["id"],
        },
    ).json()
    course = client.post(
        "/courses",
        json={"code": "CS-301", "title": "Data Structures", "department_id": dept["id"], "credits": 4},
        headers=admin,
    ).json()
    return {
        "admin": admin,
        "lecturer": auth(client, "lecturer@uni.edu"),
        "student": auth(client, "student@uni.edu"),
        "lecturer_id": lecturer["id"],
        "student_id": student["id"],
        "faculty": faculty,
        "dept": dept,
        "course": course,
    }
