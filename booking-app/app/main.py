"""
Artisans Asylum booking app — FastAPI entry point.

Run locally:
    cd booking-app
    NEXUDUS_MOCK=1 uvicorn app.main:app --reload

Production:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .auth import router as auth_router
from .resources import router as resources_router
from .bookings import router as bookings_router
from .availability import router as availability_router
from .members import router as members_router

app = FastAPI(title="A² Booking App", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten when auth is added
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# API routes under /api prefix
app.include_router(auth_router, prefix="/api")
app.include_router(resources_router, prefix="/api")
app.include_router(bookings_router, prefix="/api")
app.include_router(availability_router, prefix="/api")
app.include_router(members_router, prefix="/api")

# Serve static files (frontend)
STATIC_DIR = Path(__file__).parent.parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    import os
    return {
        "email_gate": os.getenv("BOOKING_EMAIL_GATE", "0").strip() == "1",
        # IANA timezone name for displaying and submitting booking times.
        # Defaults to America/New_York. Override in .env for other facilities.
        # Future: auto-detect from Nexudus space record (SimpleTimeZoneId field).
        "timezone": os.getenv("BOOKING_TIMEZONE", "America/New_York"),
    }
