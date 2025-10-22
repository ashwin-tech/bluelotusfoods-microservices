from fastapi import FastAPI
from app.api.vendor_quote import dictionary, vendors, fish, quotes, email
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.db import init_db_pool,close_db_pool
from app.core.settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db_pool()
    print("Database pool initialized ✅")

    yield 

    # Shutdown
    close_db_pool()
    print("Database pool closed 🛑")

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
            "quotes": "/quotes"
        }
    }

# Include routers
app.include_router(dictionary.router, prefix="/dictionary", tags=["Dictionary"])
app.include_router(vendors.router, prefix="/vendors", tags=["Vendors"])
app.include_router(fish.router, prefix="/fish", tags=["Fish"])
app.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
app.include_router(email.router, prefix="/quotes", tags=["Email"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "bluelotusfoods-api"}
