"""
main.py — FastAPI application entry point for the SOP Deviation Review Assistant.

Responsibilities:
  - Create the FastAPI app instance
  - Register CORS middleware (allows React dev server at localhost:5173)
  - Register all API routers
  - Initialize the SQLite database on startup
  - Provide a health-check endpoint

Run with:
    uvicorn backend.main:app --reload          # from project root
    uvicorn main:app --reload --port 8000      # from backend/
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.init_db import init_db

# Route modules — imported here; implemented progressively in later phases.
from routes.review    import router as review_router
from routes.traces    import router as traces_router
from routes.feedback  import router as feedback_router
from routes.dashboard import router as dashboard_router
from routes.evals     import router as evals_router


# ---------------------------------------------------------------------------
# Lifespan: runs once on startup and once on shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup; clean up on shutdown."""
    # Ensure all database tables exist before the first request is served.
    init_db()
    yield
    # Nothing to tear down in V1.


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SOP Deviation Review Assistant",
    description=(
        "A GMP compliance assistant that reviews pharmaceutical manufacturing "
        "deviations, retrieves relevant SOP guidance, and recommends QA escalation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS — must be registered BEFORE any routers
#
# Allowed origins cover:
#   • Vite default dev server  : http://localhost:5173
#   • Alternate Vite port      : http://localhost:5174  (used if 5173 is taken)
#   • Create-React-App default : http://localhost:3000  (fallback)
#
# In production, replace these with your actual frontend domain.
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


# ---------------------------------------------------------------------------
# Routers — registered as modules are built (Phase 2 onward)
# ---------------------------------------------------------------------------
app.include_router(review_router,    prefix="/api", tags=["Review"])
app.include_router(traces_router,    prefix="/api", tags=["Traces"])
app.include_router(feedback_router,  prefix="/api", tags=["Feedback"])
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(evals_router,     prefix="/api", tags=["Evals"])


# ---------------------------------------------------------------------------
# Health check — always available, no DB dependency
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
def health_check() -> dict:
    """Return service status. Used by frontend to confirm the backend is reachable."""
    return {"status": "ok", "service": "SOP Deviation Review Assistant", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Root — friendly message for browser / curl visits
# ---------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root() -> dict:
    """Root endpoint — confirms the API is running."""
    return {
        "message": "SOP Deviation Review Assistant API",
        "docs":    "/docs",
        "health":  "/health",
    }
