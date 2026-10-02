from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine
from app.auth import models as auth_models  # noqa: F401  (register tables)
from app.courses import models as courses_models  # noqa: F401
from app.classes import models as classes_models  # noqa: F401
from app.attendance import models as attendance_models  # noqa: F401
from app.participation import models as participation_models  # noqa: F401
from app.campus import models as campus_models  # noqa: F401
from app.migrations import add_missing_columns
from app.auth.security import warm_up as warm_up_password_hashing
from app.auth import router as auth_router
from app.courses import router as courses_router
from app.classes import router as classes_router
from app.attendance import router as attendance_router
from app.participation import router as participation_router
from app.reports import router as reports_router
from app.admin import router as admin_router
from app.campus import router as campus_router
from app.signaling import router as signaling_router

Base.metadata.create_all(bind=engine)
add_missing_columns(engine)


def _warm_up() -> None:
    """Pays one-time costs (bcrypt backend, ORM mapper setup) at startup, so
    the first login/registration after a (re)start isn't slow."""
    warm_up_password_hashing()
    with SessionLocal() as db:
        db.query(auth_models.Profile).first()


_warm_up()

app = FastAPI(title="Smart Virtual Classroom API")

# Lets the Flutter web app (served from any localhost port) call the API.
# Android/iOS apps are not subject to CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(courses_router.router)
app.include_router(classes_router.router)
app.include_router(attendance_router.router)
app.include_router(participation_router.router)
app.include_router(reports_router.router)
app.include_router(admin_router.router)
app.include_router(campus_router.router)
app.include_router(signaling_router.router)
