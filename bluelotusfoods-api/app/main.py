from fastapi import FastAPI
from app.api.vendor_quote import dictionary, vendors, fish, quotes, email
from app.api import buyer_pricing
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.db import init_db_pool,close_db_pool
from app.core.settings import settings
import os
import sys

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        print("=" * 60, flush=True)
        print("🚀 Starting Blue Lotus Foods API...", flush=True)
        print(f"📍 Python version: {sys.version}", flush=True)
        print(f"🔌 PORT environment variable: {os.environ.get('PORT', 'NOT SET')}", flush=True)
        print(f"💾 Database host: {settings.db_host}", flush=True)
        print(f"📧 Email service URL: {settings.email_service_url}", flush=True)
        print("=" * 60, flush=True)
        
        init_db_pool()
        print("✅ Database pool initialized successfully", flush=True)
    except Exception as e:
        print(f"❌ Failed to initialize database pool: {e}", flush=True)
        print(f"⚠️  Continuing startup without database connection", flush=True)
        # Don't raise - allow app to start even if DB is unavailable
        # DB errors will be caught per-request
    
    print("✅ Application startup complete - ready to accept requests", flush=True)
    yield 

    # Shutdown
    try:
        print("🛑 Shutting down Blue Lotus Foods API...", flush=True)
        close_db_pool()
        print("✅ Database pool closed", flush=True)
    except Exception as e:
        print(f"⚠️ Error closing database pool: {e}", flush=True)

app = FastAPI(title="Blue Lotus Foods API", lifespan=lifespan)

# CORS (frontend <-> backend communication)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to Blue Lotus Foods API",
        "status": "running",
        "available_endpoints": {
            "documentation": "/docs",
            "dictionary": "/dictionary",
            "vendors": "/vendors",
            "fish": "/fish",
            "quotes": "/quotes",
            "buyer_pricing": "/buyer-pricing"
        }
    }

# Include routers
app.include_router(dictionary.router, prefix="/dictionary", tags=["Dictionary"])
app.include_router(vendors.router, prefix="/vendors", tags=["Vendors"])
app.include_router(fish.router, prefix="/fish", tags=["Fish"])
app.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
app.include_router(email.router, prefix="/quotes", tags=["Email"])
app.include_router(buyer_pricing.router, prefix="/buyer-pricing", tags=["Buyer Pricing"])

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run probes"""
    return {
        "status": "healthy", 
        "service": "bluelotusfoods-api",
        "port": os.environ.get('PORT', 'unknown')
    }
