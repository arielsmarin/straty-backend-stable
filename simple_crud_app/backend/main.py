from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routes.config_routes import router

app = FastAPI(title="Panoconfig360 Tenant Config CRUD")
app.include_router(router)


@app.on_event("startup")
async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.exception_handler(404)
async def not_found_handler(_, __):
    return JSONResponse(status_code=404, content={"status": "error", "data": None, "error": "recurso não encontrado"})


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
