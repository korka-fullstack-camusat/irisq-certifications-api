from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os

from database import connect_to_mongo, close_mongo_connection
from routes import forms, responses, upload, exams, auth, sessions, candidate_account

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
origins = ["*"]
env_origins = os.getenv("ALLOWED_ORIGINS", "")
if env_origins:
    origins.extend([o.strip() for o in env_origins.split(",") if o.strip()])

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
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    console.print(
        Panel.fit(
            Text("IRISQ API is starting \U0001f680", justify="center", style="bold green"),
            border_style="green",
        )
    )


@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    console.print(
        Panel.fit(
            Text("IRISQ API is shutdown \U0001f6d1", justify="center", style="bold red"),
            border_style="red",
        )
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "IRISQ Form Builder API",
        "description": "Backend service for managing forms, responses, uploads, exams and sessions",
        "status": "\U0001f7e2 running",
        "version": "1.0.0",
        "documentation": {"swagger": "/docs", "redoc": "/redoc"},
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


# Routers
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(forms.router, prefix="/api/forms", tags=["Forms"])
app.include_router(responses.router, prefix="/api", tags=["Responses"])
app.include_router(upload.router, prefix="/api", tags=["Uploads"])
app.include_router(exams.router, prefix="/api", tags=["Exams"])
app.include_router(candidate_account.router, prefix="/api/candidate", tags=["Candidate"])
