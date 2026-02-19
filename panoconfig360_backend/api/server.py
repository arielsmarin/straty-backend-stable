# api/server.py
import os
import gc
import json
import logging
import shutil
import time
import tempfile
import threading
import re
from pathlib import Path
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from panoconfig360_backend.render.dynamic_stack import (
    load_config,
    build_string_from_selection,
)
from panoconfig360_backend.render.split_faces_cubemap import process_cubemap
from panoconfig360_backend.render.scene_context import resolve_scene_context
from panoconfig360_backend.render.dynamic_stack_with_masks import (
    stack_layers_image_only,
)

from panoconfig360_backend.models.render_2d import Render2DRequest
from panoconfig360_backend.storage.factory import (
    append_jsonl,
    exists,
    get_json,
    read_jsonl_slice,
    upload_file,
    get_public_url,
)
from panoconfig360_backend.storage.tile_upload_queue import TileUploadQueue
from panoconfig360_backend.utils.build_validation import (
    validate_build_string,
    validate_safe_id,
)

# ==========================================================
# CONFIGURAÇÕES GLOBAIS
# ==========================================================

ROOT_DIR = Path(__file__).resolve().parents[1].parent
LOCAL_CACHE_DIR = ROOT_DIR / "panoconfig360_cache"
FRONTEND_DIR = ROOT_DIR / "panoconfig360_frontend"

os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)

TILE_RE = re.compile(r"^[0-9a-z]+_[fblrud]_\d+_\d+_\d+\.jpg$")
TILE_ROOT_RE = re.compile(
    r"^clients/[a-z0-9\-]+/cubemap/[a-z0-9\-]+/tiles/[0-9a-z]+$"
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

last_request_time = 0.0
lock = threading.Lock()
MIN_INTERVAL = 1.0
MAX_RENDER_LOCKS = 256


# ==========================================================
# THREAD CONFIG
# ==========================================================

def _pipeline_threads() -> int:
    try:
        requested = int(os.getenv("TEST_MODE_THREADS", "1"))
    except ValueError:
        requested = 1
    return max(1, min(requested, 2))


PIPELINE_THREADS = _pipeline_threads()

render_locks: OrderedDict[str, threading.Lock] = OrderedDict()
render_locks_guard = threading.Lock()

active_background_renders: set[str] = set()
active_background_guard = threading.Lock()

BUILD_STATUS: dict[str, dict] = {}
BUILD_STATUS_LOCK = threading.Lock()


# ==========================================================
# UTILITIES
# ==========================================================

def _get_render_lock(render_key: str) -> threading.Lock:
    with render_locks_guard:
        if render_key in render_locks:
            render_locks.move_to_end(render_key)
            return render_locks[render_key]

        new_lock = threading.Lock()
        render_locks[render_key] = new_lock

        while len(render_locks) > MAX_RENDER_LOCKS:
            render_locks.popitem(last=False)

        return new_lock


def _write_metadata_file(payload: dict, tmp_dir: str) -> str:
    path = os.path.join(tmp_dir, "metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def _tiles_base_url() -> str:
    return get_public_url("").rstrip("/")


# ==========================================================
# CLIENT CONFIG
# ==========================================================

def load_client_config(client_id: str):
    validate_safe_id(client_id, "client_id")

    config_path = (
        LOCAL_CACHE_DIR / "clients" / client_id / f"{client_id}_cfg.json"
    )

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuração do cliente '{client_id}' não encontrada."
        )

    project, scenes, naming = load_config(config_path)

    if not scenes:
        raise ValueError("Configuração sem scenes definidas")

    project["scenes"] = scenes
    project["client_id"] = client_id

    return project, naming


# ==========================================================
# FASTAPI APP
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Backend iniciando...")
    yield
    logging.info("🧹 Backend encerrando...")


app = FastAPI(lifespan=lifespan)

# ==========================================================
# CORS
# ==========================================================

cors_raw = os.getenv("CORS_ORIGINS", "")
origins = [o.strip() for o in cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ==========================================================
# STATIC
# ==========================================================

app.mount("/panoconfig360_cache",
          StaticFiles(directory=LOCAL_CACHE_DIR),
          name="panoconfig360_cache")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ==========================================================
# HEALTH
# ==========================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "panoconfig360-backend",
        "version": "1.0.0",
    }


# ==========================================================
# RENDER 2D
# ==========================================================

@app.post("/api/render2d")
def render_2d(payload: Render2DRequest):

    client_id = validate_safe_id(payload.client, "client")
    scene_id = validate_safe_id(payload.scene, "scene")
    selection = payload.selection

    try:
        project, _ = load_client_config(client_id)
    except FileNotFoundError:
        raise HTTPException(404, "Config não encontrado")
    except ValueError:
        raise HTTPException(422, "Config inválido")
    except Exception:
        raise HTTPException(500, "Erro interno")

    ctx = resolve_scene_context(project, scene_id)

    build_str = build_string_from_selection(
        ctx["scene_index"],
        ctx["layers"],
        selection,
    )

    cdn_key = f"clients/{client_id}/renders/{scene_id}/2d_{build_str}.jpg"

    if exists(cdn_key):
        return {
            "status": "cached",
            "url": get_public_url(cdn_key),
        }

    output_path = None

    try:
        img = stack_layers_image_only(
            scene_id=scene_id,
            layers=ctx["layers"],
            selection=selection,
            assets_root=ctx["assets_root"],
            asset_prefix="2d_",
        )

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            output_path = tmp.name

        img.save(output_path, "JPEG", quality=80, subsampling=0)
        upload_file(output_path, cdn_key, "image/jpeg")

        return {
            "status": "generated",
            "url": get_public_url(cdn_key),
        }

    finally:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)


# ==========================================================
# ROOT
# ==========================================================

@app.get("/")
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "index.html não encontrado")
    return FileResponse(index_path)
