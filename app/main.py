from fastapi import FastAPI

from app.database import Base, engine
from app.auth import models as auth_models
from app.courses import models as courses_models
from app.classes import models as classes_models
from app.attendance import models as attendance_models
from app.participation import models as participation_models
from app.auth import router as auth_router
from app.courses import router as courses_router
from app.classes import router as classes_router
from app.attendance import router as attendance_router
from app.participation import router as participation_router
from app.reports import router as reports_router
from app.admin import router as admin_router
from app.signaling import router as signaling_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Virtual Classroom API")


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
app.include_router(signaling_router.router)