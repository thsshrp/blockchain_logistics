from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.v1 import api_router
from app.core.config import NodeSettings
from app.services.node_service import NodeService

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Optional[NodeSettings] = None,
    http_transport: Optional[httpx.AsyncBaseTransport] = None,
) -> FastAPI:
    cfg = settings or NodeSettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        svc: NodeService = application.state.node_service
        svc.start_background_sync()
        try:
            yield
        finally:
            await svc.stop_background_sync()

    application = FastAPI(
        title=f"Blockchain Logistics Node ({cfg.node_id})",
        version="0.5.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.node_service = NodeService(cfg, http_transport=http_transport)
    application.include_router(api_router, prefix="/api/v1")

    @application.get("/", include_in_schema=False)
    async def serve_ui():
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()