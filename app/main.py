from contextlib import asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import api_router
from app.database import SessionLocal, init_db, migrate_db
from app.observability import configure_logging, request_id_context
from app.services import migrate_archived_evaluations

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
configure_logging()
logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_db()
    init_db()
    with SessionLocal() as db:
        migrate_archived_evaluations(db)
    yield


app = FastAPI(title="毕节金融监管分局人事考核系统 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "").strip()[:128] or uuid4().hex
    token = request_id_context.set(request_id)
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception("Unhandled request error")
        raise
    finally:
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "client_ip": request.client.host if request.client else "-",
            },
        )
        request_id_context.reset(token)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database readiness check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


@app.get("/health")
def health():
    return health_ready()


if FRONTEND_DIST.exists():
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    def frontend_spa(path: str = ""):
        """Serve the React entry point for client-side application routes."""
        return FileResponse(FRONTEND_DIST / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        return JSONResponse(
            {
                "message": "API 服务已启动。前端开发请运行：cd frontend && npm run dev -- --host 127.0.0.1 --port 5173",
            }
        )
