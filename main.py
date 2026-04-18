from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import os

from database import connect_to_mongo, close_mongo_connection
from routes import forms, responses, upload, exams, auth, sessions, candidate, candidate_auth

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

app = FastAPI(
    title="Irisq Form Builder API",
    description="Backend API for Irisq Form Builder using FastAPI and MongoDB",
    version="1.0.0",
    redirect_slashes=False,
)

# CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://172.30.80.1:3000",
]
env_origins = os.getenv("ALLOWED_ORIGINS", "")
if env_origins:
    origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # We don't set X-Frame-Options: DENY because the frontend heavily relies on iframe for PDF Viewer
        return response

app.add_middleware(SecurityHeadersMiddleware)

# 🚀 STARTUP EVENT
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

    console.print(
        Panel.fit(
            Text("IRISQ API is starting 🚀", justify="center", style="bold green"),
            border_style="green"
        )
    )

# 🛑 SHUTDOWN EVENT
@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

    console.print(
        Panel.fit(
            Text("IRISQ API is shutdown 🛑", justify="center", style="bold red"),
            border_style="red"
        )
    )

# ✅ ROOT ENDPOINT
@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "IRISQ Form Builder API",
        "description": "Backend service for managing forms, responses, uploads, exams and sessions",
        "status": "🟢 running",
        "version": "1.0.0",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        }
    }

# (optionnel) health check
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

# Static files
# (Removed local uploads directory mounting since we use GridFS now)

# Routers
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(forms.router, prefix="/api/forms", tags=["Forms"])
app.include_router(responses.router, prefix="/api", tags=["Responses"])
app.include_router(upload.router, prefix="/api", tags=["Uploads"])
app.include_router(exams.router, prefix="/api", tags=["Exams"])
app.include_router(candidate_auth.router, prefix="/api/candidate", tags=["Candidate Auth"])
app.include_router(candidate.router, prefix="/api/candidate", tags=["Candidate"])
