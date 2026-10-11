import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before core.db / routers read their settings from the environment

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from core import db  # noqa: E402
from routers.integrated import router  # noqa: E402


@asynccontextmanager
async def lifespan(_):
    db.init_db()
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
app.include_router(router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": app.version}
