import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before core.db / routers read their settings from the environment
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from core import db  # noqa: E402
from routers.layout import router as layout_router  # noqa: E402
from routers.validation import router as validation_router  # noqa: E402
from routers.integrated import router  # noqa: E402
from routers.style import router as style_router  # noqa: E402
from routers.flags import router as flags_router  # noqa: E402
from routers.reporting import router as reporting_router  # noqa: E402
from routers.clients import router as clients_router  # noqa: E402
from routers.statements import router as statements_router  # noqa: E402
from routers.notifications import router as notifications_router  # noqa: E402
from routers.invitations import router as invitations_router  # noqa: E402
from routers.traceability import router as traceability_router  # noqa: E402
from routers.testing_design import router as testing_design_router  # noqa: E402
from routers.testing_cases import router as testing_cases_router  # noqa: E402
from routers.testing_runs import router as testing_runs_router  # noqa: E402
from routers.stories import router as stories_router  # noqa: E402
from routers.design import router as design_router  # noqa: E402
from routers.admin import router as admin_router  # noqa: E402
from routers.members import router as members_router  # noqa: E402


@asynccontextmanager
async def lifespan(_):
    # Mock tokens let anyone sign in as any email; never allow them next to real Supabase auth.
    if os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true" and os.getenv("SUPABASE_URL"):
        raise RuntimeError("DEV_AUTH_BYPASS=true is for local development only; unset it when SUPABASE_URL is set.")
    db.init_db()
    db.fail_interrupted_jobs()
    yield
    db.pool.close()


app = FastAPI(title="SDDG Backend API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Any crash is recorded for the admin Errors page (FR25d): class name and route template only, never the
    message or the URL (either can carry requirement text)."""
    route = getattr(request.scope.get("route"), "path", "unknown route")
    await asyncio.to_thread(db.record_error, "api", "error", f"{type(exc).__name__} in {request.method} {route}")
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)


app.include_router(layout_router, prefix="/api/v1")
app.include_router(validation_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(style_router, prefix="/api/v1")
app.include_router(flags_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(statements_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(invitations_router, prefix="/api/v1")
app.include_router(traceability_router, prefix="/api/v1")
app.include_router(testing_design_router, prefix="/api/v1")
app.include_router(testing_cases_router, prefix="/api/v1")
app.include_router(testing_runs_router, prefix="/api/v1")
app.include_router(stories_router, prefix="/api/v1")
app.include_router(design_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(members_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": app.version}
