# api/server.py
import os

# Limit libvips concurrency BEFORE any pyvips import
os.environ.setdefault("VIPS_CONCURRENCY", "0")

import gc
import json
import logging
import shutil
import time
import tempfile
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from panoconfig360_backend.render.dynamic_stack import (
    load_config,
    build_string_from_selection,
)
from panoconfig360_backend.render.split_faces_cubemap import process_cubemap
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
from panoconfig360_backend.render.scene_context import resolve_scene_context
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from panoconfig360_backend.utils.build_validation import validate_build_string, validate_safe_id
import re


# CONFIGURAÇÕES GLOBAIS
ROOT_DIR = Path(__file__).resolve().parents[1].parent
CLIENTS_ROOT = Path("panoconfig360_cache/clients")
LOCAL_CACHE_DIR = ROOT_DIR / "panoconfig360_cache"
FRONTEND_DIR = ROOT_DIR / "panoconfig360_frontend"
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
TILE_RE = re.compile(r"^[0-9a-z]+_[fblrud]_\d+_\d+_\d+\.jpg$")
TILE_ROOT_RE = re.compile(r"^clients/[a-z0-9\-]+/cubemap/[a-z0-9\-]+/tiles/[0-9a-z]+$")

USE_MASK_STACK = True

if USE_MASK_STACK:
    from panoconfig360_backend.render.dynamic_stack_with_masks import stack_layers_image_only
else:
    from panoconfig360_backend.render.dynamic_stack import stack_layers_image_only

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

last_request_time = 0.0
lock = threading.Lock()
MIN_INTERVAL = 1.0
MAX_RENDER_LOCKS = 256
render_locks: OrderedDict[str, threading.Lock] = OrderedDict()
render_locks_guard = threading.Lock()
active_background_renders: set[str] = set()
active_background_guard = threading.Lock()

# LOD availability tracking per build
BUILD_STATUS: dict[str, dict] = {}
BUILD_STATUS_LOCK = threading.Lock()


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


def _write_metadata_file(metadata_payload: dict, tmp_dir: str) -> str:
    meta_path = os.path.join(tmp_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f)
    return meta_path


def _tile_state_event_writer(tile_root: str, build_str: str):
    events_key = f"{tile_root}/tile_events.ndjson"

    def _writer(filename: str, state: str, lod: int):
        append_jsonl(
            events_key,
            {
                "filename": filename,
                "build": build_str,
                "state": state,
                "lod": lod,
                "ts": int(time.time() * 1000),
            },
        )

    return _writer


def _tiles_base_url() -> str:
    return get_public_url("").rstrip("/")


_TILE_WORKERS = int(os.getenv("TILE_WORKERS", "4"))


def _render_remaining_lods(
    client_id: str,
    scene_id: str,
    selection: dict,
    build_str: str,
    tile_root: str,
    metadata_key: str,
    stack_img=None,
):
    render_key = f"{client_id}:{scene_id}:{build_str}"

    try:
        start = time.monotonic()
        logging.info("🧵 Background LOD render iniciado para %s", render_key)

        # Reuse the stacked image if provided; otherwise re-stack
        if stack_img is None:
            project, _ = load_client_config(client_id)
            ctx = resolve_scene_context(project, scene_id)

            stack_img = stack_layers_image_only(
                scene_id=scene_id,
                layers=ctx["layers"],
                selection=selection,
                assets_root=ctx["assets_root"],
            )

        # Use a single upload queue for all remaining LODs
        tmp_dir = tempfile.mkdtemp(prefix=f"{build_str}_lods_")
        uploader = TileUploadQueue(
            tile_root=tile_root,
            upload_fn=upload_file,
            workers=_TILE_WORKERS,
            on_state_change=_tile_state_event_writer(tile_root, build_str),
        )
        uploader.start()

        try:
            for lod_level in (1, 2):
                process_cubemap(
                    stack_img,
                    tmp_dir,
                    tile_size=512,
                    build=build_str,
                    min_lod=lod_level,
                    max_lod=lod_level,
                    on_tile_ready=uploader.enqueue,
                )

                # Update BUILD_STATUS after each LOD
                with BUILD_STATUS_LOCK:
                    if build_str in BUILD_STATUS:
                        BUILD_STATUS[build_str]["lod_ready"] = lod_level

                logging.info(
                    "✅ LOD%s gerado para %s",
                    lod_level, render_key,
                )

            uploader.close_and_wait()
            logging.info(
                "✅ Upload concluído para %s (%s tiles)",
                render_key, uploader.uploaded_count,
            )
        finally:
            try:
                uploader.close_and_wait()
            except Exception:
                logging.exception("❌ Erro ao encerrar fila de upload (%s)", render_key)
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Release the stacked image after all LODs are done
        del stack_img
        gc.collect()

        # Final metadata update
        metadata_payload = {
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "tileRoot": tile_root,
            "generated_at": int(time.time()),
            "status": "ready",
            "last_stage": "background_lods_done",
        }
        tmp_meta = tempfile.mkdtemp(prefix=f"{build_str}_meta_")
        try:
            meta_path = _write_metadata_file(metadata_payload, tmp_meta)
            upload_file(meta_path, metadata_key, "application/json")
        finally:
            shutil.rmtree(tmp_meta, ignore_errors=True)

        # Mark as completed
        with BUILD_STATUS_LOCK:
            if build_str in BUILD_STATUS:
                BUILD_STATUS[build_str]["status"] = "completed"
                BUILD_STATUS[build_str]["lod_ready"] = 2

        logging.info("✅ Background LOD render finalizado para %s", render_key)
    except Exception:
        logging.exception("❌ Falha na geração de LODs em background para %s", render_key)
    finally:
        with active_background_guard:
            active_background_renders.discard(render_key)
        elapsed = time.monotonic() - start
        logging.info("⏱️ Background LOD render de %s terminou em %.2fs", render_key, elapsed)


def load_client_config(client_id: str):
    validate_safe_id(client_id, "client_id")

    config_path = LOCAL_CACHE_DIR / "clients" / \
        client_id / f"{client_id}_cfg.json"

    if not config_path.exists():
        logging.error("❌ Config não encontrada: %s", config_path)
        raise FileNotFoundError(
            f"Configuração do cliente '{client_id}' não encontrada em {config_path}.")

    try:
        project, scenes, naming = load_config(config_path)
    except ValueError as exc:
        raise ValueError(
            f"Configuração inválida para cliente '{client_id}': {exc}"
        ) from exc
    except json.JSONDecodeError as e:
        logging.error("❌ Config JSON inválido para client '%s': %s", client_id, e)
        raise ValueError(f"Configuração do cliente '{client_id}' contém JSON inválido: {e}")

    if not scenes:
        logging.error("❌ Config do client '%s' não possui scenes definidas", client_id)
        raise ValueError(f"Configuração do cliente '{client_id}' não possui scenes definidas")

    project["scenes"] = scenes
    project["client_id"] = client_id

    return project, naming


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Iniciando backend STRATY")
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    yield
    logging.info("🧹 Encerrando backend STRATY")


app = FastAPI(lifespan=lifespan)

# CORS middleware
_cors_raw = os.getenv("CORS_ORIGINS", "")
if not _cors_raw:
    logging.warning(
        "⚠️ CORS_ORIGINS não configurado. "
        "Defina CORS_ORIGINS no ambiente para permitir acesso do frontend."
    )
cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/panoconfig360_cache",
          StaticFiles(directory=LOCAL_CACHE_DIR), name="panoconfig360_cache")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.post("/api/render", response_model=None)
def render_cubemap(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    request: Request = None
):
    origin = request.headers.get("origin") if request else None
    logging.info(f"🌐 Requisição recebida de origem: {origin}")

    # ======================================================
    # ⏱️ RATE LIMIT
    # ======================================================
    now = time.monotonic()
    with lock:
        global last_request_time
        if now - last_request_time < MIN_INTERVAL:
            raise HTTPException(
                status_code=429,
                detail="Muitas requisições — aguarde um instante."
            )
        last_request_time = now

    # ======================================================
    # ✅ VALIDAÇÕES
    # ======================================================
    client_id = payload.get("client")
    scene_id = payload.get("scene")
    selection = payload.get("selection")

    if not client_id:
        raise HTTPException(400, "client ausente no payload")
    if not scene_id:
        raise HTTPException(400, "scene ausente no payload")
    if not selection or not isinstance(selection, dict):
        raise HTTPException(400, "selection ausente ou inválida")

    client_id = validate_safe_id(client_id, "client")
    scene_id = validate_safe_id(scene_id, "scene")

    # ======================================================
    # 📦 CARREGA CONFIG
    # ======================================================
    try:
        project, _ = load_client_config(client_id)
    except FileNotFoundError as e:
        logging.warning("❌ Config não encontrado: %s", e)
        raise HTTPException(404, f"Config não encontrado para cliente '{client_id}'.")
    except ValueError as e:
        logging.warning("❌ Config inválido: %s", e)
        raise HTTPException(422, f"Config inválido para cliente '{client_id}'.")
        logging.error("❌ Config não encontrada para client '%s': %s", client_id, e)
        raise HTTPException(404, f"Configuração do cliente não encontrada: {e}")
    except ValueError as e:
        logging.error("❌ Config inválida para client '%s': %s", client_id, e)
        raise HTTPException(400, f"Configuração do cliente inválida: {e}")
    except Exception as e:
        logging.exception("❌ Falha inesperada ao carregar config do client '%s'", client_id)
        raise HTTPException(500, "Erro interno ao carregar configuração")

    # ======================================================
    # 🎬 RESOLVE CENA
    # ======================================================
    try:
        ctx = resolve_scene_context(project, scene_id)
    except Exception as e:
        logging.exception("❌ Cena inválida")
        raise HTTPException(400, f"Cena inválida: {e}")

    scene_layers = ctx["layers"]
    assets_root = ctx["assets_root"]
    scene_index = ctx["scene_index"]

    # ======================================================
    # 🧮 BUILD STRING (SEM PROCESSAR IMAGEM)
    # ======================================================

    build_str = build_string_from_selection(
        scene_index, scene_layers, selection)

    logging.info(f"🔑 Build string: {build_str} ({len(build_str)} chars)")

    # ======================================================
    # 🔍 VERIFICA CACHE
    # ======================================================
    tile_root = f"clients/{client_id}/cubemap/{scene_id}/tiles/{build_str}"
    metadata_key = f"{tile_root}/metadata.json"
    render_key = f"{client_id}:{scene_id}:{build_str}"

    cache_exists = exists(metadata_key)
    logging.info(f"🔍 Cache check: {metadata_key} → exists={cache_exists}")

    if cache_exists:
        logging.info(f"✅ Cache hit: {build_str}")

        tiles = {
            "baseUrl": _tiles_base_url(),
            "tileRoot": tile_root,
            "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
            "build": build_str,
        }

        return {
            "status": "cached",
            "build": build_str,
            "tiles": tiles,
        }

    # ======================================================
    # 🏗️ PROCESSA IMAGEM (SÓ SE NÃO TEM CACHE) - FASE 1 (LOD 0)
    # ======================================================
    render_lock = _get_render_lock(render_key)
    with render_lock:
        if exists(metadata_key):
            tiles = {
                "baseUrl": _tiles_base_url(),
                "tileRoot": tile_root,
                "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
                "build": build_str,
            }
            return {
                "status": "cached",
                "build": build_str,
                "tiles": tiles,
            }

        logging.info("🏗️ Cache miss — iniciando processamento LOD0 para %s", render_key)
        start = time.monotonic()
        tmp_dir = tempfile.mkdtemp(prefix=f"{build_str}_lod0_")
        logging.info(f"📁 Temp dir: {tmp_dir}")
        uploader = None
        stack_img_for_bg = None

        try:
            uploader = TileUploadQueue(
                tile_root=tile_root,
                upload_fn=upload_file,
                workers=_TILE_WORKERS,
                on_state_change=_tile_state_event_writer(tile_root, build_str),
            )
            uploader.start()

            stack_img = stack_layers_image_only(
                scene_id=scene_id,
                layers=scene_layers,
                selection=selection,
                assets_root=assets_root,
            )

            process_cubemap(
                stack_img,
                tmp_dir,
                tile_size=512,
                build=build_str,
                max_lod=0,
                on_tile_ready=uploader.enqueue,
            )
            # Keep the stacked image for the background task to avoid re-compositing
            stack_img_for_bg = stack_img
            del stack_img
            uploader.close_and_wait()

            lod0_uploaded = uploader.uploaded_count
            metadata_payload = {
                "client": client_id,
                "scene": scene_id,
                "build": build_str,
                "tileRoot": tile_root,
                "generated_at": int(time.time()),
                "status": "processing",
                "last_stage": "lod0_ready",
                "lod0_tiles_count": lod0_uploaded,
            }
            meta_path = _write_metadata_file(metadata_payload, tmp_dir)
            upload_file(meta_path, metadata_key, "application/json")

            # Initialize BUILD_STATUS tracking
            with BUILD_STATUS_LOCK:
                BUILD_STATUS[build_str] = {
                    "status": "processing",
                    "lod_ready": 0,
                }

            gc.collect()

            elapsed = time.monotonic() - start
            logging.info("✅ LOD0 pronto para %s em %.2fs (%s tiles)", render_key, elapsed, lod0_uploaded)
        except Exception as e:
            logging.exception("❌ Erro no render LOD0")
            raise HTTPException(500, f"Erro interno: {e}")
        finally:
            if uploader is not None:
                try:
                    uploader.close_and_wait()
                except Exception:
                    logging.exception("❌ Erro ao encerrar fila de upload (%s)", render_key)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logging.info(f"🧹 Temp removido: {tmp_dir}")

    with active_background_guard:
        if render_key not in active_background_renders:
            background_tasks.add_task(
                _render_remaining_lods,
                client_id,
                scene_id,
                selection,
                build_str,
                tile_root,
                metadata_key,
                stack_img_for_bg,
            )
            active_background_renders.add(render_key)
            logging.info("🧵 Background task agendada para LODs >= 1 (%s)", render_key)

    tiles = {
        "baseUrl": _tiles_base_url(),
        "tileRoot": tile_root,
        "pattern": f"{build_str}_{{f}}_{{z}}_{{x}}_{{y}}.jpg",
        "build": build_str,
    }

    return {
        "status": "generated",
        "client": client_id,
        "scene": scene_id,
        "build": build_str,
        "tiles": tiles,
    }


@app.get("/api/render/events")
def render_tile_events(tile_root: str, cursor: int = 0, limit: int = 200):
    if not TILE_ROOT_RE.match(tile_root):
        raise HTTPException(status_code=400, detail="tile_root inválido")

    if cursor < 0:
        raise HTTPException(status_code=400, detail="cursor inválido")

    limit = max(1, min(limit, 500))
    events_key = f"{tile_root}/tile_events.ndjson"
    events, next_cursor = read_jsonl_slice(events_key, cursor=cursor, limit=limit)

    # Check if render is complete by reading metadata status
    metadata_key = f"{tile_root}/metadata.json"
    completed = False
    try:
        metadata = get_json(metadata_key)
        completed = metadata.get("status") == "ready"
    except FileNotFoundError:
        completed = False
    except (json.JSONDecodeError, IOError) as e:
        logging.warning("⚠️ Failed to read metadata for completion check: %s", e)
        completed = False

    return {
        "status": "success",
        "data": {
            "events": events,
            "cursor": next_cursor,
            "hasMore": len(events) >= limit,
            "completed": completed,
        },
    }


# RENDER 2D SIMPLES (SEM CACHE DE TILES, APENAS IMAGEM FINAL)

@app.post("/api/render2d")
def render_2d(payload: Render2DRequest):
    client_id = validate_safe_id(payload.client, "client")
    scene_id = validate_safe_id(payload.scene, "scene")
    selection = payload.selection

    logging.info(f"🖼️ Render 2D: client={client_id}, scene={scene_id}")

    try:
        project, _ = load_client_config(client_id)
    except FileNotFoundError as e:
        logging.warning("❌ Config não encontrado: %s", e)
        raise HTTPException(404, f"Config não encontrado para cliente '{client_id}'.")
    except ValueError as e:
        logging.warning("❌ Config inválido: %s", e)
        raise HTTPException(422, f"Config inválido para cliente '{client_id}'.")
        logging.error("❌ Config não encontrada para client '%s': %s", client_id, e)
        raise HTTPException(404, f"Configuração do cliente não encontrada: {e}")
    except ValueError as e:
        logging.error("❌ Config inválida para client '%s': %s", client_id, e)
        raise HTTPException(400, f"Configuração do cliente inválida: {e}")
    except Exception as e:
        logging.exception("❌ Falha inesperada ao carregar config do client '%s'", client_id)
        raise HTTPException(500, "Erro interno ao carregar configuração")

    try:
        ctx = resolve_scene_context(project, scene_id)
    except Exception as e:
        logging.exception("❌ Cena inválida")
        raise HTTPException(400, f"Cena inválida: {e}")

    scene_layers = ctx["layers"]
    assets_root = ctx["assets_root"]
    scene_index = ctx["scene_index"]

    build_str = build_string_from_selection(
        scene_index, scene_layers, selection)

    logging.info(f"🔑 Build string 2D: {build_str} ({len(build_str)} chars)")

    cdn_key = f"clients/{client_id}/renders/{scene_id}/2d_{build_str}.jpg"

    cache_exists = exists(cdn_key)
    logging.info(f"🔍 Cache 2D check: {cdn_key} → exists={cache_exists}")

    if cache_exists:
        logging.info(f"✅ Cache 2D hit: {build_str}")
        return {
            "status": "cached",
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "url": get_public_url(cdn_key),
        }

    # 🏗️ PROCESSA IMAGEM 2D (USANDO STACK COM MASKS)

    logging.info("🏗️ Cache 2D miss — iniciando processamento...")

    start = time.monotonic()

    output_path = None

    try:
        img = stack_layers_image_only(
            scene_id=scene_id,
            layers=scene_layers,
            selection=selection,
            assets_root=assets_root,
            asset_prefix="2d_",
        )

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            output_path = tmp.name

        img.save(output_path, "JPEG", quality=80, subsampling=0)
        upload_file(output_path, cdn_key, "image/jpeg")

        return {
            "status": "generated",
            "client": client_id,
            "scene": scene_id,
            "build": build_str,
            "url": get_public_url(cdn_key),
        }

    except FileNotFoundError as e:
        logging.error("❌ Asset não encontrado no render 2D: %s", e)
        raise HTTPException(
            status_code=404,
            detail=f"Asset não encontrado: {e}",
        )

    except Exception as e:
        logging.exception("❌ Erro inesperado no render 2D")
        raise HTTPException(
            status_code=500,
            detail="Erro interno no render 2D",
        )

    finally:
        if output_path is not None and os.path.exists(output_path):
            os.remove(output_path)


@app.get("/")
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "index.html não encontrado")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "panoconfig360-backend", "version": "0.0.1"}


@app.get("/api/status/{build_id}")
def build_status(build_id: str):
    build_id = validate_build_string(build_id)
    with BUILD_STATUS_LOCK:
        entry = BUILD_STATUS.get(build_id)
    if entry is not None:
        return entry
    # Build not tracked in memory (e.g. server restart) — return unknown
    return {"status": "unknown", "lod_ready": 0}


@app.get("/panoconfig360_cache/cubemap/{client_id}/{scene_id}/tiles/{build}/{filename}")
def get_tile(client_id: str, scene_id: str, build: str, filename: str):

    # valida IDs para prevenir path traversal
    client_id = validate_safe_id(client_id, "client_id")
    scene_id = validate_safe_id(scene_id, "scene_id")

    # valida build
    build = validate_build_string(build)

    # valida filename estritamente
    if not TILE_RE.match(filename):
        raise HTTPException(400, "Tile inválido")

    # filename deve começar com build correto
    if not filename.startswith(build + "_"):
        raise HTTPException(400, "Tile não pertence à build")

    # caminho isolado por tenant e cena
    tile_path = (
        LOCAL_CACHE_DIR
        / "clients"
        / client_id
        / "cubemap"
        / scene_id
        / "tiles"
        / build
        / filename
    )

    if not tile_path.exists():
        raise HTTPException(404, "Tile não encontrado")

    return FileResponse(
        tile_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
