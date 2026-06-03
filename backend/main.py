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
from seed.demo_seed import seed_demo_data

# Route modules — imported here; implemented progressively in later phases.
from routes.review    import router as review_router
from routes.traces    import router as traces_router
from routes.feedback  import router as feedback_router
from routes.dashboard import router as dashboard_router
from routes.evals     import router as evals_router
from agentops_push    import full_sync, ensure_agent_registered


# ---------------------------------------------------------------------------
# Lifespan: runs once on startup and once on shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup; clean up on shutdown."""
    # Ensure all database tables exist before the first request is served.
    init_db()
    # Seed demo data if the DB is empty (first deploy on Railway).
    seed_demo_data()
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
#   • Production frontend      : https://pharmacomplianceai.krishnaparuchuri.com
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "https://gmpdeviationreview.krishnaparuchuri.com",
    "https://pharmacomplianceai.krishna1parchuri.workers.dev",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Eval-Token"],
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
# AgentOps integration — POST /api/agentops/sync
# Manually trigger a sync of the last 7 days of cost/token data to AgentOps.
# Also registers the agent in AgentOps if it doesn't exist yet.
# ---------------------------------------------------------------------------
@app.post("/api/agentops/sync", tags=["AgentOps"])
def sync_to_agentops():
    """
    Push the last 7 days of review cost/token data to the AgentOps governance
    dashboard. Also ensures the agent is registered. Safe to call repeatedly —
    AgentOps cost records use INSERT OR IGNORE so duplicates are skipped.

    Requires AGENTOPS_API_URL environment variable to be set.
    """
    return full_sync()


# ---------------------------------------------------------------------------
# Health check — always available, no DB dependency
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
def health_check() -> dict:
    """Return service status. Used by frontend to confirm the backend is reachable."""
    return {"status": "ok", "service": "SOP Deviation Review Assistant", "version": "1.0.0"}


@app.get("/debug/langsmith", tags=["System"])
def debug_langsmith() -> dict:
    """Diagnose LangSmith connectivity. Remove after debugging."""
    import os
    result: dict = {
        "LANGSMITH_API_KEY":  (os.environ.get("LANGSMITH_API_KEY",  "NOT SET")[:12] + "...") if os.environ.get("LANGSMITH_API_KEY")  else "NOT SET",
        "LANGSMITH_PROJECT":  os.environ.get("LANGSMITH_PROJECT",  "NOT SET"),
        "LANGSMITH_TRACING":  os.environ.get("LANGSMITH_TRACING",  "NOT SET"),
        "LANGCHAIN_API_KEY":  (os.environ.get("LANGCHAIN_API_KEY",  "NOT SET")[:12] + "...") if os.environ.get("LANGCHAIN_API_KEY")  else "NOT SET",
        "LANGCHAIN_PROJECT":  os.environ.get("LANGCHAIN_PROJECT",  "NOT SET"),
        "LANGCHAIN_TRACING_V2": os.environ.get("LANGCHAIN_TRACING_V2", "NOT SET"),
    }
    import uuid as _uuid, urllib.request as _ur, json as _json
    from datetime import datetime, timezone
    api_key = os.environ.get("LANGSMITH_API_KEY", "")

    # Raw HTTP test — bypasses SDK to isolate account vs SDK issue
    try:
        payload = _json.dumps({
            "id":         str(_uuid.uuid4()),
            "name":       "debug-test-run",
            "run_type":   "chain",
            "inputs":     {"test": True},
            "outputs":    {"result": "debug"},
            "session_name": "gmp-deviation-review",
            "start_time": datetime.now(timezone.utc).isoformat(),
        }).encode()
        req = _ur.Request(
            "https://api.smith.langchain.com/runs",
            data    = payload,
            method  = "POST",
            headers = {"x-api-key": api_key, "Content-Type": "application/json"},
        )
        with _ur.urlopen(req, timeout=10) as r:
            result["raw_http_post"] = f"OK — status {r.status}"
            result["connection"] = "OK"
    except Exception as exc:
        result["raw_http_post"] = f"FAILED: {exc}"
        result["connection"] = "FAILED"

    # Also test GET /info (no auth needed) to confirm network is reachable
    try:
        with _ur.urlopen("https://api.smith.langchain.com/info", timeout=5) as r:
            result["api_reachable"] = f"OK — status {r.status}"
    except Exception as exc:
        result["api_reachable"] = f"FAILED: {exc}"

    return result


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
