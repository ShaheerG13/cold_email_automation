from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from arcticai.app.db.init_db import init_db
from arcticai.app.routes.companies import router as companies_router
from arcticai.app.routes.emails import router as emails_router
from arcticai.app.routes.outreach import router as outreach_router
from arcticai.app.routes.user import router as user_router


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="ArcticAI", version="0.1.0")
    app.include_router(user_router, prefix="/users", tags=["users"])
    app.include_router(companies_router, prefix="/companies", tags=["companies"])
    app.include_router(emails_router, prefix="/emails", tags=["emails"])
    app.include_router(outreach_router, tags=["outreach"])

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def _index() -> FileResponse:
            return FileResponse(str(static_dir / "index.html"))

    @app.on_event("startup")
    async def _startup() -> None:
        await init_db()

    return app


app = create_app()

