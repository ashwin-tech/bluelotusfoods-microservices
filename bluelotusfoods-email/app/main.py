from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.email import router as email_router
from app.api.test import router as test_router
from app.core.settings import settings
import structlog
import os
import sys

# Print startup information
print("=" * 60, flush=True)
print("🚀 Starting Blue Lotus Foods Email Service...", flush=True)
print(f"📍 Python version: {sys.version}", flush=True)
print(f"🔌 PORT environment variable: {os.environ.get('PORT', 'NOT SET')}", flush=True)
print(f"📧 SMTP Server: {settings.smtp_server}", flush=True)
print(f"🎭 Email simulation mode: {settings.email_simulation_mode}", flush=True)
print("=" * 60, flush=True)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

app = FastAPI(
    title="Blue Lotus Foods Email Service",
    description="Microservice for handling automated email notifications",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(email_router, prefix="/email", tags=["Email"])
app.include_router(test_router, prefix="/test", tags=["Test"])

@app.get("/")
async def root():
    return {
        "message": "Blue Lotus Foods Email Service",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run probes"""
    return {
        "status": "healthy", 
        "service": "bluelotusfoods-email",
        "port": os.environ.get('PORT', 'unknown')
    }